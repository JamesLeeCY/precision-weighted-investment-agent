"""產業內相對估值訊號（參考 WorldQuant BRAIN 的 industry-relative valuation alpha，改寫成台股可得的資料）。

原式（使用者提供）：
    ts_decay_linear(group_neutralize(group_zscore(ts_backfill(industry_relative_valuation_rank, 60), market),
        group_cartesian_product(subindustry, bucket(rank(cap), range="0,1,0.2"))), 10)

台股版本（設計在看結果前固定）：
1. industry_relative_valuation_rank：同產業（當年成員）內，盈餘殖利率 1/PER、帳面市值比 1/PBR、現金殖利率各自取百分位，
   再平均（越高越便宜）。PER ≤ 0（虧損）的盈餘殖利率視為缺值。
2. ts_backfill 60：每檔股票向前補值，最多 60 個交易日。
3. group_zscore(market)：當日全股票池 z 分數。
4. group_neutralize(產業 × 市值五分位)：減去所屬格子的平均。市值 = 收盤價 × 普通股股本 ÷ 10（季報遞延 75 天）；
   FinMind 免費層沒有市值資料。沒有子產業分類，只用 7 個大產業。
5. ts_decay_linear 10：最近 10 個交易日線性遞減加權平均。
無前視：預測日 d 只用 d 前一個交易日以前的估值與股價。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/valuation_signal.py fetch config/tickers_pit.yaml          # 抓 TaiwanStockPER（每檔 1 次呼叫）
    .venv/Scripts/python analysis/valuation_signal.py build daily_pit.csv config/tickers_pit.yaml daily_pit_val.csv
之後用 sector_neutral_portfolio.py / oos_report.py 以 --signal val_signal 等欄位評估。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from data.fetch_financials import FinMindClient, get_total_return_prices  # noqa: E402

START, END = "2018-06-01", "2026-05-31"
STATEMENT_LAG_DAYS = 75


def tickers_of(config):
    cfg = yaml.safe_load(open(config, encoding="utf-8"))
    return [u["ticker"] for u in cfg["universe"]], {u["ticker"]: u["segment"] for u in cfg["universe"]}


def fetch(config):
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    tickers, _ = tickers_of(config)
    for k, t in enumerate(tickers):
        d = client.get("TaiwanStockPER", t.split(".")[0], START, END)
        if k % 20 == 0:
            print(f"  {k}/{len(tickers)} {t} rows={len(d)}", flush=True)
    print("done")


def load_panel(tickers):
    """每檔每日的估值（PER/PBR/殖利率）與市值；索引 (date, ticker)。"""
    client = FinMindClient()
    frames = []
    for t in tickers:
        sid = t.split(".")[0]
        v = client.get("TaiwanStockPER", sid, START, END)
        if v.empty:
            continue
        v = v[["date", "PER", "PBR", "dividend_yield"]].copy()
        v["date"] = pd.to_datetime(v["date"])
        # 與回測相同的查詢參數 → 直接命中既有快取（收盤價為未還原價，市值用）
        px = get_total_return_prices(client, t, "2019-01-01", "2026-05-31")
        if not px.empty:
            px = px[["date", "close"]].assign(date=lambda x: pd.to_datetime(x["date"]))
            v = v.merge(px, on="date", how="left")
        else:
            v["close"] = np.nan
        bs = client.get("TaiwanStockBalanceSheet", sid, "2017-01-01")
        shares = pd.Series(dtype=float)
        if not bs.empty:
            sh = bs[bs["type"] == "OrdinaryShare"][["date", "value"]].copy()
            sh["avail"] = pd.to_datetime(sh["date"]) + pd.Timedelta(days=STATEMENT_LAG_DAYS)
            shares = sh.set_index("avail")["value"].astype(float).sort_index() / 10.0
        v = v.sort_values("date")
        v["shares"] = shares.reindex(v["date"], method="ffill").to_numpy() if len(shares) else np.nan
        v["cap"] = v["close"] * v["shares"]
        v["ticker"] = t
        # 無前視：預測日 d 使用前一個交易日的資料
        for c in ("PER", "PBR", "dividend_yield", "cap"):
            v[c] = v[c].shift(1)
        frames.append(v)
    return pd.concat(frames, ignore_index=True)


def pct_rank(s):
    return s.rank(pct=True, method="average")


def decay_linear(s: pd.Series, n: int = 10) -> pd.Series:
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n, min_periods=1).apply(lambda x: np.dot(x, w[-len(x):]) / w[-len(x):].sum(), raw=True)


def build(daily_csv, config, out_csv):
    tickers, sectors = tickers_of(config)
    daily = pd.read_csv(daily_csv, parse_dates=["date"])
    panel = load_panel(tickers)
    df = daily.merge(panel[["date", "ticker", "PER", "PBR", "dividend_yield", "cap"]], on=["date", "ticker"], how="left")
    df["sector"] = df["ticker"].map(sectors)
    df["ey"] = np.where(df["PER"] > 0, 1.0 / df["PER"], np.nan)
    df["bp"] = np.where(df["PBR"] > 0, 1.0 / df["PBR"], np.nan)
    df["dy"] = df["dividend_yield"].where(df["dividend_yield"] >= 0)

    # 1. 產業內相對估值百分位（三項平均）
    g = df.groupby(["date", "sector"])
    ranks = pd.concat([g[c].transform(pct_rank) for c in ("ey", "bp", "dy")], axis=1)
    df["val_rank"] = ranks.mean(axis=1, skipna=True)
    # 2. ts_backfill 60（每檔依日期向前補值）
    df = df.sort_values(["ticker", "date"])
    df["val_bf"] = df.groupby("ticker")["val_rank"].transform(lambda s: s.ffill(limit=60))
    df["cap_bf"] = df.groupby("ticker")["cap"].transform(lambda s: s.ffill(limit=60))
    # 3. 全市場 z 分數
    gd = df.groupby("date")["val_bf"]
    df["val_z"] = (df["val_bf"] - gd.transform("mean")) / gd.transform("std")
    # 4. 產業 × 市值五分位中性化
    df["cap_q"] = df.groupby("date")["cap_bf"].transform(lambda s: np.minimum((pct_rank(s) * 5).apply(np.ceil), 5))
    cell = df["sector"].astype(str) + "|" + df["cap_q"].fillna(-1).astype(int).astype(str)
    df["val_neut"] = df["val_z"] - df.groupby([df["date"], cell])["val_z"].transform("mean")
    # 5. 10 日線性遞減加權
    df["val_signal"] = df.groupby("ticker")["val_neut"].transform(decay_linear)
    # 對照：只做產業內排名（未中性化市值、未平滑）
    df["val_rank_only"] = df["val_rank"]
    # 與財報 Agent 合成：產業內百分位平均
    gs = df.groupby(["date", "sector"])
    df["combo_fund_val"] = (gs["pc_fundamentals_agent"].transform(pct_rank) + gs["val_signal"].transform(pct_rank)) / 2
    df = df.sort_values(["i", "ticker"])
    keep = [c for c in daily.columns] + ["sector", "val_rank_only", "val_signal", "combo_fund_val", "cap_q"]
    df[keep].to_csv(out_csv, index=False)
    cov = df["val_signal"].notna().mean()
    print(f"{len(df)} 列；val_signal 覆蓋率 {cov:.1%}；市值覆蓋率 {df['cap_bf'].notna().mean():.1%}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "fetch":
        fetch(sys.argv[2])
    elif cmd == "build":
        build(sys.argv[2], sys.argv[3], sys.argv[4])
