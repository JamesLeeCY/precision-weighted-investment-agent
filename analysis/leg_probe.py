"""台股版單腿探針（參考使用者在 WorldQuant 的流程：固定包裝 → 單腿探針 → 腿池 → 本機枚舉）。

用法（於專案根目錄；先執行 build_universe_mcap.py 與 fetch_leg_data.py）：
    .venv/Scripts/python analysis/leg_probe.py 300           # 全市場市值前 300 檔
    .venv/Scripts/python analysis/leg_probe.py 100 --membership config/universe_pit_membership.csv   # 開發用：電子股 100 檔
輸出 docs/leg_probe_top{N}.md 與 reports/legs/pnl_top{N}.csv（每條腿的每日純 alpha 報酬，供 leg_enumerate.py 使用）。

設計（看結果前固定）：
- 股票池：每年依市值排名的前 N 名（config/universe_mcap_membership.csv）；產業為 TaiwanStockInfo 分類。
- 換倉日：每月營收公告期限後的下一個交易日（data/revenue_signal.event_dates），只用 2026-05 之前（之後保留給前瞻驗證）。
- 腿（第 t 日的值只用 t−1 日以前的資料）：
  價量：lowvol20 / lowvol60（−報酬標準差）、resvol60（−對加權指數回歸的殘差標準差）、abvol60（成交量 60 日 z 分數）、
       amihud20（−|報酬|/成交金額 的 20 日平均）、season（過去 1–5 年同月份平均報酬）
  籌碼：short_ratio（−券資比）、short_flow（−20 日融券餘額增量 / 已發行股數）、trust_buy（20 日投信淨買超 / 已發行股數）、
       foreign_chg（20 日外資持股比例變化）
  主腿：sue（月營收驚奇；每月一值，不做 20 日平滑）
- 標準包裝：產業內 z 分數 → 20 日平均 → 換倉日對產業虛擬變數與 log 市值迴歸取殘差。
- 組合：產業內前 1/3 等權，產業權重 = 股票池產業權重；持有到下個換倉日。
- 純 alpha：每日 Σ w·r − β·r_台指期；β = 持股的 250 日 β（對加權指數含息報酬）加權平均，換倉日決定；
  台指期為近月連續（一般交易時段成交量最大的月合約）。成本：股票換手 × 單邊 0.29625%，期貨部位變動 × 單邊 0.005%。
- 指標：純 alpha 年化 Sharpe（2019–2022 / 2023–2026/04、逐年）、產業內 IC（20 日）、年換手、與 0050 的相關。
"""
import argparse
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from data.fetch_financials import FinMindClient, get_adjustment_events, total_return_index  # noqa: E402
from data.revenue_signal import event_dates, revenue_surprise  # noqa: E402

PX_START, EV_START, EV_END = "2018-06-01", "2018-06-01", "2026-05-31"
HOLDOUT = pd.Timestamp("2026-05-01")
SPLIT = pd.Timestamp("2023-01-01")
STOCK_COST, FUT_COST = 0.0029625, 0.00005
Q = 1 / 3
LEGS_PRICE = ["lowvol20", "lowvol60", "resvol60", "abvol60", "amihud20", "season"]
LEGS_CHIP = ["short_ratio", "short_flow", "trust_buy", "foreign_chg"]


# ---------------------------------------------------------------------------
# 資料
# ---------------------------------------------------------------------------

def load_stock(client, sid):
    px = client.get("TaiwanStockPrice", sid, PX_START)
    if px.empty:
        return None
    px = px[px["close"].astype(float) > 0].copy()
    px["date"] = pd.to_datetime(px["date"])
    px = px.sort_values("date").reset_index(drop=True)
    ev = get_adjustment_events(client, sid + ".TW", EV_START, EV_END)
    adj = total_return_index(px[["date", "close"]], ev)
    return pd.DataFrame({"date": px["date"], "adj": adj.to_numpy(), "volume": px["Trading_Volume"].astype(float).to_numpy(),
                         "money": px["Trading_money"].astype(float).to_numpy()}).set_index("date")


