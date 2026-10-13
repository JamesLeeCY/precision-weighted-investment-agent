"""等權多空的可借量檢查與回測（月營收驚奇；全市場市值前 N 檔）。

用法（於專案根目錄；先執行 fetch_short_balances.py）：
    .venv/Scripts/python analysis/borrow_capacity.py 300
輸出 docs/borrow_capacity_top{N}.md 與 reports/legs/borrow_ls_top{N}.csv。

設計（看結果前固定）：
- 放空名單：產業內月營收驚奇後 1/3（成員 ≥ 3 檔的產業），產業內等權，產業權重 = 檔數占比；多空各 100%。
  做多端為產業內前 1/3、同樣等權（對應 docs/leg_pool_report.md 中 1.24 / 1.73 的超額診斷）。
- 資金規模 K = 新台幣 1,000 萬、5,000 萬、2 億、10 億；每檔需借股數 = K × 放空權重 ÷ 換倉日收盤價。
- 可借條件（皆只用換倉日前一日以前的資料）：
  A 前 60 個交易日有借券成交；
  B 需借股數 ≤ 前一日借券賣出可用額度（TaiwanDailyShortSaleBalances.SBLShortSalesQuota，股）；
  C 需借股數 ≤ 前 60 日借券成交量（張 × 1000）的 10%（市場深度代理，假設）；
  D = A 且 B 且 C 且 60 日成交量加權借券費率 ≤ 5%／年。
  以放空權重加權計算可覆蓋比例；另依市值三分位（股票池內）與兩段期間分列。融券（信用交易）每年有股東會與除權息強制回補，不列入可借量。
- 回測：等權多空，放空只用條件 D 通過的股票（K = 1,000 萬與 2 億兩種）；某產業沒有可放空的股票時該產業兩邊都不做；
  借券費逐日扣（費率同 hedge_construction.lending_fees），換手兩邊 × 0.29625%，剩餘 β 以台指期對沖。
  對照：不限制可借（只要求 A）；做多 − β × 台指期；1.24 / 1.73 的超額診斷。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402

Q = 1 / 3
CAPITALS = {"1,000 萬": 1e7, "5,000 萬": 5e7, "2 億": 2e8, "10 億": 1e9}
DEPTH_FRAC, FEE_MAX = 0.10, 5.0


def ew_long_short(score: pd.Series, sector: pd.Series, shortable: pd.Series | None = None, q: float = Q) -> pd.Series:
    """多：產業內前 q 等權；空：產業內後 q（可放空者）等權；產業權重 = 參與產業的檔數占比；多空各 100%。"""
    s = score.dropna()
    sec = sector.reindex(s.index)
    parts = {}
    for name, idx in s.groupby(sec).groups.items():
        sub = s.loc[idx]
        if len(sub) < 3:
            continue
        r = sub.rank(pct=True)
        top, bot = sub[r > 1 - q].index, sub[r <= q].index
        if shortable is not None:
            bot = bot[shortable.reindex(bot).fillna(False).to_numpy(bool)]
        if len(top) and len(bot):
            parts[name] = (top, bot, len(sub))
    if not parts:
        return pd.Series(dtype=float)
    total = sum(v[2] for v in parts.values())
    out = []
    for top, bot, n in parts.values():
        out.append(pd.Series(n / total / len(top), index=top))
        out.append(pd.Series(-n / total / len(bot), index=bot))
    return pd.concat(out)


def load_short_data(client, tickers, index):
    quota, lend = {}, {}
    for t in tickers:
        sid = t.split(".")[0]
        d = client.get("TaiwanDailyShortSaleBalances", sid, "2018-06-01", "2026-05-31")
        if not d.empty:
            quota[t] = pd.Series(d["SBLShortSalesQuota"].astype(float).to_numpy(), index=pd.to_datetime(d["date"]))
        ld = client.get("TaiwanStockSecuritiesLending", sid, lp.EV_START, lp.EV_END)
        if not ld.empty:
            lend[t] = ld.assign(date=pd.to_datetime(ld["date"])).groupby("date")["volume"].sum().astype(float) * 1000
    Qd = pd.DataFrame(quota).reindex(index=index, columns=tickers).ffill().shift(1)
    L = pd.DataFrame(lend).reindex(index=index, columns=tickers).fillna(0.0)
    lend60 = L.rolling(60, min_periods=1).sum().shift(1)
    return Qd, lend60


def raw_close(c) -> pd.DataFrame:
    """未還原收盤價（算需借股數用）。"""
    out = {}
    for sid in c.ids:
        px = c.client.get("TaiwanStockPrice", sid, lp.PX_START)
        if not px.empty:
            px = px[px["close"].astype(float) > 0]
            out[sid + ".TW"] = pd.Series(px["close"].astype(float).to_numpy(), index=pd.to_datetime(px["date"]))
    return pd.DataFrame(out).reindex(index=c.adj.index, columns=c.tickers)


def main(top_n: int):
    c = lp.prepare(top_n)
    scores = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
    quota, lend60 = load_short_data(c.client, c.tickers, c.adj.index)
    close = raw_close(c)
    size_pct = np.exp(c.logcap).where(c.member).rank(axis=1, pct=True)

    # ---- 可借量檢查 ----
    rec = []
    for d in c.schedule:
        w = ew_long_short(scores[d], c.sector)
        sh = -w[w < 0]
        if sh.empty:
            continue
        for t, wt in sh.items():
            a = lend60.at[d, t] > 0
            f = fee.at[d, t]
            row = {"date": d, "t": t, "w": wt, "A": bool(a), "fee": f, "size": size_pct.at[d, t]}
            for k, K in CAPITALS.items():
                need = K * wt / close.at[d, t] if close.at[d, t] > 0 else np.inf
                b = quota.at[d, t] >= need if quota.at[d, t] == quota.at[d, t] else False
                cc = need <= DEPTH_FRAC * lend60.at[d, t]
                row[f"B_{k}"], row[f"C_{k}"] = bool(b), bool(cc)
                row[f"D_{k}"] = bool(a and b and cc and f == f and f <= FEE_MAX)
            rec.append(row)
    R = pd.DataFrame(rec)
    R["bucket"] = pd.cut(R["size"], [0, 1 / 3, 2 / 3, 1.0001], labels=["小型（後 1/3）", "中型", "大型（前 1/3）"])
    R["seg"] = np.where(R["date"] < lp.SPLIT, "2019–2022", "2023–2026/04")

    def cov(df, col):
        return float((df["w"] * df[col]).sum() / df["w"].sum())

    lines = [f"# 等權多空：可借量檢查與回測（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/borrow_capacity.py](../analysis/borrow_capacity.py) 產生；設計見程式開頭。"
             "覆蓋比例 = 通過條件的放空部位占全部放空部位的權重比例（0–100%）。研究結果，非投資建議。", "",
             f"放空名單：{len(c.schedule)} 個換倉日、共 {len(R)} 筆放空部位（平均每期 {len(R) / len(c.schedule):.0f} 檔）。", "",
             "## 1. 有沒有借券成交、借券費（與資金規模無關）", "",
             "| 分組 | 放空部位占比 | A 前 60 日有借券成交 | 借券費中位數（年化） | 費率 > 5% 占比 | 費率 > 10% 占比 |",
             "|---|---|---|---|---|---|"]
    for name, g in [("全部", R)] + [(str(b), R[R["bucket"] == b]) for b in R["bucket"].cat.categories] + [(s, R[R["seg"] == s]) for s in ("2019–2022", "2023–2026/04")]:
        fw = g.dropna(subset=["fee"])
        lines.append(f"| {name} | {g['w'].sum() / R['w'].sum():.0%} | {cov(g, 'A'):.0%} | {fw['fee'].median():.2f}% | "
                     f"{cov(fw.assign(x=fw['fee'] > 5), 'x'):.0%} | {cov(fw.assign(x=fw['fee'] > 10), 'x'):.0%} |")
    lines += ["", "## 2. 依資金規模：可覆蓋比例", "",
              "| 資金規模 | 分組 | B 借券賣出額度足夠 | C 不超過 60 日借券量 10% | D 全部條件（含費率 ≤ 5%） |", "|---|---|---|---|---|"]
    for k in CAPITALS:
        for name, g in [("全部", R)] + [(str(b), R[R["bucket"] == b]) for b in R["bucket"].cat.categories]:
            lines.append(f"| {k} | {name} | {cov(g, f'B_{k}'):.0%} | {cov(g, f'C_{k}'):.0%} | {cov(g, f'D_{k}'):.0%} |")
    for k in CAPITALS:
        by = R.groupby("seg").apply(lambda g: cov(g, f"D_{k}"))
        lines.append(f"| {k} | 分期 D：2019–2022 {by.get('2019–2022', float('nan')):.0%}、2023–2026/04 {by.get('2023–2026/04', float('nan')):.0%} | | | |")

    # ---- 回測 ----
    ok = {k: R.pivot_table(index="date", columns="t", values=f"D_{k}", aggfunc="first") for k in ("1,000 萬", "2 億")}
    anyA = R.pivot_table(index="date", columns="t", values="A", aggfunc="first")
    sched = c.schedule
    versions = {}

    def run(name, shortable_fn):
        wd = {}
        for d in sched:
            s = shortable_fn(d)
            wd[d] = ew_long_short(scores[d], c.sector, s)
        sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, sched, fee=fee)
        versions[name] = (sim, hc.stats(sim["ret"], sim))

    def lookup(tbl):
        def f(d):
            if d not in tbl.index:
                return pd.Series(dtype=bool)
            return tbl.loc[d].dropna().astype(bool)
        return f

    # 名單外（做多端）的股票不會被放空，shortable 只需涵蓋後 1/3
    run("不限制可借量（只要求前 60 日有借券成交）", lookup(anyA))
    run("限制可借：資金 1,000 萬（條件 D）", lookup(ok["1,000 萬"]))
    run("限制可借：資金 2 億（條件 D）", lookup(ok["2 億"]))
    long_only = lp.simulate(scores, c.rets, c.betas, c.tx, sched, c.sector)
    pd.DataFrame({k: v[0]["ret"] for k, v in versions.items()} | {"做多 − β × 台指期": long_only["alpha"]}).to_csv(
        ROOT / "reports" / "legs" / f"borrow_ls_top{top_n}.csv")
    lo = hc.stats(long_only["alpha"])
    lines += ["", "## 3. 等權多空回測（月營收驚奇，剩餘 β 以台指期對沖，扣交易成本與借券費）", "",
              "| 版本 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 年化波動 | 最大回撤 | 年換手（倍） | 借券成本／年 |", "|---|---|---|---|---|---|---|---|"]
    for name, (sim, s) in versions.items():
        lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} | "
                     f"{s['turnover']:.1f} | {s['borrow']:.2%} |")
    lines.append(f"| 對照：做多 − β × 台指期 | {lo['sh_oos']:.2f} | {lo['sh_is']:.2f} | {lo['ann']:+.1%} | {lo['vol']:.1%} | {lo['mdd']:.1%} | — | — |")
    lines.append("| 對照：做多 − 股票池基準（不可交易的診斷） | 1.24 | 1.73 | +4.6% | — | — | — | — |")
    lines += ["", "逐年 Sharpe：", ""]
    for name, (sim, s) in versions.items():
        lines.append(f"- {name}：" + "、".join(f"{y}:{v:+.1f}" for y, v in s["yearly"].items() if v == v))
    (ROOT / "docs" / f"borrow_capacity_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
