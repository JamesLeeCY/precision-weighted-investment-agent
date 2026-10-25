"""I061 fv5 家族的稅後績效與除息日建倉規則（點子卡 research/ideas/I061-fv5-after-tax-exdiv-entry.md，檢定計畫看結果前固定）。

用法（於專案根目錄；先執行 analysis/fetch_i058_i060.py 取得 TaiwanStockDividend）：
    .venv/Scripts/python analysis/fv5_after_tax.py
輸出 docs/fv5_after_tax.md。

設計（依點子卡；補充以「補」標示）：
- 回測與權重：analysis/fv5_family.run_backtests（fv5 與 fv5x，各三份資金的換倉權重）。
- 稅率情境：T0 不課稅（現行回測）；T1 個人合併計稅淨 11.5% + 補充保費 2.11% = 13.61%；T2 分開計稅 28% + 2.11% = 30.11%。
  只對多方持股在除息（權）交易日課稅：稅 = 權重 × 應稅股利 ÷ 除息前一日收盤 × 稅率；現金股利 = 盈餘＋公積配息，股票股利依面額（每股配股元數）課稅。
  空方借券權益補償以稅前全額支付（含息報酬已反映），不抵稅。股利資料：TaiwanStockDividend（現金與股票除權息交易日）。
- 第一部分（必報）：fv5、fv5x 在 T0、T1、T2 的年化淨報酬、Sharpe、回撤，與每年股利稅負占組合資金比例。
- R1：換倉日 d 新建或加碼的多單（權重增加部分 Δw），若 AnnouncementDate ≤ d 且除息交易日在 (d, d + 20 個交易日]、且在同一持有期內，
  改在除息交易日收盤買進；期間以 β × 台指期多單暫代（期貨單邊 0.005%，進出各一次）。損益調整 = −Δw × (股票含息報酬 − β × 台指期報酬)
  − 期貨成本 + Δw × 應稅股利率 × 稅率（省下的稅）。補：只延後到第一個除息日；同一期內再有除息不處理。
- 指標：T2 與 T0 下 R1 相對 fv5 的年化淨報酬差、兩段稅後 Sharpe、受影響多單權重比例、每次換倉配對差（T2）Newey-West t（落後 2）。
- 通過：T2 年化差 ≥ +0.20 個百分點、兩段皆 > 0、兩段稅後 Sharpe 都不低於 fv5、配對差 t > 2，且 T0 損失 ≤ 0.10 個百分點。
- 補：只報告的 R2（延到除息後第 20 日）、R3（除息前賣出再買回）未做。
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
import fv5_family as ff  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
from sue_attention import nw_t  # noqa: E402

RATES = {"T0 不課稅": 0.0, "T1 合併計稅（淨 11.5% + 2.11%）": 0.1361, "T2 分開計稅（28% + 2.11%）": 0.3011}
FUT = 0.00005


def div_events(client, tickers) -> dict:
    """每檔：[(除息交易日, 應稅股利元／股, 公告日)]。現金與股票同日者合併。"""
    out = {}
    for t in tickers:
        d = client.get("TaiwanStockDividend", t.split(".")[0], "2005-01-01")
        if d.empty:
            continue
        ev = []
        for r in d.itertuples():
            ann = pd.to_datetime(getattr(r, "AnnouncementDate"), errors="coerce")
            cash = float(r.CashEarningsDistribution or 0) + float(r.CashStatutorySurplus or 0)
            stock = float(r.StockEarningsDistribution or 0) + float(r.StockStatutorySurplus or 0)
            cd = pd.to_datetime(r.CashExDividendTradingDate, errors="coerce")
            sd = pd.to_datetime(r.StockExDividendTradingDate, errors="coerce")
            if cash > 0 and cd == cd:
                ev.append((cd, cash, ann))
            if stock > 0 and sd == sd:
                ev.append((sd, stock, ann))
        if ev:
            e = pd.DataFrame(ev, columns=["ex", "amt", "ann"]).groupby("ex").agg(amt=("amt", "sum"), ann=("ann", "min")).reset_index()
            out[t] = e
    return out


def main():
    R, sched = ff.run_backtests()
    c = ff.LAST["c"]
    days = c.adj.index
    import borrow_capacity as bc
    raw = bc.raw_close(c)
    dv = div_events(c.client, c.tickers)
    tx = c.tx.reindex(days).fillna(0.0)
    # 每日每檔應稅股利率（除息日；÷ 前一日收盤）
    Y = pd.DataFrame(0.0, index=days, columns=c.tickers)
    ANN = {}
    for t, e in dv.items():
        for r in e.itertuples():
            k = int(days.searchsorted(r.ex))
            if 0 < k < len(days) and days[k] == r.ex:
                p = raw[t].iat[k - 1]
                if p == p and p > 0:
                    Y.iat[k, Y.columns.get_loc(t)] += r.amt / p
                    ANN[(t, k)] = r.ann
    start = sched[2]
    out = {}
    for name, key in (("fv5", (False, False, False)), ("fv5x", (True, True, True))):
        tranches = ff.LAST["wd"][key]
        drag_parts, r1_parts = {nm: [] for nm in RATES}, {nm: [] for nm in RATES}
        per, affected = [], []
        for wd in tranches:
            reb = list(wd)
            drag = pd.Series(0.0, index=days)
            r1_pre = pd.Series(0.0, index=days)
            r1_tax = pd.Series(0.0, index=days)
            prev = pd.Series(dtype=float)
            for n, d in enumerate(reb):
                nxt = reb[n + 1] if n + 1 < len(reb) else lp.HOLDOUT
                period = days[(days > d) & (days <= nxt)]
                if not len(period):
                    continue
                w = wd[d]
                lg = w[w > 0]
                drag.loc[period] += (Y.loc[period, lg.index] * lg).sum(axis=1)
                dw = (lg - prev.reindex(lg.index).fillna(0.0).clip(lower=0)).clip(lower=0)
                kd = int(days.searchsorted(d))
                lim_k = min(kd + 20, int(days.searchsorted(period[-1])))
                pre_sum, tax_sum, aff = 0.0, 0.0, 0.0
                for t, x in dw[dw > 0].items():
                    yy = Y[t].iloc[kd + 1:lim_k + 1]
                    hit = yy[yy > 0]
                    if not len(hit):
                        continue
                    ex = hit.index[0]
                    ke = int(days.searchsorted(ex))
                    ann = ANN.get((t, ke))
                    if ann is None or ann != ann or ann > d:
                        continue
                    rng = days[kd + 1:ke + 1]
                    b = float(c.betas.at[d, t]) if c.betas.at[d, t] == c.betas.at[d, t] else 1.0
                    adj = -x * (c.rets.loc[rng, t].fillna(0.0) - b * tx.loc[rng])
                    r1_pre.loc[rng] += adj
                    r1_pre.loc[rng[0]] -= 2 * FUT * x * abs(b)
                    r1_tax.loc[ex] += x * float(yy.loc[ex])
                    pre_sum += float(adj.sum()) - 2 * FUT * x * abs(b)
                    tax_sum += x * float(yy.loc[ex])
                    aff += x
                per.append({"d": d, "pre": pre_sum, "tax": tax_sum})
                affected.append(aff / max(float(lg.sum()), 1e-12))
                prev = w
            for nm, rate in RATES.items():
                drag_parts[nm].append(-drag * rate)
                r1_parts[nm].append(-drag * rate + r1_pre + r1_tax * rate)
        x0 = R["fv5" if name == "fv5" else "fv5x（E+S+V）"]
        x0 = x0[x0.index > start]
        agg = lambda parts: pd.concat(parts, axis=1).mean(axis=1).reindex(x0.index).fillna(0.0)  # noqa: E731
        res = {}
        for nm in RATES:
            a = x0 + agg(drag_parts[nm])
            b = x0 + agg(r1_parts[nm])
            yrs = len(x0) / 252
            res[nm] = {"base": hc.stats(a) | {"full": lp.sharpe(a.dropna())}, "r1": hc.stats(b) | {"full": lp.sharpe(b.dropna())},
                       "tax_yr": float(-agg(drag_parts[nm]).sum() / yrs), "base_s": a, "r1_s": b}
        pr = pd.DataFrame(per).groupby("d").sum().sort_index()
        out[name] = (res, pr, float(np.mean(affected)) if affected else 0.0)
    L = ["# I061 fv5 家族的稅後績效與除息日建倉規則（自動產生）", "",
         "由 [analysis/fv5_after_tax.py](../analysis/fv5_after_tax.py) 產生；設計見程式開頭（看結果前固定）。"
         "Sharpe 為扣成本與台指期對沖後，格式 2019–2022 / 2023–2026/04；稅負只計多方持股的股利（空方權益補償已含在含息報酬中、不抵稅）。研究結果，非投資建議。", "",
         "## 第一部分：稅後績效（必報）", "",
         "| 規格 | 稅率情境 | Sharpe | 全期 | 年化淨報酬 | 最大回撤 | 股利稅負（年化，占資金） |", "|---|---|---|---|---|---|---|"]
    for name, (res, pr, aff) in out.items():
        for nm, v in res.items():
            s = v["base"]
            L.append(f"| {name} | {nm} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.2%} | {s['mdd']:.1%} | {v['tax_yr']:.2%} |")
    res, pr, aff = out["fv5"]
    t2, t0 = list(RATES)[2], list(RATES)[0]
    d2 = res[t2]["r1"]["ann"] - res[t2]["base"]["ann"]
    d0 = res[t0]["r1"]["ann"] - res[t0]["base"]["ann"]
    s2 = res[t2]["r1_s"] - res[t2]["base_s"]
    seg = [float(s2[(s2.index < lp.SPLIT) == f].mean() * 252) for f in (True, False)]
    pair = pr["pre"] + pr["tax"] * RATES[t2]
    tp = nw_t(pair, 2)
    shok = res[t2]["r1"]["sh_oos"] >= res[t2]["base"]["sh_oos"] and res[t2]["r1"]["sh_is"] >= res[t2]["base"]["sh_is"]
    ok = d2 >= 0.002 and seg[0] > 0 and seg[1] > 0 and shok and tp > 2 and d0 >= -0.001
    L += ["", "## R1：新多單延到除息日收盤才買（fv5）", "",
          f"受影響的多單權重占多方的比例（每次換倉平均）：{aff:.1%}。", "",
          "| 情境 | fv5 年化淨報酬 | R1 年化淨報酬 | 差 | R1 Sharpe |", "|---|---|---|---|---|"]
    for nm in RATES:
        b, r = res[nm]["base"], res[nm]["r1"]
        L.append(f"| {nm} | {b['ann']:+.2%} | {r['ann']:+.2%} | {r['ann'] - b['ann']:+.2%} | {r['sh_oos']:.2f} / {r['sh_is']:.2f} |")
    L += ["", "## 判定（T2）", "",
          f"- 年化淨報酬差 ≥ +0.20 個百分點：{d2:+.2%} → {'✓' if d2 >= 0.002 else '✗'}",
          f"- 兩段皆 > 0：{seg[0]:+.2%} / {seg[1]:+.2%} → {'✓' if seg[0] > 0 and seg[1] > 0 else '✗'}",
          f"- 兩段稅後 Sharpe 不低於 fv5 → {'✓' if shok else '✗'}",
          f"- 每次換倉配對差 t > 2：{tp:.2f} → {'✓' if tp > 2 else '✗'}",
          f"- 稅前（T0）損失 ≤ 0.10 個百分點：{d0:+.2%} → {'✓' if d0 >= -0.001 else '✗'}", "",
          f"**結論：{'R1 通過（供使用者決定是否加入前瞻執行規則）' if ok else 'R1 未通過；第一部分稅後績效仍可作為實作參考'}**"]
    (ROOT / "docs" / "fv5_after_tax.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
