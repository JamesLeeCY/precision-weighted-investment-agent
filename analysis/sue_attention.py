"""I004 月營收驚奇 × 低法人關注（點子卡 research/ideas/I004-sue-x-low-attention.md 的檢定計畫，看結果前固定）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/sue_attention.py
輸出 docs/sue_attention.md 與 reports/legs/sue_attention.csv。

- SUE 分數：leg_probe.leg_scores(c, "sue")，不改定義。
- 關注度（換倉日 d，只用 d−1 以前）：ATT = 產業內百分位平均（外資持股比例水準、前 60 日三大法人成交占比
  = Σ(各法人買 + 賣) ÷ (2 × 成交股數)），再對產業虛擬變數與 log 市值取殘差 → ATT_res（同市值下的法人關注）。
- 檢定一：每期每個產業內依 ATT_res 中位數分低／高兩半，各算 SUE 的產業內 IC（fwd20／40／60）；差額 = 低 − 高，
  Newey-West t（lag 0／1／2）。
- 檢定二：Fama-MacBeth，應變數 = 產業內 fwd20 報酬百分位，自變數 = SUE、ATT_res、SUE × ATT_res（皆產業內標準化、產業內去均值），
  看交互項（預期為負）。
- 檢定三：fv3 建構（每 3 個月、三份錯開取平均、緩衝 1/2、可借條件 D、資金 2 億、台指期對沖、扣成本與借券費），
  入選股權重 × (1 + 0.5 × ATT_low)，ATT_low = 1 − 2 × 產業內 ATT_res 百分位（低關注 = +1），產業內多、空各自重新正規化。
- 另報告：ATT_res 與 foreign_chg、trust_buy 的橫斷面相關；ATT_res 單獨當腿（做多低關注）的多空 Sharpe；
  低／高兩半各自的 SUE 多空 Sharpe；放空端可借覆蓋率（以放空權重加權）；進場日漲停比例。
- 通過（全部成立）：(1) 前 300 名 fwd20 IC 差兩段 > 0、合併 t > 2；(2) 前 500 名同號；(3) 交互項兩段皆 < 0；
  (4) 傾斜版兩段 Sharpe 都高於 fv3 建構，且放空覆蓋率 ≥ fv3 的 90%。(1)–(3) 成立而 (4) 不成立記為 partial。
研究結果，非投資建議。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import borrow_capacity as bc  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402

TILT = 0.5
HORIZONS = {"fwd20": (20, 0), "fwd40": (40, 1), "fwd60": (60, 2)}


def spearman(a: pd.Series, b: pd.Series) -> float:
    """Spearman 相關（排名後的 Pearson；不需 scipy）。"""
    df = pd.concat([a, b], axis=1).dropna()
    return float(df.iloc[:, 0].rank().corr(df.iloc[:, 1].rank())) if len(df) > 2 else float("nan")


def nw_t(x: pd.Series, lags: int) -> float:
    x = x.dropna()
    n = len(x)
    if n < 5:
        return float("nan")
    e = x - x.mean()
    var = (e ** 2).sum() / n
    for k in range(1, lags + 1):
        var += 2 * (1 - k / (lags + 1)) * (e.iloc[k:].to_numpy() * e.iloc[:-k].to_numpy()).sum() / n
    return float(x.mean() / math.sqrt(var / n)) if var > 0 else float("nan")


def sector_pct(v: pd.Series, sector: pd.Series) -> pd.Series:
    v = v.dropna()
    return v.groupby(sector.reindex(v.index)).rank(pct=True)


def attention_raw(c) -> tuple[pd.DataFrame, pd.DataFrame]:
    """（外資持股比例, 前 60 日三大法人成交占比），皆 shift 1（只用前一日以前）。"""
    fr, part = {}, {}
    for t in c.tickers:
        sid = t.split(".")[0]
        sh = c.client.get("TaiwanStockShareholding", sid, lp.EV_START, lp.EV_END)
        if not sh.empty:
            fr[t] = pd.Series(sh["ForeignInvestmentSharesRatio"].astype(float).to_numpy(), index=pd.to_datetime(sh["date"]))
        ii = c.client.get("TaiwanStockInstitutionalInvestorsBuySell", sid, lp.EV_START, lp.EV_END)
        px = c.client.get("TaiwanStockPrice", sid, lp.PX_START)
        if not ii.empty and not px.empty:
            inst = (ii["buy"].astype(float) + ii["sell"].astype(float)).groupby(pd.to_datetime(ii["date"])).sum()
            vol = pd.Series(px["Trading_Volume"].astype(float).to_numpy(), index=pd.to_datetime(px["date"]))
            inst = inst.reindex(vol.index).fillna(0.0)
            part[t] = inst.rolling(60, min_periods=40).sum() / (2 * vol.rolling(60, min_periods=40).sum().replace(0, np.nan))
    idx = c.adj.index
    F = pd.DataFrame(fr).reindex(index=idx, columns=c.tickers).ffill().shift(1)
    P = pd.DataFrame(part).reindex(index=idx, columns=c.tickers).shift(1)
    return F, P


def att_res_at(c, F, P, d) -> pd.Series:
    mem = c.member.loc[d]
    f, p = F.loc[d].where(mem), P.loc[d].where(mem)
    att = pd.concat([sector_pct(f, c.sector), sector_pct(p, c.sector)], axis=1).mean(axis=1, skipna=False)
    return lp.neutralize(att, c.sector, c.logcap.loc[d])


def tilt_weights(w: pd.Series, att: pd.Series, sector: pd.Series, k: float = TILT) -> pd.Series:
    """入選股權重 × (1 + k × ATT_low)，產業內多、空各自重新正規化（產業總權重不變）。"""
    if w.empty:
        return w
    low = 1 - 2 * sector_pct(att, sector)                              # 低關注 = +1，高關注 = −1
    out = []
    for _, g in w.groupby(sector.reindex(w.index)):
        for side in (g[g > 0], g[g < 0]):
            if side.empty:
                continue
            m = 1 + k * low.reindex(side.index).fillna(0.0)
            nw = side * m
            out.append(nw * (side.sum() / nw.sum()))
    return pd.concat(out)


def fm_interaction(score: pd.Series, att: pd.Series, fwd: pd.Series, sector: pd.Series) -> float:
    df = pd.DataFrame({"s": score, "a": att, "f": fwd.reindex(score.index)}).dropna()
    df["sec"] = sector.reindex(df.index)
    df = df.groupby("sec").filter(lambda g: len(g) >= 4)
    if len(df) < 30:
        return float("nan")
    g = df.groupby("sec")
    z = lambda col: (df[col] - g[col].transform("mean")) / g[col].transform("std")  # noqa: E731
    y = df["f"].groupby(df["sec"]).rank(pct=True)
    y = y - y.groupby(df["sec"]).transform("mean")
    s, a = z("s"), z("a")
    X = pd.concat([s, a, s * a], axis=1).fillna(0.0)
    X = X - X.groupby(df["sec"]).transform("mean")
    beta, *_ = np.linalg.lstsq(X.to_numpy(), y.to_numpy(), rcond=None)
    return float(beta[2])


def analyse(top_n: int) -> dict:
    c = lp.prepare(top_n)
    scores = lp.leg_scores(c, "sue")
    sched = c.schedule
    F, P = attention_raw(c)
    att = {d: att_res_at(c, F, P, d) for d in sched}
    fwd = {h: c.adj.shift(-n) / c.adj - 1 for h, (n, _) in HORIZONS.items()}

    # 與已失敗腿的區隔
    corr = {}
    for leg in ("foreign_chg", "trust_buy"):
        wz = lp.wrap(c.raws[leg], c.member, c.sector)
        corr[leg] = float(np.nanmean([spearman(att[d], wz.loc[d].reindex(att[d].index)) for d in sched]))

    # 檢定一：低／高兩半的 IC
    ic = {h: {"low": {}, "high": {}} for h in HORIZONS}
    for d in sched:
        a, s = att[d], scores[d]
        common = a.index.intersection(s.dropna().index)
        if len(common) < 30:
            continue
        a = a.loc[common]
        med = a.groupby(c.sector.reindex(common)).transform("median")
        for half, idx in (("low", common[(a <= med).to_numpy()]), ("high", common[(a > med).to_numpy()])):
            for h in HORIZONS:
                ic[h][half][d] = lp.within_ic(s.loc[idx], fwd[h].loc[d], c.sector)
    ic_tab = {}
    for h, (_, lag) in HORIZONS.items():
        lo, hi = pd.Series(ic[h]["low"]), pd.Series(ic[h]["high"])
        diff = (lo - hi).dropna()
        segs = {}
        for name, m in (("all", diff.index == diff.index), ("a", diff.index < lp.SPLIT), ("b", diff.index >= lp.SPLIT)):
            x = diff[m]
            segs[name] = (float(x.mean()), nw_t(x, lag), float(lo[lo.index.isin(x.index)].mean()), float(hi[hi.index.isin(x.index)].mean()))
        ic_tab[h] = segs

    # 檢定二：Fama-MacBeth 交互項
    fm = pd.Series({d: fm_interaction(scores[d], att[d], fwd["fwd20"].loc[d], c.sector) for d in sched}).dropna()
    fm_tab = {name: (float(x.mean()), nw_t(x, 0)) for name, x in
              (("all", fm), ("a", fm[fm.index < lp.SPLIT]), ("b", fm[fm.index >= lp.SPLIT]))}

    # 檢定三：可交易版本
    fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
    close = bc.raw_close(c)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    def run(tilted: bool, offset: int):
        wd, pl, ps = {}, frozenset(), frozenset()
        for d in sched[offset::3]:
            w = lt.ew_ls_buffer(scores[d], c.sector, shortable_at(d), pl, ps)
            if tilted:
                w = tilt_weights(w, att[d], c.sector)
            wd[d] = w
            pl, ps = frozenset(w[w > 0].index), frozenset(w[w < 0].index)
        return hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)

    start = sched[2]
    series, turn = {}, {}
    for name, tilted in (("fv3 建構（SUE 單獨）", False), ("傾斜：低關注權重 × (1 + 0.5 × ATT_low)", True)):
        sims = [run(tilted, off) for off in (0, 1, 2)]
        rets = pd.concat([s["ret"][s.index > start] for s in sims], axis=1).mean(axis=1)
        series[name] = rets
        turn[name] = float(np.mean([s["turnover"][s.index > start].sum() for s in sims]) / (len(rets) / 252))

    # 放空覆蓋率（以放空權重加權；不受可借限制時應放空的權重中，能借到的比例）
    cover = {"fv3": [], "tilt": []}
    for d in sched:
        allow = pd.Series(True, index=c.tickers)
        w0 = lt.ew_ls_buffer(scores[d], c.sector, allow, q_keep=None)
        ok = shortable_at(d)
        for name, w in (("fv3", w0), ("tilt", tilt_weights(w0, att[d], c.sector))):
            sh = -w[w < 0]
            if sh.sum() > 0:
                cover[name].append(float((sh * ok.reindex(sh.index).fillna(False)).sum() / sh.sum()))

    # 低／高兩半各自的 SUE 多空（每月、限制可借）與進場日漲停比例
    halves, limit_up = {}, {}
    for half in ("low", "high"):
        wd = {}
        lu = []
        for d in sched:
            a = att[d]
            med = a.groupby(c.sector.reindex(a.index)).transform("median")
            keep = a.index[(a <= med).to_numpy()] if half == "low" else a.index[(a > med).to_numpy()]
            w = bc.ew_long_short(scores[d].reindex(keep), c.sector, shortable_at(d))
            wd[d] = w
            lg = w[w > 0].index
            if len(lg):
                lu.append(float((c.rets.loc[d].reindex(lg) >= 0.095).mean()))
        sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, sched, fee=fee)
        halves[half] = hc.stats(sim["ret"], sim)
        limit_up[half] = float(np.mean(lu))

    # ATT_res 單獨當腿（做多低關注）
    wd = {d: bc.ew_long_short(-att[d], c.sector, shortable_at(d)) for d in sched}
    att_leg = hc.stats(hc.simulate_weights(wd, c.rets, c.betas, c.tx, sched, fee=fee)["ret"])

    return {"top_n": top_n, "corr": corr, "ic": ic_tab, "fm": fm_tab, "series": series, "turn": turn,
            "cover": {k: float(np.mean(v)) for k, v in cover.items()}, "halves": halves, "limit_up": limit_up, "att_leg": att_leg}


def main():
    res = {n: analyse(n) for n in (300, 500)}
    lines = ["# I004 月營收驚奇 × 低法人關注（自動產生）", "",
             "由 [analysis/sue_attention.py](../analysis/sue_attention.py) 產生；檢定計畫見點子卡 "
             "[I004](../research/ideas/I004-sue-x-low-attention.md)（看結果前固定）。IC = 產業內 Spearman 相關（−1～1），"
             "括號為 Newey-West t 值；Sharpe = 年化報酬 ÷ 波動，格式 2019–2022 / 2023–2026/04。研究結果，非投資建議。", ""]
    verdict = {}
    for n, r in res.items():
        lines += [f"## 市值前 {n} 名", "",
                  f"ATT_res 與已失敗腿的橫斷面相關：foreign_chg {r['corr']['foreign_chg']:+.2f}、trust_buy {r['corr']['trust_buy']:+.2f}；"
                  f"ATT_res 單獨當腿（做多低關注、限制可借）Sharpe {r['att_leg']['sh_oos']:.2f} / {r['att_leg']['sh_is']:.2f}。", "",
                  "### 檢定一：低／高關注兩半的 SUE 產業內 IC", "",
                  "| 視窗 | 期間 | 低關注 IC | 高關注 IC | 差額（低 − 高） |", "|---|---|---|---|---|"]
        for h in HORIZONS:
            for seg, lab in (("a", "2019–2022"), ("b", "2023–2026/04"), ("all", "全期")):
                m, t, lo, hi = r["ic"][h][seg]
                lines.append(f"| {h} | {lab} | {lo:+.3f} | {hi:+.3f} | {m:+.3f}（{t:.1f}） |")
        lines += ["", "### 檢定二：Fama-MacBeth 交互項（SUE × ATT_res，預期為負）", "",
                  "| 期間 | 係數 | t |", "|---|---|---|"]
        for seg, lab in (("a", "2019–2022"), ("b", "2023–2026/04"), ("all", "全期")):
            m, t = r["fm"][seg]
            lines.append(f"| {lab} | {m:+.4f} | {t:.1f} |")
        lines += ["", "### 檢定三：可交易版本（fv3 建構：每 3 個月三份錯開、緩衝、可借條件 D、台指期對沖、扣成本與借券費）", "",
                  "| 版本 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 最大回撤 | 年換手（倍） |", "|---|---|---|---|---|---|"]
        st = {}
        for name, x in r["series"].items():
            s = hc.stats(x)
            st[name] = s
            lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} | {r['turn'][name]:.1f} |")
        lines += ["", f"放空覆蓋率（應放空權重中可借到的比例）：fv3 {r['cover']['fv3']:.0%}、傾斜 {r['cover']['tilt']:.0%}。", "",
                  "低／高關注兩半各自的 SUE 多空（每月換倉、限制可借）：" +
                  "；".join(f"{'低' if k == 'low' else '高'}關注 Sharpe {v['sh_oos']:.2f} / {v['sh_is']:.2f}、年換手 {v['turnover']:.0f} 倍、"
                           f"進場日做多名單漲停比例 {r['limit_up'][k]:.1%}" for k, v in r["halves"].items()) + "。", ""]
        base, tl = list(st.values())
        verdict[n] = {"ic": r["ic"]["fwd20"], "fm": r["fm"], "trade": (tl["sh_oos"] > base["sh_oos"] and tl["sh_is"] > base["sh_is"]),
                      "cover": r["cover"]["tilt"] >= 0.9 * r["cover"]["fv3"]}
        pd.DataFrame(r["series"]).to_csv(ROOT / "reports" / "legs" / f"sue_attention_top{n}.csv")

    v3, v5 = verdict[300], verdict[500]
    c1 = v3["ic"]["a"][0] > 0 and v3["ic"]["b"][0] > 0 and v3["ic"]["all"][1] > 2
    c2 = np.sign(v5["ic"]["all"][0]) == np.sign(v3["ic"]["all"][0])
    c3 = v3["fm"]["a"][0] < 0 and v3["fm"]["b"][0] < 0
    c4 = v3["trade"] and v3["cover"]
    overall = "通過" if (c1 and c2 and c3 and c4) else ("partial（有解釋力、可交易性不足）" if (c1 and c2 and c3) else "未通過")
    lines += ["## 判定（主樣本前 300 名）", "",
              f"1. fwd20 IC 差兩段 > 0 且合併 t > 2：{'✓' if c1 else '✗'}",
              f"2. 前 500 名同號：{'✓' if c2 else '✗'}",
              f"3. 交互項兩段皆 < 0：{'✓' if c3 else '✗'}",
              f"4. 傾斜版兩段 Sharpe 都高於 fv3 建構，且放空覆蓋率 ≥ fv3 的 90%：{'✓' if c4 else '✗'}", "",
              f"**結論：{overall}**"]
    (ROOT / "docs" / "sue_attention.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
