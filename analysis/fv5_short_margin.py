"""I056 fv5 空方腿以融券為主、借券補足（點子卡 research/ideas/I056-fv5-short-leg-margin-vs-sbl.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/fv5_short_margin.py
輸出 docs/fv5_short_margin.md。

設計（依點子卡；補充以「補」標示）：
- fv5 名單與權重不變（前 500 名、SUE 產業內前／後 1/3、放空只用條件 D 可借者、三份錯開、每 3 個換倉日換倉、台指期對沖）。
- 停券日期：補——改用 FinMind TaiwanStockMarginPurchaseShortSale 的官方註記（Note 含「X」= 證交所／櫃買停止融券賣出），
  不必自行由餘額偵測，所以點子卡前置 (a) 的公告核對改為報告「停券窗內融券餘額降到窗前 5% 以下」的比例。
  每個連續 X 區間為一次停券；第一個 X 日收盤回補，最後一個 X 日之後第一個交易日收盤再放空。
- 可融券：換倉日融券限額 > 0、前一日融券餘額 < 限額、當日非 X。前置 (b)：可融券的放空權重比例 < 50% 則停止。
- 版本：S0 全用借券（現行）；S1 可融券者用融券，停券期間回補、以 β × 台指期空單暫代，停券後再融券放空；
  S2 可融券者用融券，停券時改用借券（多一次回補＋借券放空），之後持有借券到下次換倉。
- 成本（使用者 2026-10-24 同意用點子卡預設值）：融券費 0.08%（每次融券賣出）；保證金與擔保品不計利息；借券費同 fv5（60 日成交量加權費率），
  券商加碼 0%（主要）與 30%（敏感度）；股票交易單邊 0.29625%；台指期 0.005%。
- 指標：年化淨報酬、Sharpe、最大回撤；空方成本拆解；每次換倉的配對成本差（S − S0，正值 = 省下）Newey-West t（落後 2）。
- 通過：S1 或 S2 相對 S0 年化淨報酬差 ≥ +0.5%、兩段同為正、兩段 Sharpe 都不低於 S0，配對差 Holm 校正（家族 5%）；以加碼 30% 的保守情境為準。
- 附帶：最後回補日（停券窗內融券餘額首次降到窗前 5% 以下的日子；補）前 5 個交易日，該股的市場調整報酬（全部前 500 名停券事件）。
  補：依借券費率分組的成本差未做。
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
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
from sue_attention import nw_t  # noqa: E402

MFEE = 0.0008
SC = lp.STOCK_COST


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def margin_frames(c):
    X, LIM, BAL = {}, {}, {}
    for t in c.tickers:
        d = c.client.get("TaiwanStockMarginPurchaseShortSale", t.split(".")[0], lp.EV_START, lp.EV_END)
        if d.empty:
            continue
        d = d.assign(date=pd.to_datetime(d["date"])).drop_duplicates("date").set_index("date")
        X[t] = d["Note"].astype(str).str.contains("X")
        LIM[t] = d["ShortSaleLimit"].astype(float)
        BAL[t] = d["ShortSaleTodayBalance"].astype(float)
    f = lambda m: pd.DataFrame(m).reindex(index=c.adj.index, columns=c.tickers)  # noqa: E731
    return f(X).fillna(False).astype(bool), f(LIM), f(BAL)


def main():
    c = lp.prepare(500)
    days, sched, sector = c.adj.index, c.schedule, c.sector
    sue = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    close = bc.raw_close(c)
    XN, LIM, BAL = margin_frames(c)
    tx = c.tx.reindex(days).fillna(0.0)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    # 停券窗：連續 X 區間
    windows = {}
    for t in c.tickers:
        s = XN[t].to_numpy()
        w, i = [], 0
        while i < len(s):
            if s[i]:
                j = i
                while j + 1 < len(s) and s[j + 1]:
                    j += 1
                w.append((i, j))
                i = j + 1
            else:
                i += 1
        windows[t] = w
    # 前置 (a)：窗內餘額降到窗前 5% 以下的比例
    chk, cover_day = [], {}
    for t, ws in windows.items():
        for i, j in ws:
            if i < 1 or not (pd.Timestamp("2019-01-01") <= days[i] < lp.HOLDOUT):
                continue
            pre = BAL[t].iat[i - 1]
            seg = BAL[t].iloc[i:j + 1]
            if pre == pre and pre > 0:
                hit = seg <= 0.05 * pre
                chk.append(bool(hit.any()))
                if hit.any():
                    cover_day[(t, i)] = int(np.argmax(hit.to_numpy())) + i
    ok_a = float(np.mean(chk)) if chk else float("nan")

    def run(markup: float):
        out = {k: [] for k in ("S0", "S1", "S2")}
        per = {k: [] for k in ("S1", "S2")}
        comp = {k: {"borrow": 0.0, "mfee": 0.0, "roundtrip": 0.0, "track": 0.0} for k in ("S0", "S1", "S2")}
        margin_share = []
        for off in range(3):
            wd = {d: lt.ew_ls_buffer(sue[d], sector, shortable_at(d), q_keep=None) for d in sched[off::3]}
            reb = list(wd)
            base = hc.simulate_weights(wd, c.rets, c.betas, c.tx, reb, fee=fee, fee_mult=1 + markup)["ret"]
            adj = {k: pd.Series(0.0, index=base.index) for k in ("S1", "S2")}
            prev = pd.Series(dtype=float)
            for n, d in enumerate(reb):
                nxt = reb[n + 1] if n + 1 < len(reb) else lp.HOLDOUT
                kd = int(days.searchsorted(d))
                period = days[(days > d) & (days <= nxt)]
                if not len(period):
                    continue
                w = wd[d]
                sh = -w[w < 0]
                if not len(sh):
                    prev = w
                    continue
                rate = fee.loc[d, sh.index].fillna(fee.loc[d].median()) / 100 * (1 + markup)
                lim_ok = (LIM.loc[d, sh.index] > 0) & (BAL.iloc[max(kd - 1, 0)][sh.index] < LIM.loc[d, sh.index]) & ~XN.loc[d, sh.index]
                mg = sh[lim_ok.fillna(False).to_numpy(bool)]
                margin_share.append(float(mg.sum() / sh.sum()))
                newsh = (sh - (-prev[prev < 0]).reindex(sh.index).fillna(0.0)).clip(lower=0)
                bvec = c.betas.loc[d].reindex(sh.index).fillna(1.0)
                comp["S0"]["borrow"] += float((sh * rate).sum()) / 252 * len(period)
                for ver in ("S1", "S2"):
                    a = adj[ver]
                    saved_total = 0.0
                    for t, wt in mg.items():
                        kk = [int(days.searchsorted(x)) for x in (period[0], period[-1])]
                        win = [(i, j) for i, j in windows.get(t, []) if i <= kk[1] and j >= kk[0]]
                        r_day = rate[t] / 252
                        on_margin = np.ones(len(period), bool)
                        cost_series = pd.Series(0.0, index=period)
                        cost_series.iloc[0] += MFEE * newsh.get(t, 0.0)
                        comp[ver]["mfee"] += MFEE * newsh.get(t, 0.0)
                        for i, j in win[:1]:                         # 補：一段持有期最多處理一次停券（季配息股一季一次）
                            fi = max(i, kk[0])
                            pos_f = int(np.searchsorted(period, days[fi]))
                            if ver == "S1":
                                re = j + 1
                                pos_r = int(np.searchsorted(period, days[min(re, len(days) - 1)])) if re < len(days) else len(period)
                                cost_series.iloc[pos_f] += 2 * SC * wt
                                comp[ver]["roundtrip"] += 2 * SC * wt
                                if pos_r < len(period):
                                    cost_series.iloc[pos_r] += MFEE * wt
                                    comp[ver]["mfee"] += MFEE * wt
                                rng = period[pos_f + 1:pos_r + 1]
                                tr = wt * (c.rets.loc[rng, t].fillna(0.0) - bvec[t] * tx.loc[rng])     # 空方換成 β×台指期：多賺 w(r − βtx)
                                cost_series.loc[rng] -= tr
                                comp[ver]["track"] += float(-tr.sum())
                            else:
                                cost_series.iloc[pos_f] += 2 * SC * wt
                                comp[ver]["roundtrip"] += 2 * SC * wt
                                on_margin[pos_f + 1:] = False
                        borrow_saved = wt * r_day * on_margin.sum()
                        saved_total += borrow_saved
                        comp[ver]["borrow"] += wt * r_day * (len(period) - on_margin.sum())
                        a.loc[period] += wt * r_day * on_margin - cost_series.to_numpy()
                    nb = sh.drop(mg.index, errors="ignore")
                    comp[ver]["borrow"] += float((nb * rate.reindex(nb.index)).sum()) / 252 * len(period)
                    per[ver].append({"d": d, "diff": float(a.loc[period].sum())})
                prev = w
            out["S0"].append(base)
            for ver in ("S1", "S2"):
                out[ver].append(base + adj[ver])
        start = sched[2]
        res, ser = {}, {}
        for k, parts in out.items():
            x = pd.concat(parts, axis=1).mean(axis=1)
            x = x[x.index > start]
            ser[k] = x
            res[k] = hc.stats(x) | {"full": lp.sharpe(x.dropna())}
        yrs = len(ser["S0"]) / 252
        for k in comp:
            for kk in comp[k]:
                comp[k][kk] = comp[k][kk] / 3 / yrs
        return res, ser, per, comp, float(np.mean(margin_share)) if margin_share else 0.0

    res0, ser0, per0, comp0, share = run(0.0)
    res3, ser3, per3, comp3, _ = run(0.3)
    stop_b = share < 0.5
    # 最後回補日前 5 日的空方價格變動（只報告）
    pre5 = []
    for (t, i), kc in cover_day.items():
        if kc - 5 < 1:
            continue
        rng = days[kc - 5:kc]
        pre5.append(float((c.rets.loc[rng, t].fillna(0.0) - c.betas[t].iat[kc - 5] * c.tx.reindex(rng).fillna(0.0)).sum()) if t in c.tickers else np.nan)
    pre5 = np.array([x for x in pre5 if x == x])
    L = ["# I056 fv5 空方腿以融券為主、借券補足（自動產生）", "",
         "由 [analysis/fv5_short_margin.py](../analysis/fv5_short_margin.py) 產生；設計見程式開頭（看結果前固定）。"
         "Sharpe 為扣成本與台指期對沖後，格式 2019–2022 / 2023–2026/04；成本為年化、占組合資金的比例。成本參數為點子卡預設值（融券費 0.08%、擔保品不計利息），尚未經券商確認。研究結果，非投資建議。", "",
         "## 前置檢查", "",
         f"- (a) 停券日期用官方註記；停券窗內融券餘額降到窗前 5% 以下的比例 {ok_a:.0%}（{len(chk)} 個窗）。",
         f"- (b) 放空權重中可融券的比例 {share:.0%}（門檻 50%）→ {'停止' if stop_b else '繼續'}。", ""]
    if not stop_b:
        for lab, res, comp in (("券商借券加碼 0%（主要）", res0, comp0), ("券商借券加碼 30%（保守，判定依據）", res3, comp3)):
            L += [f"## {lab}", "", "| 版本 | Sharpe | 全期 | 年化淨報酬 | 最大回撤 | 借券費 | 融券費 | 停券來回交易 | 台指期暫代追蹤差 |", "|---|---|---|---|---|---|---|---|---|"]
            for k, nm in (("S0", "S0 全用借券（現行）"), ("S1", "S1 融券＋停券時台指期暫代"), ("S2", "S2 融券＋停券時改借券")):
                s, cp = res[k], comp[k]
                L.append(f"| {nm} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.2%} | {s['mdd']:.1%} | "
                         f"{cp['borrow']:.2%} | {cp['mfee']:.2%} | {cp['roundtrip']:.2%} | {cp['track']:+.2%} |")
            L.append("")
        pv, rows = {}, []
        for k in ("S1", "S2"):
            pr = pd.DataFrame(per3[k]).groupby("d")["diff"].sum().sort_index()
            t = nw_t(pr, 2)
            pv[k] = 1 - phi(t) if t == t else 1.0
            d_all = res3[k]["ann"] - res3["S0"]["ann"]
            seg = [float((ser3[k] - ser3["S0"])[(ser3[k].index < lp.SPLIT) == flag].mean() * 252) for flag in (True, False)]
            rows.append((k, d_all, seg, t, res3[k]))
        order = sorted(pv, key=pv.get)
        holm, still = {}, True
        for i, k in enumerate(order):
            ok = still and pv[k] <= 0.05 / (len(order) - i)
            holm[k] = ok
            still = ok
        passed = []
        L += ["## 判定（保守情境：借券加碼 30%）", "", "| 版本 | 年化淨報酬差 | 2019–2022 / 2023–2026/04 | 每次換倉配對差 t | Sharpe 兩段不低於 S0 | Holm |", "|---|---|---|---|---|---|"]
        for k, d_all, seg, t, s in rows:
            sh_ok = s["sh_oos"] >= res3["S0"]["sh_oos"] and s["sh_is"] >= res3["S0"]["sh_is"]
            ok = d_all >= 0.005 and seg[0] > 0 and seg[1] > 0 and sh_ok and holm[k]
            if ok:
                passed.append(k)
            L.append(f"| {k} | {d_all:+.2%} | {seg[0]:+.2%} / {seg[1]:+.2%} | {t:.2f} | {'✓' if sh_ok else '✗'} | {'✓' if holm[k] else '✗'} |")
        L += ["", f"只報告：最後回補日前 5 個交易日，空方股票的市場調整報酬平均 {pre5.mean():+.2%}（{len(pre5)} 次；正值 = 對空方不利）。", "",
              f"**結論：{'、'.join(passed) + ' 通過（成本參數需先向券商確認）' if passed else '未通過，維持全用借券'}**"]
    else:
        L += ["**結論：未通過（前置 (b) 停止）**"]
    (ROOT / "docs" / "fv5_short_margin.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