def load_chips(client, sid):
    out = {}
    mg = client.get("TaiwanStockMarginPurchaseShortSale", sid, EV_START, EV_END)
    if not mg.empty:
        mg = mg.assign(date=pd.to_datetime(mg["date"])).set_index("date")
        out["short_bal"] = mg["ShortSaleTodayBalance"].astype(float)
        out["margin_bal"] = mg["MarginPurchaseTodayBalance"].astype(float)
    sh = client.get("TaiwanStockShareholding", sid, EV_START, EV_END)
    if not sh.empty:
        sh = sh.assign(date=pd.to_datetime(sh["date"])).set_index("date")
        out["shares"] = sh["NumberOfSharesIssued"].astype(float)
        out["foreign_ratio"] = sh["ForeignInvestmentSharesRatio"].astype(float)
    ii = client.get("TaiwanStockInstitutionalInvestorsBuySell", sid, EV_START, EV_END)
    if not ii.empty:
        it = ii[ii["name"] == "Investment_Trust"].assign(date=lambda x: pd.to_datetime(x["date"]))
        out["trust_net"] = (it["buy"].astype(float) - it["sell"].astype(float)).groupby(it["date"]).sum()
    return out


def tx_continuous(client) -> pd.Series:
    d = client.get("TaiwanFuturesDaily", "TX", "2019-01-01", EV_END)  # 對沖只用 2019 年起；與既有快取同鍵
    d = d[(d["trading_session"] == "position") & d["contract_date"].str.fullmatch(r"\d{6}") & (d["close"].astype(float) > 0)].copy()
    d["date"] = pd.to_datetime(d["date"])
    d["close"] = d["close"].astype(float)
    front = d.sort_values(["date", "volume"]).groupby("date").tail(1).set_index("date")["contract_date"]
    px = d.pivot_table(index="date", columns="contract_date", values="close")
    rets = {}
    dates = list(px.index)
    for k in range(1, len(dates)):
        c = front[dates[k]]
        p0, p1 = px.at[dates[k - 1], c] if c in px.columns else np.nan, px.at[dates[k], c]
        rets[dates[k]] = p1 / p0 - 1 if p0 == p0 and p0 > 0 else 0.0
    return pd.Series(rets)


def market_tri(client) -> pd.Series:
    t = client.get("TaiwanStockTotalReturnIndex", "TAIEX", EV_START, EV_END)
    return pd.Series(t["price"].astype(float).to_numpy(), index=pd.to_datetime(t["date"])).sort_index()


# ---------------------------------------------------------------------------
# 腿
# ---------------------------------------------------------------------------

def raw_legs(adj, vol, money, mkt, chips) -> dict[str, pd.DataFrame]:
    r = adj.pct_change()
    m = mkt.pct_change().reindex(r.index)
    legs = {
        "lowvol20": -r.rolling(20, min_periods=15).std(),
        "lowvol60": -r.rolling(60, min_periods=40).std(),
        "abvol60": (vol - vol.rolling(60, min_periods=40).mean()) / vol.rolling(60, min_periods=40).std(),
        "amihud20": -(r.abs() / money.replace(0, np.nan)).rolling(20, min_periods=15).mean(),
    }
    cov = r.rolling(60, min_periods=40).cov(m)
    var_m = m.rolling(60, min_periods=40).var()
    beta = cov.div(var_m, axis=0)
    resid_var = r.rolling(60, min_periods=40).var() - beta.pow(2).mul(var_m, axis=0)
    legs["resvol60"] = -np.sqrt(resid_var.clip(lower=0))
    # 季節性：過去 1–5 年同月份的平均月報酬（同一個月內各日相同）
    # 在 M−1 月底就知道「過去 1–5 年 M 月」的報酬：mret.shift(12k−1) 在 M−1 月底的值 = M−12k 月的報酬
    month_end = adj.resample("ME").last()
    mret = month_end.pct_change()
    past = [mret.shift(12 * k - 1) for k in range(1, 6)]
    total = sum(v.fillna(0.0) for v in past)
    count = sum(v.notna().astype(float) for v in past)
    season_m = (total / count).where(count >= 2)
    legs["season"] = season_m.reindex(adj.index, method="ffill")
    if chips:
        shares = chips["shares"].reindex(adj.index).ffill()
        legs["short_ratio"] = -(chips["short_bal"] / chips["margin_bal"].replace(0, np.nan)).reindex(adj.index)
        legs["short_flow"] = -(chips["short_bal"].reindex(adj.index).diff(20) * 1000 / shares)
        legs["trust_buy"] = chips["trust_net"].reindex(adj.index).fillna(0).rolling(20, min_periods=15).sum() / shares
        legs["foreign_chg"] = chips["foreign_ratio"].reindex(adj.index).diff(20)
    # 第 t 日只能用 t−1 日以前的資料
    return {k: v.shift(1) for k, v in legs.items()}


