"""技術面、動能、均值回歸、估值訊號的產業內選股能力，以及進出場濾網對 Sharpe 的影響。

用法（於專案根目錄；輸入為 valuation_signal.py build 的輸出）：
    .venv/Scripts/python analysis/technical_timing.py daily_pit_val.csv config/tickers_pit.yaml
輸出 docs/technical_timing_data.md（自動產生的數字），並把加上技術欄位的每日表存成 <輸入>_tech.csv。

訊號（參數為文獻標準值，看結果前固定；只用預測日前一個交易日以前的含息還原價）：
- pc_technical：技術面 Agent 連續輸出（均線趨勢、均線排列、量價、支撐壓力、K 線）
- mom_12_1 / mom_6_1：t−21 相對 t−252 / t−126 的報酬（跳過最近一個月）
- rev_1m / rev_1w：過去 21 / 5 個交易日報酬的負值（短期反轉）
- val_signal：產業內相對估值（valuation_signal.py）；combo_fund_val：財報 + 估值的產業內百分位平均
進出場濾網（只在換倉日判斷，持有 20 日不中途出場）：
- 大盤：0050 前一日含息收盤 > 200 日均線才持股，否則全部現金
- 個股：股價 > 60 日均線才持有（被剔除的權重持現金）
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
import sector_neutral_portfolio as snp  # noqa: E402
from agents.base import continuous_judgement  # noqa: E402
from agents.technical_agent import TechnicalAgent  # noqa: E402
from backtest.portfolio import max_drawdown  # noqa: E402
from data.fetch_financials import FinMindClient, get_total_return_prices  # noqa: E402
from data.fetch_technical import FinMindTechnicalProvider  # noqa: E402

PPY = 252 / 21
COST = snp.COST_PER_SIDE
SPLIT = "2023-01-01"
SEGMENTS = [("2019–2022 樣本外", lambda d: d < SPLIT), ("2023–2026/05", lambda d: d >= SPLIT)]
SIGNALS = [
    ("pc_fundamentals_agent", "財報 Agent（基準）"),
    ("val_signal", "產業內相對估值"),
    ("combo_fund_val", "財報 + 估值"),
    ("pc_technical", "技術面 Agent"),
    ("mom_12_1", "動能 12-1 月"),
    ("mom_6_1", "動能 6-1 月"),
    ("rev_1m", "反轉 1 個月"),
    ("rev_1w", "反轉 1 週"),
]


def add_technical(df: pd.DataFrame) -> pd.DataFrame:
    prov = FinMindTechnicalProvider(FinMindClient(), "2019-01-01", "2026-05-31")
    parts = []
    for t in df["ticker"].unique():
        ind = prov.indicators(t)
        if ind.empty:
            continue
        c = ind["close"]
        ind = ind.assign(
            mom_12_1=c.shift(21) / c.shift(252) - 1, mom_6_1=c.shift(21) / c.shift(126) - 1,
            rev_1m=-(c / c.shift(21) - 1), rev_1w=-(c / c.shift(5) - 1), above_ma60=(c > ind["ma60"]).astype(float),
        )
        ind.loc[ind["ma60"].isna(), "above_ma60"] = np.nan
        ind["ticker"] = t
        parts.append(ind)
    ind = pd.concat(parts, ignore_index=True)
    cols = ["trend", "ma_spread", "vol_price", "breakout", "candle", "mom_12_1", "mom_6_1", "rev_1m", "rev_1w", "above_ma60"]
    # 無前視：預測日 d 用 d 之前最後一列（allow_exact_matches=False）
    left = df.sort_values("date")
    right = ind[["date", "ticker", *cols]].sort_values("date")
    out = pd.merge_asof(left, right, on="date", by="ticker", allow_exact_matches=False)
    judged = out[["trend", "ma_spread", "vol_price", "breakout", "candle"]].to_dict("records")
    pcs = []
    for row in judged:
        _, _, _, score, cov = TechnicalAgent.judge(row)
        pcs.append(continuous_judgement(score, cov)[2])
    out["pc_technical"] = pcs
    return out.sort_values(["i", "ticker"]).reset_index(drop=True)


def market_regime(dates) -> pd.Series:
    """0050 前一交易日含息收盤是否高於 200 日均線。"""
    px = get_total_return_prices(FinMindClient(), "0050.TW", "2017-06-01", "2026-05-31")
    adj = pd.Series(px["adj_close"].astype(float).to_numpy(), index=pd.DatetimeIndex(px["date"]))
    on = (adj > adj.rolling(200, min_periods=200).mean()).astype(float)
    on[adj.rolling(200, min_periods=200).mean().isna()] = np.nan
    return pd.Series({d: on[on.index < d].iloc[-1] if (on.index < d).any() else np.nan for d in pd.to_datetime(dates)})


def bench_20d(df):
    px = get_total_return_prices(FinMindClient(), "0050.TW", "2019-01-01", "2026-05-31")
    adj = pd.Series(px["adj_close"].astype(float).to_numpy(), index=pd.DatetimeIndex(px["date"]))
    cal = df.groupby("i")["date"].first()
    out = {}
    for i, d0 in cal.items():
        if i + 20 in cal.index:
            d1 = cal[i + 20]
        else:
            pos = adj.index.searchsorted(d0)
            if pos + 20 >= len(adj):
                continue
            d1 = adj.index[pos + 20]
        out[d0] = adj.asof(d1) / adj.asof(d0) - 1
    return pd.Series(out)


def daily_within_ic(df, col):
    def one(g):
        vals, w = [], []
        for _, s in g.groupby("sector"):
            s = s.dropna(subset=[col])
            if len(s) >= 3 and s[col].nunique() > 1:
                vals.append(s[col].rank().corr(s["ret"].rank()))
                w.append(len(s))
        return np.average(vals, weights=w) if vals else np.nan
    return df.groupby("i").apply(one)


def stats(r):
    r = np.asarray(r, dtype=float)
    total = float(np.prod(1 + r) - 1)
    ann = (1 + total) ** (PPY / len(r)) - 1 if total > -1 else -1.0
    vol = r.std(ddof=1) * math.sqrt(PPY)
    return ann, (ann / vol if vol else float("nan")), max_drawdown(r)


def overlay_series(df, regime, bench, phase, signal="pc_fundamentals_agent", base="sn", mkt=False, stock=False):
    rows, prev = [], {}
    for i in sorted(df["i"].unique()):
        if i % snp.STEP != phase:
            continue
        g = df[df["i"] == i]
        d = g["date"].iloc[0]
        if base == "sn":
            w = snp.sector_neutral_weights(g.dropna(subset=[signal]), signal, 1 / 3, 3, +1)
        elif base == "ew":
            w = {t: 1 / len(g) for t in g["ticker"]}
        else:  # 0050
            w = {"0050": 1.0}
        if stock and base != "0050":
            ok = set(g.loc[g["above_ma60"] == 1.0, "ticker"])
            w = {t: x for t, x in w.items() if t in ok}
        if mkt and regime.get(d) == 0:
            w = {}
        rets = g.set_index("ticker")["ret"].to_dict()
        rets["0050"] = bench.get(d, np.nan)
        gross = sum(x * rets[t] for t, x in w.items())
        to = sum(abs(w.get(t, 0) - prev.get(t, 0)) for t in set(w) | set(prev))
        rows.append({"d": d.strftime("%Y-%m-%d"), "net": gross - to * COST, "exposure": sum(w.values())})
        prev = w
    return pd.DataFrame(rows)


def main(path, config):
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")  # 0050 較長歷史（200 日均線）可能需要呼叫 API
    regime_check = market_regime([pd.Timestamp("2019-01-02")])  # 先確認資料可取得，避免跑完訊號才失敗
    print(f"0050 200 日線資料 OK（2019-01-02 狀態 {regime_check.iloc[0]}）", flush=True)
    df = pd.read_csv(path, parse_dates=["date"])
    cfg = yaml.safe_load(open(config, encoding="utf-8"))
    df["sector"] = df["ticker"].map({u["ticker"]: u["segment"] for u in cfg["universe"]})
    df = df.dropna(subset=["sector", "ret"])
    df = add_technical(df)
    df.to_csv(Path(path).with_name(Path(path).stem + "_tech.csv"), index=False)
    dates = df.groupby("i")["date"].first()

    out = ["# 技術面 / 動能 / 反轉 / 估值與進出場濾網（自動產生）", "",
           "由 [analysis/technical_timing.py](../analysis/technical_timing.py) 產生；解讀見 "
           "[technical_timing_report.md](technical_timing_report.md)。21 種取樣起點的中位數，含息總報酬、扣交易成本。", "",
           "## 一、產業內選股能力", "",
           "| 訊號 | 產業內 IC 2019–2022（為正起點） | 產業內 IC 2023–2026 | 產業中性做多 − 等權 2019–2022（扣成本） | 2023–2026 | 每期換手 |",
           "|---|---|---|---|---|---|"]
    for col, label in SIGNALS:
        ic = daily_within_ic(df, col)
        cells = []
        for _, fn in SEGMENTS:
            mask = np.array([fn(dates[i].strftime("%Y-%m-%d")) for i in ic.index])
            sub = ic[mask]
            by_phase = sub.groupby(sub.index % snp.STEP).mean()
            cells.append(f"{by_phase.median():+.3f}（{(by_phase > 0).sum()}/21）")
        phases = [snp.phase_series(df.dropna(subset=[col]), col, 1 / 3, 3, ph) for ph in range(snp.STEP)]
        ex = []
        for _, fn in SEGMENTS:
            m = [p[pd.to_datetime(p["date"]).dt.strftime("%Y-%m-%d").map(fn)]["sn_excess_net"].mean() for p in phases]
            ex.append(f"{np.median(m) * 100:+.2f}%（{sum(x > 0 for x in m)}/21）")
        to = np.median([p["sn_to"].mean() for p in phases])
        out.append(f"| {label} | {cells[0]} | {cells[1]} | {ex[0]} | {ex[1]} | {to:.2f} |")
        print(out[-1], flush=True)

    regime = market_regime(dates.values)
    bench = bench_20d(df)
    out += ["", "## 二、進出場濾網（Sharpe／最大回撤／年化報酬／平均持股比例）", "",
            "| 組合 | " + " | ".join(name for name, _ in SEGMENTS) + " |", "|---|---|---|"]
    configs = [
        ("0050 買進持有", dict(base="0050")),
        ("0050 + 大盤濾網（> 200 日線）", dict(base="0050", mkt=True)),
        ("等權持有全部", dict(base="ew")),
        ("等權 + 大盤濾網", dict(base="ew", mkt=True)),
        ("財報產業中性做多", dict(base="sn")),
        ("財報產業中性 + 大盤濾網", dict(base="sn", mkt=True)),
        ("財報產業中性 + 個股濾網（> 60 日線）", dict(base="sn", stock=True)),
        ("財報產業中性 + 大盤與個股濾網", dict(base="sn", mkt=True, stock=True)),
        ("財報 + 估值產業中性做多", dict(base="sn", signal="combo_fund_val")),
        ("財報 + 估值產業中性 + 大盤濾網", dict(base="sn", signal="combo_fund_val", mkt=True)),
    ]
    for label, kw in configs:
        series = [overlay_series(df, regime, bench, ph, **kw) for ph in range(snp.STEP)]
        cells = []
        for _, fn in SEGMENTS:
            st = [stats(s[s["d"].map(fn)]["net"].dropna()) for s in series]
            expo = np.median([s[s["d"].map(fn)]["exposure"].mean() for s in series])
            cells.append(f"{np.median([x[1] for x in st]):.2f}／{np.median([x[2] for x in st]) * 100:.0f}%／"
                         f"{np.median([x[0] for x in st]) * 100:+.1f}%／{expo:.0%}")
        out.append(f"| {label} | {cells[0]} | {cells[1]} |")
        print(out[-1], flush=True)
    off = 1 - regime.dropna().mean()
    out += ["", f"大盤濾網在預測日處於「空手」的比例：{off:.0%}（2019-01 ~ 2026-05）。", ""]
    (ROOT / "docs" / "technical_timing_data.md").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
