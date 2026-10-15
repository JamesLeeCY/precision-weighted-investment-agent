"""I005 產業層級營收驚奇（產業輪動）（點子卡 research/ideas/I005-industry-revenue-surprise-rotation.md 的檢定計畫，看結果前固定）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/industry_sue.py
輸出 docs/industry_sue.md 與 reports/legs/industry_sue_top{300,500}.csv。

- 樣本：主樣本市值前 500 名、次要前 300 名；換倉日 = leg_probe 的 schedule（2019-01 ~ 2026-04）；只納入該期成員 ≥ 5 檔的產業；排除金融保險業。
- 訊號 ISUE：產業成員原始 SUE 截尾到 [−3, 3] 後等權平均；次要：廣度（SUE > 0 比例）、市值加權平均 SUE（只報告）。
- 檢定一：每期 ISUE 與產業等權 fwd20／40／60 報酬的跨產業 Spearman IC；Newey-West t（lag 0／1／2）。
- 控制：產業過去 1 個月、12−1 個月等權報酬；Fama-MacBeth（應變數 fwd40 產業報酬，自變數 ISUE、1 個月、12−1，皆橫斷面標準化），看 ISUE 係數；
  另報告 ISUE 與公告期間（上月最後交易日 → 進場前一日）產業報酬的相關。
- 檢定二：產業多空——依 ISUE 做多前 1/3 產業、放空後 1/3；產業內等權持有全部成員（放空只用可借條件 D）、產業之間等權；
  台指期對沖、扣成本與借券費；持有 1 個月與 3 個月（三份錯開取平均，主規格）。
- 檢定三：與同股票池 fv3 建構（SUE 產業內多空、每 3 個月三份錯開、緩衝、條件 D）的日報酬相關，及波動相同的 50/50 合成。
- 穩健性（只報告）：排除半導體業；排除「其他」「其他電子業」；產業報酬改市值加權。
- 通過（全部成立）：(1) 前 500 名 fwd40 IC 兩段 > 0 且合併 NW t > 2.5；(2) Fama-MacBeth ISUE 係數兩段 > 0；
  (3) 產業多空（3 個月）扣成本 Sharpe 兩段 > 0.3；(4) 50/50 合成兩段 Sharpe 都高於 fv3。只有 (1)(2) 成立記為 partial；前 300 名需同號。
研究結果，非投資建議。
"""
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
from sue_attention import nw_t, spearman  # noqa: E402

MIN_N = 5
HORIZONS = {"fwd20": (20, 0), "fwd40": (40, 1), "fwd60": (60, 2)}


def industry_signal(sue: pd.Series, sector: pd.Series, cap: pd.Series | None = None, exclude=()) -> pd.DataFrame:
    """回傳各產業 [n, isue, breadth, isue_cw]；只取成員 ≥ MIN_N、排除金融保險與 exclude。"""
    s = sue.dropna().clip(-3, 3)
    sec = sector.reindex(s.index)
    rows = {}
    for k, g in s.groupby(sec):
        if len(g) < MIN_N or "金融" in str(k) or k in exclude:
            continue
        row = {"n": len(g), "isue": g.mean(), "breadth": (g > 0).mean()}
        if cap is not None:
            w = cap.reindex(g.index).fillna(0)
            row["isue_cw"] = float((g * w).sum() / w.sum()) if w.sum() > 0 else np.nan
        rows[k] = row
    return pd.DataFrame(rows).T.astype(float)


def industry_return(r: pd.Series, members: pd.Index, sector: pd.Series, cap: pd.Series | None = None) -> pd.Series:
    x = r.reindex(members).dropna()
    sec = sector.reindex(x.index)
    if cap is None:
        return x.groupby(sec).mean()
    w = cap.reindex(x.index).fillna(0)
    return (x * w).groupby(sec).sum() / w.groupby(sec).sum()