def wrap(raw: pd.DataFrame, member: pd.DataFrame, sector: pd.Series, smooth=True) -> pd.DataFrame:
    """產業內 z 分數（只在成員中）→ 20 日平均。"""
    x = raw.where(member)
    long = x.stack().rename("v").reset_index()
    long.columns = ["date", "ticker", "v"]
    long["sector"] = long["ticker"].map(sector)
    g = long.groupby(["date", "sector"])["v"]
    long["z"] = (long["v"] - g.transform("mean")) / g.transform("std")
    z = long.pivot(index="date", columns="ticker", values="z").reindex(index=raw.index, columns=raw.columns)
    return z.rolling(20, min_periods=10).mean().where(member) if smooth else z


def neutralize(score: pd.Series, sector: pd.Series, logcap: pd.Series) -> pd.Series:
    df = pd.DataFrame({"s": score, "sec": sector.reindex(score.index), "lc": logcap.reindex(score.index)}).dropna()
    if len(df) < 20:
        return pd.Series(dtype=float)
    X = pd.get_dummies(df["sec"], dtype=float)
    X["lc"] = df["lc"] - df["lc"].mean()
    beta, *_ = np.linalg.lstsq(X.to_numpy(), df["s"].to_numpy(), rcond=None)
    return pd.Series(df["s"].to_numpy() - X.to_numpy() @ beta, index=df.index)


# ---------------------------------------------------------------------------
# 組合與指標
# ---------------------------------------------------------------------------

def select(score: pd.Series, sector: pd.Series, q: float = Q) -> dict:
    s = score.dropna()
    sec = sector.reindex(s.index)
    w_sec = sec.value_counts(normalize=True)
    w = {}
    for name, idx in s.groupby(sec).groups.items():
        sub = s.loc[idx]
        if len(sub) < 3:
            for t in sub.index:
                w[t] = w_sec[name] / len(sub)
            continue
        top = sub[sub.rank(pct=True) > 1 - q]
        for t in top.index:
            w[t] = w_sec[name] / len(top)
    return w


def simulate(scores: dict, rets: pd.DataFrame, betas: pd.DataFrame, tx: pd.Series, schedule: list, sector: pd.Series, q: float = Q):
    """scores：{換倉日: 中性化分數}；回傳每日 DataFrame [alpha, long, beta, turnover]。"""
    rows, w_prev, b_prev = [], {}, 0.0
    days = rets.index
    for k, d in enumerate(schedule):
        nxt = schedule[k + 1] if k + 1 < len(schedule) else HOLDOUT
        w = select(scores[d], sector, q)
        tickers = list(w)
        wv = np.array([w[t] for t in tickers])
        b = float(np.nansum(wv * betas.loc[d, tickers].fillna(1.0).to_numpy())) if tickers else 0.0
        to = sum(abs(w.get(t, 0) - w_prev.get(t, 0)) for t in set(w) | set(w_prev))
        cost = to * STOCK_COST + abs(b - b_prev) * FUT_COST
        period = days[(days > d) & (days <= nxt)]
        R = rets.loc[period, tickers].fillna(0.0).to_numpy() if tickers else np.zeros((len(period), 0))
        long = R @ wv if tickers else np.zeros(len(period))
        alpha = long - b * tx.reindex(period).fillna(0.0).to_numpy()
        if len(period):
            alpha[0] -= cost
            long[0] -= to * STOCK_COST
        rows.append(pd.DataFrame({"alpha": alpha, "long": long, "beta": b, "turnover": 0.0}, index=period))
        rows[-1].iloc[0, rows[-1].columns.get_loc("turnover")] = to if len(period) else 0
        w_prev, b_prev = w, b
    return pd.concat(rows)


