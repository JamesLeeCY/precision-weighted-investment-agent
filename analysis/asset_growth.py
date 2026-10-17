"""I020 資產成長異常（點子卡 research/ideas/I020-asset-growth.md，檢定計畫看結果前固定），附 I024 關係人資金往來的事件數前置檢查。

用法（於專案根目錄；資產負債表已快取）：
    .venv/Scripts/python analysis/asset_growth.py
輸出 docs/asset_growth.md。

設計（依點子卡；點子卡沒寫清楚、在看結果前補上的細節以「補」標示）：
- AG = 合併總資產_q ÷ 總資產_q−4 − 1（FinMind TaiwanStockBalanceSheet TotalAssets）；該季法定期限
  （Q1 5/15、Q2 8/14、Q3 11/14、Q4 次年 3/31）的次一交易日起可用，保持到下一季期限；每期 1%／99% 截尾；非金融股（產業不是「金融保險」「金融業」）。
- 主檢定：2019-01 ~ 2026-04 每月最後一個交易日的產業內 Spearman IC（−AG vs 之後 20、60 個交易日報酬；視窗須在 2026-05 前結束，補），
  兩段平均與 Newey-West t（20 日落後 1、60 日落後 3）。
- 增量：每月 Fama-MacBeth：20 日報酬 = a + b·AG + c·SUE + d·log 市值 + 產業固定效果（補：AG、SUE、log 市值用當月橫斷面百分位 − 0.5）。
- 驗證：第 501–1000 名同樣的 IC。
- 可交易：(a) 單獨：產業內 −AG 前 30% 做多、後 30% 放空（ls_turnover.ew_ls_buffer，q_in = 0.3、不含緩衝），借券條件 D（2 億）、
  每 3 個換倉日換倉三份錯開、台指期對沖，單邊 0.29625% ＋ 借券費；(b) 合成：fv5 的分數改為 2/3 × SUE 百分位 ＋ 1/3 × (−AG) 百分位
  （補：沒有 AG 的股票（含金融股）AG 百分位以 0.5 計），與 fv5 原版比較。
- 通過：(1) 20 日或 60 日 IC 兩段 > 0、全期 t > 2；(2) Fama-MacBeth b（−AG 方向）全期 t > 2、兩段同號；(3) 驗證樣本全期 IC 同號；
  (4) 單獨多空兩段 Sharpe > 0，或合成版兩段 Sharpe 都不低於 fv5 原版。
- I024 前置檢查（只數事件、不看報酬）：其他應收款—關係人 ÷ 總資產 ≥ 1% 且比去年同季增加 ≥ 0.5 個百分點；同公司 4 季內只取第一次；
  事件日 = 法定期限次一交易日；報告主樣本與驗證樣本兩段的事件數（任一段 < 40 則依點子卡不做主檢定）。
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
import corp_event_study as ce  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from sue_attention import nw_t  # noqa: E402

FIN = ("金融保險", "金融業")


def deadline(q: pd.Timestamp) -> pd.Timestamp:
    return {3: pd.Timestamp(q.year, 5, 15), 6: pd.Timestamp(q.year, 8, 14), 9: pd.Timestamp(q.year, 11, 14),
            12: pd.Timestamp(q.year + 1, 3, 31)}[q.month]


def balance(client, tickers) -> tuple[pd.DataFrame, pd.DataFrame]:
    ta, rp = {}, {}
    for t in tickers:
        d = client.get("TaiwanStockBalanceSheet", t.split(".")[0], "2017-01-01")
        if d.empty:
            continue
        d = d.assign(date=pd.to_datetime(d["date"]))
        p = d.pivot_table(index="date", columns="type", values="value", aggfunc="last")
        if "TotalAssets" in p:
            ta[t] = p["TotalAssets"].astype(float)
            rp[t] = p["OtherReceivablesDueFromRelatedParties"].astype(float) if "OtherReceivablesDueFromRelatedParties" in p else pd.Series(0.0, index=p.index)
    return pd.DataFrame(ta).sort_index(), pd.DataFrame(rp).sort_index()


def to_daily(qv: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    """季資料 → 每日可用值（法定期限次一交易日起）。"""
    rows = {}
    for q in qv.index:
        if q.month not in (3, 6, 9, 12):
            continue
        k = int(days.searchsorted(deadline(q), side="right"))
        if k < len(days):
            rows[days[k]] = qv.loc[q]
    return pd.DataFrame(rows).T.sort_index().reindex(days).ffill()


def sample_ag(S, client):
    sector = pd.Series({t: S.sector.get(t.split(".")[0], "NA") for t in S.tickers})
    nonfin = [t for t in S.tickers if sector[t] not in FIN]
    ta, rp = balance(client, nonfin)
    agq = ta / ta.shift(4) - 1
    ag = to_daily(agq, S.days).reindex(columns=S.tickers)
    return ag, sector, ta, rp


def month_ends(days, limit):
    s = pd.Series(days[:limit], index=days[:limit])
    me = s.groupby(s.index.to_period("M")).last()
    return [d for d in me if pd.Timestamp("2019-01-01") <= d < lp.HOLDOUT]


def winsor(x: pd.Series) -> pd.Series:
    x = x.dropna()
    if len(x) < 20:
        return x
    lo, hi = x.quantile([0.01, 0.99])
    return x.clip(lo, hi)


def ic_series(S, ag, sector, h):
    out = {}
    for d in month_ends(S.days, S.limit):
        k = int(S.days.searchsorted(d))
        if k + h >= S.limit:
            continue
        mem = S.member.iloc[k].to_numpy(bool)
        x = winsor(ag.iloc[k][mem])
        fwd = S.adj.iloc[k + h] / S.adj.iloc[k] - 1
        out[d] = lp.within_ic(-x, fwd, sector)
    return pd.Series(out).dropna()


def segs(x: pd.Series, lag: int) -> dict:
    f = lambda y: (float(y.mean()), nw_t(y, lag), len(y))  # noqa: E731
    return {"2019–2022": f(x[x.index < lp.SPLIT]), "2023–2026/04": f(x[x.index >= lp.SPLIT]), "全期": f(x)}


def fmt(x, pct=False) -> str:
    m, t, n = x
    return "—" if m != m else (f"{m:+.2%}" if pct else f"{m:+.3f}") + f"（{t:.1f}，{n}）"


def rp_events(ta, rp, S) -> pd.DataFrame:
    ratio = (rp.reindex(ta.index).fillna(0.0) / ta).where(ta > 0)
    hit = (ratio >= 0.01) & (ratio - ratio.shift(4) >= 0.005)
    rows = []
    for t in hit.columns:
        last = None
        for q in hit.index[hit[t].fillna(False).to_numpy(bool)]:
            if q.month not in (3, 6, 9, 12) or q < pd.Timestamp("2018-12-31") or q > pd.Timestamp("2025-12-31"):
                continue
            if last is not None and (q - last).days < 360:
                continue
            last = q
            k = int(S.days.searchsorted(deadline(q), side="right"))
            if k < S.limit and S.member.iloc[k].get(t, False):
                rows.append({"ticker": t, "q": q, "t0": S.days[k]})
    return pd.DataFrame(rows)


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    S = ce.Sample(client, 1, 500, mkt, tx)
    ag, sector, ta, rp = sample_ag(S, client)
    ic20, ic60 = ic_series(S, ag, sector, 20), ic_series(S, ag, sector, 60)
    # Fama-MacBeth（20 日）
    fm, corr = {}, {}
    for d in month_ends(S.days, S.limit):
        k = int(S.days.searchsorted(d))
        if k + 20 >= S.limit:
            continue
        mem = S.member.iloc[k].to_numpy(bool)
        df = pd.DataFrame({"y": S.adj.iloc[k + 20] / S.adj.iloc[k] - 1, "ag": winsor(ag.iloc[k][mem]), "sue": S.sue.iloc[k],
                           "lm": S.lmcap.iloc[k], "sec": sector}).dropna()
        if len(df) < 50:
            continue
        X = np.column_stack([np.ones(len(df)), -(df["ag"].rank(pct=True) - 0.5), df["sue"].rank(pct=True) - 0.5, df["lm"].rank(pct=True) - 0.5,
                             pd.get_dummies(df["sec"], drop_first=True, dtype=float).to_numpy()])
        beta, *_ = np.linalg.lstsq(X, df["y"].to_numpy(float), rcond=None)
        fm[d] = beta[1]
        corr[d] = df["ag"].rank().corr(df["sue"].rank())
    fm, corr = pd.Series(fm), pd.Series(corr)
    # 驗證
    V = ce.Sample(client, 501, 1000, mkt, tx)
    vag, vsec, vta, vrp = sample_ag(V, client)
    v20, v60 = ic_series(V, vag, vsec, 20), ic_series(V, vag, vsec, 60)
    # 可交易（fv5 架構）
    c = lp.prepare(500)
    sched = c.schedule
    fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
    close = bc.raw_close(c)
    cag = ag.reindex(index=c.adj.index, columns=c.tickers)
    sue = lp.leg_scores(c, "sue")

    def shortable_at(d, q):
        n_short = max(1, int(c.member.loc[d].sum() * q))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    def book(fn, q_in):
        parts = []
        for off in range(3):
            wd = {d: lt.ew_ls_buffer(fn(d), c.sector, shortable_at(d, q_in), q_in=q_in, q_keep=None) for d in sched[off::3]}
            parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)["ret"])
        x = pd.concat(parts, axis=1).mean(axis=1)
        x = x[x.index > sched[2]]
        return hc.stats(x) | {"full": lp.sharpe(x.dropna())}

    def neg_ag(d):
        x = winsor(cag.loc[d][c.member.loc[d].to_numpy(bool)])
        return -x

    def comp(d):
        s = sue[d].dropna()
        r_s = s.rank(pct=True)
        a = neg_ag(d).reindex(s.index).rank(pct=True).fillna(0.5)
        return 2 / 3 * r_s + 1 / 3 * a
    port = {"(a) 單獨 −AG（產業內前／後 30%）": book(neg_ag, 0.3), "fv5 原版（SUE）": book(lambda d: sue[d], 1 / 3),
            "(b) 合成：2/3 SUE ＋ 1/3 (−AG)": book(comp, 1 / 3)}
    # I024 前置檢查
    ev_m, ev_v = rp_events(ta, rp, S), rp_events(vta, vrp, V)
    cnt = lambda e: (int((e["t0"] < lp.SPLIT).sum()) if len(e) else 0, int((e["t0"] >= lp.SPLIT).sum()) if len(e) else 0)  # noqa: E731

    a20, a60, afm, av20, av60 = segs(ic20, 1), segs(ic60, 3), segs(fm, 1), segs(v20, 1), segs(v60, 3)
    L = ["# I020 資產成長異常（自動產生）", "",
         "由 [analysis/asset_growth.py](../analysis/asset_growth.py) 產生；設計見程式開頭（看結果前固定）。"
         "IC 為產業內 Spearman（−AG vs 之後報酬，−1～1，0 為無預測力；正值代表資產成長低的股票較好），括號為（Newey-West t 值，月份數）；"
         "Fama-MacBeth 係數為 −AG 百分位差 1 對應的 20 日報酬差；Sharpe 為扣成本與台指期對沖後，格式 2019–2022 / 2023–2026/04。研究結果，非投資建議。", "",
         f"AG 與 SUE 的平均橫斷面等級相關 {corr.mean():+.3f}。", "",
         "| 統計量 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         "| 主樣本 IC 20 日 | " + " | ".join(fmt(a20[s]) for s in a20) + " |",
         "| 主樣本 IC 60 日 | " + " | ".join(fmt(a60[s]) for s in a60) + " |",
         "| Fama-MacBeth −AG 係數（控制 SUE、市值、產業） | " + " | ".join(fmt(afm[s], True) for s in afm) + " |",
         "| 驗證樣本 IC 20 日 | " + " | ".join(fmt(av20[s]) for s in av20) + " |",
         "| 驗證樣本 IC 60 日 | " + " | ".join(fmt(av60[s]) for s in av60) + " |", "",
         "| 建構 | Sharpe | 全期 | 年化報酬 | 最大回撤 |", "|---|---|---|---|---|"]
    for k, s in port.items():
        L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} |")
    c1 = any(x["2019–2022"][0] > 0 and x["2023–2026/04"][0] > 0 and x["全期"][1] > 2 for x in (a20, a60))
    c2 = afm["全期"][1] > 2 and np.sign(afm["2019–2022"][0]) == np.sign(afm["2023–2026/04"][0])
    c3 = av20["全期"][0] > 0 or av60["全期"][0] > 0
    pa, pb, p0 = port["(a) 單獨 −AG（產業內前／後 30%）"], port["(b) 合成：2/3 SUE ＋ 1/3 (−AG)"], port["fv5 原版（SUE）"]
    c4 = (pa["sh_oos"] > 0 and pa["sh_is"] > 0) or (pb["sh_oos"] >= p0["sh_oos"] and pb["sh_is"] >= p0["sh_is"])
    m1, m2 = cnt(ev_m)
    v1, v2 = cnt(ev_v)
    L += ["", "## 判定", "",
          f"1. 20 日或 60 日 IC 兩段 > 0、全期 t > 2 → {'✓' if c1 else '✗'}",
          f"2. Fama-MacBeth 全期 t > 2、兩段同號：{fmt(afm['全期'], True)} → {'✓' if c2 else '✗'}",
          f"3. 驗證樣本方向相同（全期 IC > 0）：20 日 {fmt(av20['全期'])}、60 日 {fmt(av60['全期'])} → {'✓' if c3 else '✗'}",
          f"4. 單獨多空兩段 > 0（{pa['sh_oos']:.2f} / {pa['sh_is']:.2f}）或合成兩段不低於 fv5（{pb['sh_oos']:.2f} / {pb['sh_is']:.2f} vs "
          f"{p0['sh_oos']:.2f} / {p0['sh_is']:.2f}）→ {'✓' if c4 else '✗'}", "",
          f"**結論：{'通過' if c1 and c2 and c3 and c4 else ('訊號有效、可交易未通過' if c1 and c2 else '未通過')}**", "",
          "## I024 前置檢查：關係人資金占用事件數（只數事件，未看報酬）", "",
          "| 樣本 | 2019–2022 | 2023–2026/04 |", "|---|---|---|",
          f"| 前 500 名 | {m1} | {m2} |", f"| 第 501–1000 名 | {v1} | {v2} |", "",
          f"依點子卡：主樣本任一段 < 40 → {'不做主檢定，只能報告合併樣本方向' if min(m1, m2) < 40 else '事件數足夠，可進行主檢定'}。"]
    (ROOT / "docs" / "asset_growth.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