def industry_ls(sig: pd.Series, members: pd.Index, sector: pd.Series, shortable: pd.Series) -> pd.Series:
    """做多 ISUE 前 1/3 產業、放空後 1/3；產業內等權、產業之間等權；放空只用可借股票。"""
    r = sig.dropna().rank(pct=True)
    longs, shorts = r[r > 2 / 3].index, r[r <= 1 / 3].index
    sec = sector.reindex(members)
    out = {}
    lw = {k: list(sec[sec == k].index) for k in longs}
    sw = {k: [t for t in sec[sec == k].index if bool(shortable.get(t, False))] for k in shorts}
    lw, sw = {k: v for k, v in lw.items() if v}, {k: v for k, v in sw.items() if v}
    for book, sign in ((lw, 1.0), (sw, -1.0)):
        for k, names in book.items():
            for t in names:
                out[t] = sign / len(book) / len(names)
    return pd.Series(out, dtype=float)


def analyse(top_n: int) -> dict:
    c = lp.prepare(top_n)
    sched = c.schedule
    days = c.adj.index
    cap = np.exp(c.logcap)
    fwd = {h: c.adj.shift(-n) / c.adj - 1 for h, (n, _) in HORIZONS.items()}
    mom1 = c.adj / c.adj.shift(20) - 1
    mom12 = c.adj.shift(20) / c.adj.shift(250) - 1

    sig, ic = {}, {h: {} for h in HORIZONS}
    rob = {"排除半導體業": {}, "排除其他、其他電子業": {}, "產業報酬改市值加權": {}, "廣度（SUE > 0 比例）": {}, "市值加權平均 SUE": {}}
    fm, ann_corr = {}, {}
    for d in sched:
        mo = d.to_period("M").to_timestamp()
        if mo not in c.sue.index:
            continue
        mem = c.member.columns[c.member.loc[d]]
        sue = c.sue.loc[mo].reindex(mem)
        S = industry_signal(sue, c.sector, cap.loc[d])
        if len(S) < 6:
            continue
        sig[d] = S
        rets = {h: industry_return(fwd[h].loc[d], mem, c.sector) for h in HORIZONS}
        for h in HORIZONS:
            ic[h][d] = spearman(S["isue"], rets[h].reindex(S.index))
        rcw = industry_return(fwd["fwd40"].loc[d], mem, c.sector, cap.loc[d])
        rob["產業報酬改市值加權"][d] = spearman(S["isue"], rcw.reindex(S.index))
        rob["廣度（SUE > 0 比例）"][d] = spearman(S["breadth"], rets["fwd40"].reindex(S.index))
        rob["市值加權平均 SUE"][d] = spearman(S["isue_cw"], rets["fwd40"].reindex(S.index))
        for lab, ex in (("排除半導體業", ("半導體業",)), ("排除其他、其他電子業", ("其他", "其他電子業"))):
            S2 = industry_signal(sue, c.sector, exclude=ex)
            rob[lab][d] = spearman(S2["isue"], rets["fwd40"].reindex(S2.index))
        # Fama-MacBeth：fwd40 產業報酬 ~ ISUE + 1 個月 + 12−1
        X = pd.DataFrame({"isue": S["isue"].astype(float),
                          "m1": industry_return(mom1.loc[d], mem, c.sector).reindex(S.index),
                          "m12": industry_return(mom12.loc[d], mem, c.sector).reindex(S.index)})
        y = rets["fwd40"].reindex(S.index)
        df = pd.concat([X, y.rename("y")], axis=1).dropna()
        if len(df) >= 8:
            Z = (df[["isue", "m1", "m12"]] - df[["isue", "m1", "m12"]].mean()) / df[["isue", "m1", "m12"]].std()
            A = np.column_stack([np.ones(len(Z)), Z.to_numpy()])
            beta, *_ = np.linalg.lstsq(A, ((df["y"] - df["y"].mean()) / df["y"].std()).to_numpy(), rcond=None)
            fm[d] = beta[1]
        prev_end = days[days < mo][-1]
        k = days.get_loc(d)
        ann = industry_return(c.adj.iloc[k - 1] / c.adj.loc[prev_end] - 1, mem, c.sector)
        ann_corr[d] = spearman(S["isue"], ann.reindex(S.index))

    def seg_stats(x: pd.Series, lag: int):
        x = pd.Series(x).dropna()
        return {name: (float(v.mean()), nw_t(v, lag)) for name, v in
                (("a", x[x.index < lp.SPLIT]), ("b", x[x.index >= lp.SPLIT]), ("all", x))}

    ic_tab = {h: seg_stats(ic[h], lag) for h, (_, lag) in HORIZONS.items()}
    rob_tab = {k: seg_stats(v, 1) for k, v in rob.items()}
    fm_tab = seg_stats(pd.Series(fm), 1)

    # 交易：產業多空與 fv3 建構
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    close = bc.raw_close(c)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    sdates = [d for d in sched if d in sig]
    start = sdates[2]

    def ind_run(step: int, offset: int):
        wd = {}
        for d in sdates[offset::step]:
            mem = c.member.columns[c.member.loc[d]]
            wd[d] = industry_ls(sig[d]["isue"], mem, c.sector, shortable_at(d))
        return hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)

    scores = lp.leg_scores(c, "sue")

    def fv3_run(offset: int):
        wd, pl, ps = {}, frozenset(), frozenset()
        for d in sched[offset::3]:
            w = lt.ew_ls_buffer(scores[d], c.sector, shortable_at(d), pl, ps)
            wd[d] = w
            pl, ps = frozenset(w[w > 0].index), frozenset(w[w < 0].index)
        return hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)

    def avg3(fn):
        sims = [fn(o) for o in (0, 1, 2)]
        r = pd.concat([s["ret"][s.index > start] for s in sims], axis=1).mean(axis=1)
        to = float(np.mean([s["turnover"][s.index > start].sum() for s in sims]) / (len(r) / 252))
        return r, to

    m1 = ind_run(1, 0)
    series = {"產業多空：每月換倉": m1["ret"][m1.index > start]}
    turn = {"產業多空：每月換倉": float(m1["turnover"][m1.index > start].sum() / (len(series["產業多空：每月換倉"]) / 252))}
    series["產業多空：3 個月三份錯開（主規格）"], turn["產業多空：3 個月三份錯開（主規格）"] = avg3(lambda o: ind_run(3, o))
    series["fv3 建構（SUE 產業內多空）"], turn["fv3 建構（SUE 產業內多空）"] = avg3(fv3_run)
    a, b = series["產業多空：3 個月三份錯開（主規格）"], series["fv3 建構（SUE 產業內多空）"]
    ab = pd.concat([a, b], axis=1).dropna()
    scale = ab.iloc[:, 1].std() / ab.iloc[:, 0].std()
    series["50/50 合成（產業多空調到與 fv3 同波動）"] = (ab.iloc[:, 0] * scale + ab.iloc[:, 1]) / 2
    turn["50/50 合成（產業多空調到與 fv3 同波動）"] = float("nan")
    corr = float(ab.iloc[:, 0].corr(ab.iloc[:, 1]))
    n_ind = float(np.mean([len(v) for v in sig.values()]))
    return {"top_n": top_n, "ic": ic_tab, "rob": rob_tab, "fm": fm_tab, "ann_corr": float(np.nanmean(list(ann_corr.values()))),
            "series": series, "turn": turn, "corr": corr, "n_ind": n_ind, "n_dates": len(sig)}