def sharpe(x: pd.Series) -> float:
    return float(x.mean() / x.std(ddof=1) * math.sqrt(252)) if len(x) > 20 and x.std(ddof=1) > 0 else float("nan")


def within_ic(score: pd.Series, fwd: pd.Series, sector: pd.Series) -> float:
    df = pd.DataFrame({"s": score, "f": fwd.reindex(score.index), "sec": sector.reindex(score.index)}).dropna()
    vals, w = [], []
    for _, g in df.groupby("sec"):
        if len(g) >= 3 and g["s"].nunique() > 1:
            vals.append(g["s"].rank().corr(g["f"].rank()))
            w.append(len(g))
    return float(np.average(vals, weights=w)) if vals else float("nan")


# ---------------------------------------------------------------------------
# 主程式
# ---------------------------------------------------------------------------

def prepare(top_n: int, membership=None) -> SimpleNamespace:
    """載入股票池前 N 名的價量、籌碼、SUE、β、台指期；只讀快取（缺的才呼叫 API）。"""
    membership = membership or str(ROOT / "config" / "universe_mcap_membership.csv")
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mem = pd.read_csv(membership, dtype={"stock_id": str})
    mem = mem[mem["rank"] <= top_n]
    ids = sorted(mem["stock_id"].unique())
    sector = mem.drop_duplicates("stock_id", keep="last").set_index("stock_id")["sector"]
    sector.index = sector.index + ".TW"

    adj, vol, money, chips_all = {}, {}, {}, {}
    for k, sid in enumerate(ids):
        s = load_stock(client, sid)
        if s is None:
            continue
        t = sid + ".TW"
        adj[t], vol[t], money[t] = s["adj"], s["volume"], s["money"]
        chips_all[t] = load_chips(client, sid)
        if k % 100 == 0:
            print(f"  載入 {k}/{len(ids)}", flush=True)
    adj, vol, money = pd.DataFrame(adj).sort_index(), pd.DataFrame(vol).sort_index(), pd.DataFrame(money).sort_index()
    mkt = market_tri(client)
    tx = tx_continuous(client)
    tickers = list(adj.columns)
    member = pd.DataFrame(False, index=adj.index, columns=tickers)
    for y, g in mem.groupby("year"):
        cols = [s + ".TW" for s in g["stock_id"] if s + ".TW" in member.columns]
        member.loc[member.index.year == y, cols] = True
    member &= adj.notna()

    # 各腿原始值（逐檔計算再組成矩陣）
    raws = {name: {} for name in LEGS_PRICE + LEGS_CHIP}
    shares = {}
    for t in tickers:
        ch = chips_all.get(t) or {}
        need = all(k in ch for k in ("short_bal", "margin_bal", "shares", "foreign_ratio", "trust_net"))
        legs = raw_legs(adj[[t]], vol[[t]], money[[t]], mkt, ch if need else None)
        for name, v in legs.items():
            raws[name][t] = v[t] if isinstance(v, pd.DataFrame) else v
        if "shares" in ch:
            shares[t] = ch["shares"]
    raws = {n: pd.DataFrame(v).reindex(index=adj.index, columns=tickers) for n, v in raws.items() if v}
    sh = pd.DataFrame(shares).reindex(index=adj.index, columns=tickers).ffill()
    raw_close = {}
    for sid in ids:
        px = client.get("TaiwanStockPrice", sid, PX_START)
        if not px.empty:
            px = px[px["close"].astype(float) > 0]
            raw_close[sid + ".TW"] = pd.Series(px["close"].astype(float).to_numpy(), index=pd.to_datetime(px["date"]))
    logcap = np.log((pd.DataFrame(raw_close).reindex(index=adj.index, columns=tickers) * sh).shift(1))

    rets = adj.pct_change()
    m = mkt.pct_change().reindex(rets.index)
    betas = rets.rolling(250, min_periods=120).cov(m).div(m.rolling(250, min_periods=120).var(), axis=0).shift(1)

    schedule = [d for d in event_dates(adj.index) if pd.Timestamp("2019-01-01") <= d < HOLDOUT]
    fwd20 = adj.shift(-20) / adj - 1

    # SUE（主腿）
    sue_rows = {}
    for t in tickers:
        rev = client.get("TaiwanStockMonthRevenue", t.split(".")[0], "2017-01-01")
        if not rev.empty:
            s = revenue_surprise(rev).set_index("avail_month")["sue"]
            sue_rows[t] = s
    sue = pd.DataFrame(sue_rows)

    return SimpleNamespace(client=client, mem=mem, ids=ids, sector=sector, adj=adj, money=money.reindex(columns=tickers), tickers=tickers, member=member,
                           raws=raws, logcap=logcap, rets=rets, betas=betas, tx=tx, schedule=schedule, fwd20=fwd20, sue=sue)


