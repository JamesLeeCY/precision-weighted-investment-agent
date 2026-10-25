"""I051 fv5 家族的合併規格 fv5x 與前瞻採用規則的檢定力分析（點子卡 research/ideas/I051-fv5-family-combined-spec-decision-rule.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/fv5_family.py
輸出 docs/fv5_family.md。

設計（依點子卡；補充以「補」標示）：
- 基準 fv5：前 500 名、SUE 分數（leg_probe.leg_scores）產業內前／後 1/3 等權、條件 D、三份錯開、每 3 個換倉日換倉、台指期對沖、單邊 0.29625% + 借券費。
- 三項修改（沿用各自回測的寫法）：
  E（fv5e）：金融股若 45 個交易日內有已知 ESUE，以 ESUE 在這些金融股間的百分位取全體分數同分位數值取代（analysis/fv5_fin_esue.py）。
  S（fv5s）：分數 = 0.75 × 分數產業內百分位 + 0.25 × S1 產業內百分位（S1 缺值 0.5；analysis/ts_rank_validate.py）。
  V（fv5v）：名單決定後各腿改 1/σ 權重（60 日，單檔 1/3 ~ 3 倍等權），放空端重查條件 D、剔除後重新正規化（analysis/fv5_invvol.py）。
  合併順序 E → S → 名單 → V。fv5x = E + S + V。
- 回測判定：(1) fv5x 全期 Sharpe > 1.78；(2) 兩段都不低於 fv5；(3) 三項的邊際貢獻（fv5x 全期 Sharpe − 拿掉該項）都 ≥ 0。全部成立才另立 fv5x 前瞻。
  另報告 4 個兩兩組合與資金四等分（fv5、fv5e、fv5s、fv5v 日報酬平均）。
- 檢定力：以回測每個換倉段（相鄰換倉日之間，約一個月）的報酬差 d_k = 規格 k − fv5 的平均 μ 與標準差 σ，
  單尾 t > 2 的檢定力 ≈ 1 − Φ(2 − μ/σ × √n)（補：常態近似），報告 n = 24、48、72 與達 80%、50% 所需期數。
研究結果，非投資建議。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import borrow_capacity as bc  # noqa: E402
import fv5_invvol as iv  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import self_earnings_events as see  # noqa: E402
import ts_rank_chips as trc  # noqa: E402

LOOKBACK = 45
LAST: dict = {}


def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def run_backtests(membership: str | None = None, shadow: bool = False, extra_cost: float = 0.0):
    """回傳（各規格日淨報酬 dict、換倉日）。shadow=True（I057 影子規格）：不限制可借、借券費一律 2%／年、
    交易成本單邊另加 extra_cost；membership 可指向名次重編的股票池檔（例如第 501–1000 名改為 1–500）。"""
    c = lp.prepare(500, membership)
    days, sched, sector = c.adj.index, c.schedule, c.sector
    sue = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, days)
    if shadow:
        fee = pd.DataFrame(2.0, index=fee.index, columns=fee.columns)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    close = bc.raw_close(c)
    vol = c.rets.rolling(60, min_periods=40).std().shift(1)
    # E
    e = see.esue_table(c.client)
    e["ticker"] = e["stock_id"] + ".TW"
    e = e[e["ticker"].isin(c.tickers)].copy()
    e["k0"] = [int(days.searchsorted(d)) for d in e["date"]]
    fin = set(t for t in c.tickers if c.sector.get(t) in see.FIN)
    # S1
    X, _ = trc.raw_fields(c)
    ts1 = trc.ts_rank(X["x1"]).where(X["x1"].rolling(250, min_periods=120).max() > 0)
    mwz = lp.wrap((-ts1.shift(1)).replace([np.inf, -np.inf], np.nan), c.member, c.sector)
    s1 = {d: lp.neutralize(mwz.loc[d], c.sector, c.logcap.loc[d]) for d in sched}

    def shortable_at(d):
        if shadow:
            return pd.Series(True, index=c.tickers)
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    def score(d, use_e, use_s):
        s = sue[d].copy()
        if use_e:
            kd = int(days.searchsorted(d))
            g = e[(e["k0"] + 1 <= kd) & (kd - e["k0"] <= LOOKBACK) & e["ticker"].isin(fin)]
            g = g.sort_values("k0").drop_duplicates("ticker", keep="last")
            g = g[[bool(c.member.at[d, t]) for t in g["ticker"]] & g["ticker"].isin(s.index).to_numpy()]   # 沒有 SUE 分數者不替換（影子樣本才會發生）
            base = s.dropna()
            if len(g) >= 2 and len(base):
                s.loc[g["ticker"].to_numpy()] = np.nanquantile(base.to_numpy(), g["esue"].rank(pct=True).to_numpy())
        if use_s:
            s = s.dropna()
            grp = sector.reindex(s.index)
            s = 0.75 * s.groupby(grp).rank(pct=True) + 0.25 * s1[d].reindex(s.index).groupby(grp).rank(pct=True).fillna(0.5)
        return s

    def invvol(d, w):
        out = []
        for sign in (1, -1):
            x = w[w * sign > 0].abs()
            if not len(x):
                continue
            sd = vol.loc[d].reindex(x.index)
            sd = sd.fillna(sd.median())
            nw = iv.capped(1 / sd, float(x.sum()))
            if sign < 0 and not shadow:
                need = lt.K_CAPITAL * nw / close.loc[d].reindex(nw.index)
                ok = (lend60.loc[d].reindex(nw.index) > 0) & (quota.loc[d].reindex(nw.index) >= need) \
                    & (need <= bc.DEPTH_FRAC * lend60.loc[d].reindex(nw.index)) & (fee.loc[d].reindex(nw.index) <= bc.FEE_MAX)
                nw = nw[ok.to_numpy(bool)]
                nw = nw / nw.sum() * float(x.sum()) if len(nw) else nw
            out.append(nw * sign)
        return pd.concat(out)

    def book(use_e, use_s, use_v):
        parts = []
        LAST.setdefault("wd", {})[(use_e, use_s, use_v)] = []
        for off in range(3):
            wd = {}
            for d in sched[off::3]:
                w = lt.ew_ls_buffer(score(d, use_e, use_s), sector, shortable_at(d), q_keep=None)
                wd[d] = invvol(d, w) if use_v else w
            LAST["wd"][(use_e, use_s, use_v)].append(wd)
            sc0 = lp.STOCK_COST
            lp.STOCK_COST = sc0 + extra_cost
            try:
                parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)["ret"])
            finally:
                lp.STOCK_COST = sc0
        x = pd.concat(parts, axis=1).mean(axis=1)
        return x[x.index > sched[2]]

    specs = {"fv5": (0, 0, 0), "fv5e": (1, 0, 0), "fv5s": (0, 1, 0), "fv5v": (0, 0, 1),
             "E+S": (1, 1, 0), "E+V": (1, 0, 1), "S+V": (0, 1, 1), "fv5x（E+S+V）": (1, 1, 1)}
    R = {}
    for k, f in specs.items():
        R[k] = book(*map(bool, f))
        print(k, flush=True)
    R["資金四等分（fv5、fv5e、fv5s、fv5v）"] = pd.concat([R["fv5"], R["fv5e"], R["fv5s"], R["fv5v"]], axis=1).mean(axis=1)
    LAST.update(c=c, sue=sue, s1=s1, e=e, fin=fin)     # 供其他分析重用（analysis/fv5_mechanism_power.py）
    return R, sched


def main():
    R, sched = run_backtests()
    st = {k: hc.stats(x) | {"full": lp.sharpe(x.dropna())} for k, x in R.items()}
    b, x = st["fv5"], st["fv5x（E+S+V）"]
    marg = {"E": x["full"] - st["S+V"]["full"], "S": x["full"] - st["E+V"]["full"], "V": x["full"] - st["E+S"]["full"]}
    c1 = x["full"] > 1.78
    c2 = x["sh_oos"] >= b["sh_oos"] and x["sh_is"] >= b["sh_is"]
    c3 = all(v >= 0 for v in marg.values())
    # 檢定力
    seg_id = pd.Series(np.searchsorted(np.array(sched), R["fv5"].index, side="right"), index=R["fv5"].index)
    seg_ret = {k: (1 + v).groupby(seg_id.reindex(v.index)).prod() - 1 for k, v in R.items()}
    power = {}
    for k in ("fv5e", "fv5s", "fv5v", "fv5x（E+S+V）"):
        d = (seg_ret[k] - seg_ret["fv5"]).dropna()
        mu, sd = float(d.mean()), float(d.std(ddof=1))
        es = mu / sd if sd > 0 else float("nan")
        pw = {n: 1 - phi(2 - es * math.sqrt(n)) for n in (24, 48, 72)}
        need = lambda p: (math.ceil(((2 + {0.8: 0.8416, 0.5: 0.0}[p]) / es) ** 2) if es > 0 else None)  # noqa: E731
        power[k] = (mu, sd, len(d), pw, need(0.8), need(0.5))
    L = ["# I051 fv5 家族合併規格與前瞻檢定力（自動產生）", "",
         "由 [analysis/fv5_family.py](../analysis/fv5_family.py) 產生；設計見程式開頭（看結果前固定）。"
         "E = 金融股改用自結盈餘驚奇（fv5e）、S = 加入借券餘額 ts_rank（fv5s）、V = 逆標準差權重（fv5v）。"
         "Sharpe 為扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後，格式 2019–2022 / 2023–2026/04。研究結果，非投資建議。", "",
         "| 規格 | Sharpe | 全期 | 年化報酬 | 年化波動 | 最大回撤 |", "|---|---|---|---|---|---|"]
    for k, s in st.items():
        L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} |")
    L += ["", "邊際貢獻（fv5x 全期 Sharpe − 拿掉該項）：" + "、".join(f"{k} {v:+.2f}" for k, v in marg.items()), "",
          "## 判定（是否另立 fv5x 前瞻）", "",
          f"1. fv5x 全期 Sharpe > 1.78：{x['full']:.2f} → {'✓' if c1 else '✗'}",
          f"2. 兩段不低於 fv5：{x['sh_oos']:.2f} / {x['sh_is']:.2f} vs {b['sh_oos']:.2f} / {b['sh_is']:.2f} → {'✓' if c2 else '✗'}",
          f"3. 三項邊際貢獻皆 ≥ 0 → {'✓' if c3 else '✗'}", "",
          f"**結論：{'通過，另立 fv5x 平行前瞻' if c1 and c2 and c3 else '未通過，不另立 fv5x'}**", "",
          "## 檢定力分析（每個換倉段約一個月；d = 規格 − fv5 的段報酬差）", "",
          "| 規格 | 每段平均差 | 標準差 | 回測段數 | 24 期檢定力 | 48 期 | 72 期 | 80% 檢定力所需期數 | 50% 所需期數 |", "|---|---|---|---|---|---|---|---|---|"]
    for k, (mu, sd, n, pw, n80, n50) in power.items():
        L.append(f"| {k} | {mu:+.3%} | {sd:.3%} | {n} | {pw[24]:.0%} | {pw[48]:.0%} | {pw[72]:.0%} | {n80 if n80 else '—'} | {n50 if n50 else '—'} |")
    (ROOT / "docs" / "fv5_family.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