def main():
    res = {n: analyse(n) for n in (500, 300)}
    lines = ["# I005 產業層級營收驚奇（產業輪動）（自動產生）", "",
             "由 [analysis/industry_sue.py](../analysis/industry_sue.py) 產生；檢定計畫見點子卡 "
             "[I005](../research/ideas/I005-industry-revenue-surprise-rotation.md)（看結果前固定）。IC = 跨產業 Spearman 相關（−1～1），"
             "括號為 Newey-West t 值；Sharpe = 年化報酬 ÷ 波動，格式 2019–2022 / 2023–2026/04。研究結果，非投資建議。", ""]
    lab = {"a": "2019–2022", "b": "2023–2026/04", "all": "全期"}
    st_all = {}
    for n, r in res.items():
        lines += [f"## 市值前 {n} 名", "",
                  f"有效期數 {r['n_dates']}，平均每期 {r['n_ind']:.1f} 個產業（成員 ≥ {MIN_N}、排除金融保險）。"
                  f"ISUE 與公告期間（上月底 → 進場前一日）產業報酬的平均相關 {r['ann_corr']:+.2f}。", "",
                  "### 檢定一：跨產業 IC", "", "| 視窗 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|"]
        for h in HORIZONS:
            lines.append(f"| {h} | " + " | ".join(f"{r['ic'][h][s][0]:+.3f}（{r['ic'][h][s][1]:.1f}）" for s in ("a", "b", "all")) + " |")
        lines += ["", "穩健性（fwd40 IC，只報告）：", "", "| 版本 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|"]
        for k, v in r["rob"].items():
            lines.append(f"| {k} | " + " | ".join(f"{v[s][0]:+.3f}（{v[s][1]:.1f}）" for s in ("a", "b", "all")) + " |")
        lines += ["", "### 控制產業價格動能（Fama-MacBeth，fwd40，ISUE 標準化係數）", "",
                  "| 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|",
                  "| " + " | ".join(f"{r['fm'][s][0]:+.3f}（{r['fm'][s][1]:.1f}）" for s in ("a", "b", "all")) + " |", "",
                  "### 檢定二、三：策略（台指期對沖，扣成本與借券費）", "",
                  "| 版本 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 年化波動 | 最大回撤 | 年換手（倍） |", "|---|---|---|---|---|---|---|"]
        st = {}
        for name, x in r["series"].items():
            s = hc.stats(x)
            st[name] = s
            to = r["turn"][name]
            lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} | "
                         f"{'—' if to != to else f'{to:.1f}'} |")
        lines += ["", f"產業多空（主規格）與 fv3 建構的日報酬相關：{r['corr']:+.2f}。", ""]
        st_all[n] = st
        pd.DataFrame(r["series"]).to_csv(ROOT / "reports" / "legs" / f"industry_sue_top{n}.csv")

    r5, r3, s5 = res[500], res[300], st_all[500]
    c1 = r5["ic"]["fwd40"]["a"][0] > 0 and r5["ic"]["fwd40"]["b"][0] > 0 and r5["ic"]["fwd40"]["all"][1] > 2.5
    c2 = r5["fm"]["a"][0] > 0 and r5["fm"]["b"][0] > 0
    m = s5["產業多空：3 個月三份錯開（主規格）"]
    c3 = m["sh_oos"] > 0.3 and m["sh_is"] > 0.3
    bl, f3 = s5["50/50 合成（產業多空調到與 fv3 同波動）"], s5["fv3 建構（SUE 產業內多空）"]
    c4 = bl["sh_oos"] > f3["sh_oos"] and bl["sh_is"] > f3["sh_is"]
    c5 = np.sign(r3["ic"]["fwd40"]["all"][0]) == np.sign(r5["ic"]["fwd40"]["all"][0])
    overall = "通過" if (c1 and c2 and c3 and c4 and c5) else ("partial（有預測力、可交易性不足）" if (c1 and c2 and c5) else "未通過")
    lines += ["## 判定（主樣本前 500 名）", "",
              f"1. fwd40 跨產業 IC 兩段 > 0 且合併 NW t > 2.5：{'✓' if c1 else '✗'}",
              f"2. 加入產業價格動能後 ISUE 係數兩段 > 0：{'✓' if c2 else '✗'}",
              f"3. 產業多空（3 個月）扣成本 Sharpe 兩段 > 0.3：{'✓' if c3 else '✗'}",
              f"4. 與 fv3 的 50/50 合成兩段 Sharpe 都高於 fv3：{'✓' if c4 else '✗'}",
              f"5. 前 300 名 fwd40 IC 同號：{'✓' if c5 else '✗'}", "", f"**結論：{overall}**"]
    (ROOT / "docs" / "industry_sue.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