def leg_scores(c: SimpleNamespace, name: str) -> dict:
    """{換倉日: 包裝後並對產業與 log 市值中性化的分數}。"""
    if name == "sue":
        scores = {}
        for d in c.schedule:
            mo = d.to_period("M").to_timestamp()
            v = c.sue.loc[mo] if mo in c.sue.index else pd.Series(dtype=float)
            v = v.reindex(c.tickers).where(c.member.loc[d])
            z = v.groupby(c.sector.reindex(v.index)).transform(lambda x: (x - x.mean()) / x.std())
            scores[d] = neutralize(z, c.sector, c.logcap.loc[d])
        return scores
    wz = wrap(c.raws[name], c.member, c.sector)
    return {d: neutralize(wz.loc[d], c.sector, c.logcap.loc[d]) for d in c.schedule}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("top_n", type=int)
    ap.add_argument("--membership", default=str(ROOT / "config" / "universe_mcap_membership.csv"))
    args = ap.parse_args(argv)
    c = prepare(args.top_n, args.membership)
    client, sector, tickers, member, raws = c.client, c.sector, c.tickers, c.member, c.raws
    rets, betas, tx, schedule, fwd20 = c.rets, c.betas, c.tx, c.schedule, c.fwd20

    # 股票池基準（看完第一版結果後加的診斷）：同樣產業權重、產業內持有全部成員，同樣 β 對沖。
    # 腿的「超額」= 腿的純 alpha − 基準的純 alpha，只留下選股本身的貢獻（去掉等權 vs 市值加權指數的結構差）。
    base_scores = {d: pd.Series(1.0, index=member.columns[member.loc[d]]) for d in schedule}
    base = simulate(base_scores, rets, betas, tx, schedule, sector, q=1.0)["alpha"]

    results, pnl = [], {}
    leg_names = ["sue"] + [n for n in LEGS_PRICE + LEGS_CHIP if n in raws]
    for name in leg_names:
        scores = leg_scores(c, name)
        sim = simulate(scores, rets, betas, tx, schedule, sector)
        pnl[name] = sim["alpha"]
        ics = pd.Series({d: within_ic(scores[d], fwd20.loc[d], sector) for d in schedule})
        row = {"leg": name}
        for seg, mask in (("oos", sim.index < SPLIT), ("is", sim.index >= SPLIT)):
            row[f"sh_{seg}"] = sharpe(sim.loc[mask, "alpha"])
            row[f"ex_{seg}"] = sharpe((sim["alpha"] - base.reindex(sim.index))[mask])
            icm = ics[(ics.index < SPLIT) if seg == "oos" else (ics.index >= SPLIT)].dropna()
            row[f"ic_{seg}"] = icm.mean()
            row[f"ict_{seg}"] = icm.mean() / (icm.std(ddof=1) / math.sqrt(len(icm))) if len(icm) > 2 else float("nan")
        row["yearly"] = {int(y): round(sharpe(g), 2) for y, g in sim["alpha"].groupby(sim.index.year)}
        row["turnover_yr"] = sim["turnover"].sum() / (len(sim) / 252)
        row["beta"] = sim["beta"].mean()
        results.append(row)
        print(f"  {name}: Sharpe {row['sh_oos']:.2f} / {row['sh_is']:.2f}；超額 {row['ex_oos']:.2f} / {row['ex_is']:.2f}；"
              f"IC {row['ic_oos']:+.3f} / {row['ic_is']:+.3f}", flush=True)

    P = pd.DataFrame(pnl)
    P["universe"] = base.reindex(P.index)   # 基準欄；leg_enumerate.py 用來算超額，不當成腿
    out_dir = ROOT / "reports" / "legs"
    out_dir.mkdir(parents=True, exist_ok=True)
    P.to_csv(out_dir / f"pnl_top{args.top_n}.csv")
    corr = P.drop(columns="universe").corr()
    b0050 = None
    try:
        from data.fetch_financials import get_total_return_prices

        e = get_total_return_prices(client, "0050.TW", "2019-01-01", "2026-05-31").set_index("date")["adj_close"]
        b0050 = e.pct_change().reindex(P.index)
    except Exception:  # noqa: BLE001
        pass
    lines = [f"# 單腿探針：全市場市值前 {args.top_n} 檔（自動產生）", "",
             "由 [analysis/leg_probe.py](../analysis/leg_probe.py) 產生。純 alpha = 產業中性做多（前 1/3）減去 β × 台指期報酬，扣股票與期貨成本；"
             "Sharpe 為年化（無風險利率 0）；產業內 IC 為同產業內訊號排名與之後 20 日報酬排名的相關係數（−1～1）。"
             f"換倉日 {len(schedule)} 個（{schedule[0]:%Y-%m} ~ {schedule[-1]:%Y-%m}），2026-05 之後保留給前瞻驗證。", "",
             f"股票池基準（產業內持有全部成員、同樣對沖）純 alpha Sharpe：2019–2022 {sharpe(base[base.index < SPLIT]):.2f}、"
             f"2023–2026/04 {sharpe(base[base.index >= SPLIT]):.2f}；逐年 "
             + "、".join(f"{y}:{sharpe(g):+.1f}" for y, g in base.groupby(base.index.year))
             + "。「超額」= 腿的純 alpha 減去此基準的每日報酬後的年化 Sharpe，只衡量選股（看完第一版結果後加的診斷欄）。", "",
             "| 腿 | 純 alpha Sharpe 2019–2022 | 2023–2026/04 | 超額 Sharpe 2019–2022 | 2023–2026/04 | 產業內 IC 2019–2022（t） | 2023–2026（t） | 年換手 | 平均 β | 與 0050 相關 | 逐年 Sharpe |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        c0050 = P[r["leg"]].corr(b0050) if b0050 is not None else float("nan")
        yearly = "、".join(f"{y}:{v:+.1f}" for y, v in r["yearly"].items())
        lines.append(f"| {r['leg']} | {r['sh_oos']:.2f} | {r['sh_is']:.2f} | {r['ex_oos']:.2f} | {r['ex_is']:.2f} | "
                     f"{r['ic_oos']:+.3f}（{r['ict_oos']:+.1f}） | "
                     f"{r['ic_is']:+.3f}（{r['ict_is']:+.1f}） | {r['turnover_yr']:.1f} | {r['beta']:.2f} | {c0050:+.2f} | {yearly} |")
    names = list(corr.columns)
    lines += ["", "## 腿與腿之間的每日純 alpha 報酬相關", "", "| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    lines += [f"| {a} | " + " | ".join(f"{corr.at[a, b]:+.2f}" for b in names) + " |" for a in names]
    (ROOT / "docs" / f"leg_probe_top{args.top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
