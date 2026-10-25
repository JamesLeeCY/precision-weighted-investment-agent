"""I059 fv5 空方新倉避開停券窗（點子卡 research/ideas/I059-fv5-short-defer-stop-window.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/fv5_short_defer.py
輸出 docs/fv5_short_defer.md。

設計（依點子卡；補充以「補」標示）：
- 啟動條件：I058 第 501–1000 名全部停券事件市場調整 CAR[s − 4, s] = +0.47%（t 2.9）> 0 且 t > 2，成立（docs/forced_covering.md）。
- 停券窗：前 500 名 TaiwanStockMarginPurchaseShortSale 官方 Note「X」，s = 停券首日（analysis/forced_covering.events_for 的事件定義與類別）。
- 事前可知：除權息類需 TaiwanStockDividend 的 AnnouncementDate ≤ d（換倉日），延到 s 收盤放空；
  股東常會類用前一年同類窗 s 加 52 週的預測 ŝ，若 d < ŝ ≤ d + 10 個交易日，延到 ŝ + 3 個交易日收盤（不論實際停券是否發生）；其餘不延後。
  補：除權息類也需 s ≤ d + 10 個交易日；延後日超過該持有期結束者以持有期最後一日為限。
- 規則 R：只作用在 d 日新建或加碼的空單（權重增加部分 Δ）；延後期間以 β × 台指期空單暫代（期貨單邊 0.005%，進出各一次），
  省下延後期間的借券費；損益調整 = Δ × (股票報酬 − β × 台指期報酬) 加總 + 省下的借券費 − 期貨成本。
- 比較：fv5（S0）vs fv5 + R；只報告 fv5x + R。通過：年化淨報酬差 ≥ +0.10 個百分點、兩段皆 > 0、兩段 Sharpe 都不低於 S0、
  每次換倉配對差 Newey-West（落後 2）t > 2。
研究結果，非投資建議。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import corp_event_study as ce  # noqa: E402
import forced_covering as fc  # noqa: E402
import fv5_family as ff  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
from sue_attention import nw_t  # noqa: E402

K = 10
FUT = 0.00005


def known_windows(client, ev: pd.DataFrame, days: pd.DatetimeIndex) -> dict:
    """每檔：[(類別, s 的交易日索引, 公告日或預測基準)]。除權息類附公告日；股東常會類附前一年的 s。"""
    out = {}
    ann_cache = {}
    for t, g in ev.sort_values("s").groupby("ticker"):
        rows = []
        prev_agm = None
        for r in g.itertuples():
            k = int(days.searchsorted(r.s))
            if r.cat == "除權息":
                sid = t.split(".")[0]
                if sid not in ann_cache:
                    ann_cache[sid] = client.get("TaiwanStockDividend", sid, "2005-01-01")
                d = ann_cache[sid]
                ann = pd.NaT
                if not d.empty and r.ex == r.ex:
                    for col in ("CashExDividendTradingDate", "StockExDividendTradingDate"):
                        dd = pd.to_datetime(d[col], errors="coerce")
                        m = (dd - r.ex).abs() <= pd.Timedelta(days=3)
                        a = pd.to_datetime(d.loc[m, "AnnouncementDate"], errors="coerce").dropna()
                        if len(a):
                            ann = a.min() if ann != ann else min(ann, a.min())
                rows.append(("除權息", k, ann))
            elif r.cat == "股東常會":
                if prev_agm is not None and 300 <= (r.s - prev_agm).days <= 430:
                    pass
                rows.append(("股東常會", k, prev_agm))
                prev_agm = r.s
        out[t] = rows
    return out


def main():
    R, sched = ff.run_backtests()
    c = ff.LAST["c"]
    days = c.adj.index
    fee = hc.lending_fees(c.client, c.tickers, days)
    tx = c.tx.reindex(days).fillna(0.0)
    mkt = lp.market_tri(c.client)
    S = ce.Sample(c.client, 1, 500, mkt, c.tx)
    ev = fc.events_for(S, c.client)
    kw = known_windows(c.client, ev, days)
    # 股東常會類的預測：每檔每年用前一年 s + 52 週
    agm_prev = {t: sorted([pd.Timestamp(x) for x in ev.loc[(ev["ticker"] == t) & (ev["cat"] == "股東常會"), "s"]]) for t in kw}
    start = sched[2]
    results = {}
    for name, key in (("fv5", (False, False, False)), ("fv5x", (True, True, True))):
        adj_all, per, aff_w, delays, saved = [], [], [], [], []
        for wd in ff.LAST["wd"][key]:
            reb = list(wd)
            adj = pd.Series(0.0, index=days)
            prev = pd.Series(dtype=float)
            for n, d in enumerate(reb):
                nxt = reb[n + 1] if n + 1 < len(reb) else lp.HOLDOUT
                period = days[(days > d) & (days <= nxt)]
                if not len(period):
                    continue
                kd = int(days.searchsorted(d))
                kend = int(days.searchsorted(period[-1]))
                w = wd[d]
                sh = -w[w < 0]
                dsh = (sh - (-prev[prev < 0]).reindex(sh.index).fillna(0.0)).clip(lower=0)
                tot, aff = 0.0, 0.0
                for t, x in dsh[dsh > 0].items():
                    target = None
                    for cat, k, info in kw.get(t, []):
                        if cat == "除權息" and kd < k <= kd + K and info == info and info is not None and info <= d:
                            target = k
                            break
                    if target is None:
                        for s_prev in agm_prev.get(t, []):
                            shat = s_prev + pd.Timedelta(weeks=52)
                            ks = int(days.searchsorted(shat))
                            if s_prev < d and kd < ks <= kd + K:
                                target = min(ks + 3, len(days) - 1)
                                break
                    if target is None:
                        continue
                    target = min(target, kend)
                    rng = days[kd + 1:target + 1]
                    if not len(rng):
                        continue
                    b = float(c.betas.at[d, t]) if c.betas.at[d, t] == c.betas.at[d, t] else 1.0
                    rate = fee.at[d, t] if fee.at[d, t] == fee.at[d, t] else float(fee.loc[d].median())
                    gain = x * (c.rets.loc[rng, t].fillna(0.0) - b * tx.loc[rng])
                    adj.loc[rng] += gain + x * rate / 100 / 252
                    adj.loc[rng[0]] -= 2 * FUT * x * abs(b)
                    tot += float(gain.sum()) + x * rate / 100 / 252 * len(rng) - 2 * FUT * x * abs(b)
                    saved.append(float((c.rets.loc[rng, t].fillna(0.0) - b * tx.loc[rng]).sum()))
                    delays.append(len(rng))
                    aff += x
                aff_w.append(aff / max(float(dsh.sum()), 1e-12))
                per.append({"d": d, "diff": tot})
                prev = w
            adj_all.append(adj)
        base = R["fv5" if name == "fv5" else "fv5x（E+S+V）"]
        base = base[base.index > start]
        new = base + pd.concat(adj_all, axis=1).mean(axis=1).reindex(base.index).fillna(0.0)
        results[name] = {"s0": hc.stats(base) | {"full": lp.sharpe(base.dropna())}, "r": hc.stats(new) | {"full": lp.sharpe(new.dropna())},
                         "diff": new - base, "per": pd.DataFrame(per).groupby("d")["diff"].sum().sort_index(),
                         "aff": float(np.mean(aff_w)) if aff_w else 0.0, "delay": float(np.mean(delays)) if delays else 0.0,
                         "saved": float(np.mean(saved)) if saved else float("nan"), "n": len(delays)}
    r = results["fv5"]
    d_ann = r["r"]["ann"] - r["s0"]["ann"]
    seg = [float(r["diff"][(r["diff"].index < lp.SPLIT) == f].mean() * 252) for f in (True, False)]
    tp = nw_t(r["per"], 2)
    shok = r["r"]["sh_oos"] >= r["s0"]["sh_oos"] and r["r"]["sh_is"] >= r["s0"]["sh_is"]
    ok = d_ann >= 0.001 and seg[0] > 0 and seg[1] > 0 and shok and tp > 2
    L = ["# I059 fv5 空方新倉避開停券窗（自動產生）", "",
         "由 [analysis/fv5_short_defer.py](../analysis/fv5_short_defer.py) 產生；設計見程式開頭（看結果前固定）。"
         "Sharpe 為扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後，格式 2019–2022 / 2023–2026/04。研究結果，非投資建議。", "",
         "| 規格 | 版本 | Sharpe | 全期 | 年化淨報酬 | 最大回撤 |", "|---|---|---|---|---|---|"]
    for name, v in results.items():
        for lab, s in (("S0（現行）", v["s0"]), ("+ R（延後新空單）", v["r"])):
            L.append(f"| {name} | {lab} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.2%} | {s['mdd']:.1%} |")
    L += ["", f"fv5：受影響的新空單權重比例 {r['aff']:.1%}（{r['n']} 筆延後），平均延後 {r['delay']:.1f} 個交易日；"
          f"被延後部位在延後期間的「股票 − β × 台指期」報酬平均 {r['saved']:+.2%}（正值 = 省下的回補買壓）。", "",
          "## 判定（fv5）", "",
          f"- 年化淨報酬差 ≥ +0.10 個百分點：{d_ann:+.2%} → {'✓' if d_ann >= 0.001 else '✗'}",
          f"- 兩段皆 > 0：{seg[0]:+.2%} / {seg[1]:+.2%} → {'✓' if seg[0] > 0 and seg[1] > 0 else '✗'}",
          f"- 兩段 Sharpe 不低於 S0 → {'✓' if shok else '✗'}",
          f"- 每次換倉配對差 t > 2：{tp:.2f} → {'✓' if tp > 2 else '✗'}", "",
          f"**結論：{'通過（是否加入前瞻執行規則由使用者決定）' if ok else '未通過'}**"]
    (ROOT / "docs" / "fv5_short_defer.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
