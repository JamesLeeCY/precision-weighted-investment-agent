"""I015 每月自結損益驚奇的檢定（點子卡 research/ideas/I015-monthly-self-reported-earnings-surprise.md，檢定計畫看結果前固定）。

用法（於專案根目錄；先執行 fetch_self_earnings.py 與 self_earnings_parse.py）：
    .venv/Scripts/python analysis/self_earnings_events.py
輸出 docs/self_earnings_events.md。

設計（依點子卡；點子卡沒寫清楚、在看結果前補上的細節以「補」標示）：
- 資料：data_cache/events/self_earnings_series.csv（每家公司每月一個數字；稅後涵蓋率 ≥ 80% 的公司用當月稅後、其餘用稅前）。
- ESUE =（本月 − 去年同月 − 過去 24 個月年差平均）÷ 年差標準差（與營收 SUE 同一公式：只用過去、最少 12 個年差），
  且公告月份往回 24 個月都有數字（連續公告）才計算。
- 事件時點：數字來源公告（第一則有數字、非更正者）的發言日期與時間；13:30 以後發言者事件日 0 為下一個交易日。
  第 +1 日收盤進場，視窗 CAR[+2, +21]（個股 − β × 加權指數含息）。事件日 2019-01 ~ 2026-04，且視窗在 2026-05 前結束（補）。
- 樣本：主樣本 = 事件日為市值前 500 名成員；驗證 = 第 501–1000 名（補：股票池只排到 1,000 名）。兩段 2019–2022、2023–2026/04。
- 主檢定：每個公告月份（事件日所在月）把當月有 ESUE 的公司依 ESUE 分三組（至少 6 家），前三分之一 − 後三分之一的平均 CAR；
  t 值 = 各月份差額的平均 ÷ 標準誤（等同依月份群集）。
- 輔助 (a)：事件層級迴歸 CAR = a + b·ESUE + c·SUE + 產業固定效果，依月份群集；ESUE、SUE 轉成全樣本百分位（−0.5 ~ +0.5）（補），
  SUE = 同一資料月份的營收 SUE（FinMind 月營收，與本專案 SUE 相同公式）。
- 輔助 (b)：非金融公司（補：產業不是「金融保險」「金融業」者）用 corp_event_study.matched 算配對差額
  （同日、同產業、SUE 與事件前 60 日報酬三分位相同、前後 21 個交易日內沒有自結損益公告的股票），報告前、後三分之一與相減。
- 可交易 (4a)：金融股（產業為「金融保險」「金融業」）月度多空。補：每月 16 日（或之後第一個交易日）收盤用當月已公告的 ESUE 分三組，
  做多前三分之一、放空後三分之一（各邊等權、各 1 倍），持有到下個月換倉；放空須通過借券條件 D（2 億資金、同 borrow_capacity.py），
  台指期對沖剩餘 β；單邊成本 0.29625%＋借券費。
- 可交易 (4b)：fv5 建構的做多名單排除過去 22 個交易日內 ESUE 屬當月後三分之一的股票（corp_event_study.fv5_filter）。
- 通過：(1) 主檢定兩段皆 > 0、全期 t > 2；(2) 迴歸 ESUE 係數全期 t > 2 且兩段同號；(3) 驗證樣本方向相同；
  (4) 多空扣成本後 Sharpe > 0，或濾網版兩段 Sharpe 不低於 fv5 基準。(1)(2) 成立才算訊號有效，(4) 決定是否可用。
- 穩健性（只報告）：排除主旨含「注意」「要求」「補充」的公告；只看金融股；只看非金融股。
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
import dividend_surprise as dsu  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import self_earnings_parse as sp  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from data.revenue_signal import revenue_surprise  # noqa: E402

EV = ROOT / "data_cache" / "events"
WIN = (2, 21)
FIN = ("金融保險", "金融業")
K_SHORT = 2e8


def esue_table(client) -> pd.DataFrame:
    s = pd.read_csv(EV / "self_earnings_series.csv", dtype={"stock_id": str, "spoke_time": str}, parse_dates=["date"])
    out = []
    for sid, g in sp.esue(s).groupby("stock_id"):
        g = g.assign(p=pd.PeriodIndex(g["data_ym"], freq="M")).set_index("p").sort_index()
        rev = client.get("TaiwanStockMonthRevenue", sid, "2015-01-01")
        if not rev.empty:
            rs = revenue_surprise(rev).set_index("avail_month")["sue"]
            g["sue"] = [rs.get((p + 1).to_timestamp(), np.nan) for p in g.index]
        else:
            g["sue"] = np.nan
        out.append(g.reset_index(drop=True))
    e = pd.concat(out, ignore_index=True)
    # 13:30 以後發言 → 下一個交易日；先把日期往後推一天，Sample.events 用 searchsorted(left) 取當日或之後第一個交易日
    late = e["spoke_time"].astype(str).str.zfill(6) >= "133000"
    e["date_raw"] = e["date"]
    e["date"] = e["date"] + pd.to_timedelta(late.astype(int), unit="D")
    e = e[e["esue"].notna() & (e["date"] >= "2019-01-01") & (e["date"] < lp.HOLDOUT)]
    return e.reset_index(drop=True)


def attach(S: ce.Sample, e: pd.DataFrame) -> pd.DataFrame:
    ev = S.events(e)
    ev = ev[ev["k0"] + WIN[1] < S.limit].copy()
    ev["car"] = [float(S.car(S.col[t], k + WIN[0], k + WIN[1])) for t, k in zip(ev["ticker"], ev["k0"])]
    ev["month"] = ev["t0"].dt.to_period("M")
    ev["sector"] = [S.sector.get(t.split(".")[0], "NA") for t in ev["ticker"]]
    ev["fin"] = ev["sector"].isin(FIN)
    ev["grp"] = -1
    for _, g in ev.groupby("month"):
        ev.loc[g.index, "grp"] = ce.terciles(g["esue"].to_numpy(float), np.ones(len(g), bool))
    return ev


def spread(ev: pd.DataFrame, col: str = "car") -> pd.Series:
    """每個月份：前三分之一 − 後三分之一的平均。"""
    out = {}
    for m, g in ev[ev["grp"] >= 0].groupby("month"):
        hi, lo = g.loc[g["grp"] == 2, col].dropna(), g.loc[g["grp"] == 0, col].dropna()
        if len(hi) and len(lo):
            out[m] = hi.mean() - lo.mean()
    return pd.Series(out, dtype=float)


def tstat(x: pd.Series) -> tuple[float, float, int]:
    x = x.dropna()
    if len(x) < 5:
        return (float(x.mean()) if len(x) else float("nan")), float("nan"), len(x)
    return float(x.mean()), float(x.mean() / x.std(ddof=1) * math.sqrt(len(x))), len(x)


def segs(ev: pd.DataFrame, f) -> dict:
    return {"2019–2022": f(ev[ev["seg"] == "2019–2022"]), "2023–2026/04": f(ev[ev["seg"] == "2023–2026/04"]), "全期": f(ev)}


def regress(ev: pd.DataFrame) -> tuple[float, float, int]:
    df = ev.dropna(subset=["car", "esue", "sue"]).copy()
    if len(df) < 30:
        return float("nan"), float("nan"), len(df)
    df["r_e"] = df["esue"].rank(pct=True) - 0.5
    df["r_s"] = df["sue"].rank(pct=True) - 0.5
    fe = pd.get_dummies(df["sector"], drop_first=True, dtype=float)
    X = np.column_stack([np.ones(len(df)), df[["r_e", "r_s"]].to_numpy(float), fe.to_numpy(float)])
    beta, se = dsu.ols_cluster(df["car"].to_numpy(float), X, df["month"].astype(str).to_numpy())
    return float(beta[1]), float(beta[1] / se[1]), len(df)


def fmt3(x) -> str:
    m, t, n = x
    return "—" if m != m else (f"{m:+.2%}（{t:.1f}，{n}）" if t == t else f"{m:+.2%}（—，{n}）")


def fmtb(x) -> str:
    b, t, n = x
    return "—" if b != b else f"{b:+.2%}（{t:.1f}，{n}）"


def fin_long_short(S: ce.Sample, ev: pd.DataFrame, client) -> dict:
    fee = hc.lending_fees(client, S.tickers, S.days)
    quota, lend60 = bc.load_short_data(client, S.tickers, S.days)
    f = ev[ev["fin"]]
    days = S.days[: S.limit]
    sched = []
    for m in pd.period_range("2019-01", "2026-04", freq="M"):
        k = int(days.searchsorted(pd.Timestamp(m.year, m.month, 16)))
        if k < len(days):
            sched.append(days[k])
    wd, n_l, n_s, blocked = {}, [], [], 0
    for d in sched:
        g = f[(f["t0"].dt.to_period("M") == d.to_period("M")) & (f["k0"] + 1 <= days.searchsorted(d))]   # 第 +1 日收盤以前已知
        g = g.drop_duplicates("ticker", keep="last")
        w = pd.Series(dtype=float)
        if len(g) >= 6:
            q = ce.terciles(g["esue"].to_numpy(float), np.ones(len(g), bool))
            longs, shorts = list(g["ticker"][q == 2]), list(g["ticker"][q == 0])
            ok = []
            for t in shorts:
                j = S.col[t]
                kk = int(S.days.searchsorted(d))
                px = S.close.iat[kk, j]
                need = K_SHORT / 2 / max(len(shorts), 1) / px if px > 0 else np.inf
                fe_ = fee.iat[kk, j]
                if lend60.iat[kk, j] > 0 and quota.iat[kk, j] >= need and need <= bc.DEPTH_FRAC * lend60.iat[kk, j] and fe_ == fe_ and fe_ <= bc.FEE_MAX:
                    ok.append(t)
            blocked += len(shorts) - len(ok)
            if longs and ok:
                w = pd.concat([pd.Series(1 / len(longs), index=longs), pd.Series(-1 / len(ok), index=ok)])
                n_l.append(len(longs))
                n_s.append(len(ok))
        wd[d] = w
    sim = hc.simulate_weights(wd, S.rets, S.betas, S.tx, sched, fee=fee)
    st = hc.stats(sim["ret"], sim)
    return st | {"n_long": float(np.mean(n_l)) if n_l else 0.0, "n_short": float(np.mean(n_s)) if n_s else 0.0, "blocked": blocked,
                 "months": len(n_l)}


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    e = esue_table(client)
    L = ["# I015 每月自結損益驚奇（自動產生）", "",
         "由 [analysis/self_earnings_events.py](../analysis/self_earnings_events.py) 產生；設計見程式開頭（看結果前固定）。"
         "CAR = 第 +2 ~ +21 個交易日累積異常報酬（個股 − β × 加權指數含息）；「前 − 後」= 同一公告月份 ESUE 前三分之一 − 後三分之一的平均 CAR；"
         "括號為（t 值，月份數或事件數）。研究結果，非投資建議。", "",
         f"有 ESUE 的公告（2019-01 ~ 2026-04 事件日）：{len(e):,} 則、{e['stock_id'].nunique()} 家。", ""]
    res = {}
    S_main = None
    for name, (lo, hi) in (("前 500 名（主樣本）", (1, 500)), ("第 501–1000 名（驗證）", (501, 1000))):
        S = ce.Sample(client, lo, hi, mkt, tx)
        ev = attach(S, e)
        res[name] = ev
        if lo == 1:
            S_main = S
        L += [f"## {name}", "",
              f"事件 {len(ev):,} 則、{ev['ticker'].nunique()} 家（金融股 {ev.loc[ev['fin'], 'ticker'].nunique()} 家）；"
              f"每月平均 {ev.groupby('month').size().mean():.1f} 家。", "",
              "| 統計量 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|"]
        sp = segs(ev, lambda x: tstat(spread(x)))
        L.append("| 前 − 後（主檢定） | " + " | ".join(fmt3(v) for v in sp.values()) + " |")
        for lab, gq in (("前三分之一 CAR", 2), ("中間 CAR", 1), ("後三分之一 CAR", 0)):
            L.append(f"| {lab} | " + " | ".join(fmt3(v) for v in segs(ev, lambda x: tstat(x[x['grp'] == gq].groupby('month')['car'].mean())).values()) + " |")
        rg = segs(ev, regress)
        L.append("| 迴歸 ESUE 係數（控制 SUE、產業） | " + " | ".join(fmtb(v) for v in rg.values()) + " |")
        for lab, sub in (("前 − 後：只看金融股", ev[ev["fin"]]), ("前 − 後：只看非金融股", ev[~ev["fin"]]),
                         ("前 − 後：排除主旨含注意／要求／補充", ev[~ev["subject"].str.contains("注意|要求|補充")])):
            sub = sub.copy()
            sub["grp"] = -1
            for _, g in sub.groupby("month"):
                sub.loc[g.index, "grp"] = ce.terciles(g["esue"].to_numpy(float), np.ones(len(g), bool))
            L.append(f"| {lab} | " + " | ".join(fmt3(v) for v in segs(sub, lambda x: tstat(spread(x))).values()) + " |")
        L.append("")
        res[name + "_sp"], res[name + "_rg"] = sp, rg

    # (b) 非金融公司配對
    ev = res["前 500 名（主樣本）"]
    nf = ev[~ev["fin"]].copy()
    allev = S_main.events(e)
    m = ce.matched(S_main, nf, allev, {"CAR": WIN}, exclude_span=21)
    L += ["## 非金融公司配對差額（主樣本，只報告）", "",
          f"非金融事件 {len(m):,} 則，有配對者 {int((m['n_ctrl'] > 0).sum()):,} 則。配對差額 = 事件 CAR − 配對 CAR。", "",
          "| 分組 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|"]
    for lab, gq in (("前三分之一", 2), ("後三分之一", 0)):
        L.append(f"| {lab} | " + " | ".join(fmt3(v) for v in segs(m, lambda x: tstat(x[x['grp'] == gq].groupby('month')['CAR_diff'].mean())).values()) + " |")
    L.append("| 前 − 後 | " + " | ".join(fmt3(v) for v in segs(m, lambda x: tstat(spread(x, "CAR_diff"))).values()) + " |")
    L.append("")

    # (4a) 金融股多空
    ls = fin_long_short(S_main, ev, client)
    L += ["## 可交易版本", "",
          f"**(4a) 金融股月度多空**（每月 16 日換倉；平均做多 {ls['n_long']:.1f} 檔、放空 {ls['n_short']:.1f} 檔；{ls['months']} 個月有部位；"
          f"借券條件不通過而不放空 {ls['blocked']} 檔次）", "",
          "| Sharpe 2019–2022 | Sharpe 2023–2026/04 | 年化報酬 | 年化波動 | 最大回撤 | 年換手 | 年借券費 |", "|---|---|---|---|---|---|---|",
          f"| {ls['sh_oos']:.2f} | {ls['sh_is']:.2f} | {ls['ann']:+.1%} | {ls['vol']:.1%} | {ls['mdd']:.1%} | {ls['turnover']:.1f} | {ls['borrow']:.2%} |", ""]

    # (4b) fv5 濾網
    bad = ev[ev["grp"] == 0][["ticker", "t0"]]
    fv = ce.fv5_filter(bad, 22)
    b0, b1 = fv["fv5 建構（基準）"], fv["濾網版"]
    L += [f"**(4b) fv5 濾網**：做多名單排除過去 22 個交易日內 ESUE 屬後三分之一者（平均排除做多權重 {fv['share']:.1%}）", "",
          "| 版本 | Sharpe 2019–2022 | Sharpe 2023–2026/04 | 全期 | 年化報酬 | 最大回撤 |", "|---|---|---|---|---|---|",
          f"| fv5 建構（基準） | {b0['sh_oos']:.2f} | {b0['sh_is']:.2f} | {b0['full']:.2f} | {b0['ann']:+.1%} | {b0['mdd']:.1%} |",
          f"| 濾網版 | {b1['sh_oos']:.2f} | {b1['sh_is']:.2f} | {b1['full']:.2f} | {b1['ann']:+.1%} | {b1['mdd']:.1%} |", ""]

    # 判定
    sp, rg = res["前 500 名（主樣本）_sp"], res["前 500 名（主樣本）_rg"]
    vs = res["第 501–1000 名（驗證）_sp"]["全期"]
    c1 = sp["2019–2022"][0] > 0 and sp["2023–2026/04"][0] > 0 and sp["全期"][1] > 2
    c2 = rg["全期"][1] > 2 and np.sign(rg["2019–2022"][0]) == np.sign(rg["2023–2026/04"][0])
    c3 = vs[0] > 0
    c4 = (ls["sh_oos"] > 0 and ls["sh_is"] > 0) or (b1["sh_oos"] >= b0["sh_oos"] and b1["sh_is"] >= b0["sh_is"])
    L += ["## 判定", "",
          f"1. 主檢定兩段 > 0、全期 t > 2：{fmt3(sp['2019–2022'])}、{fmt3(sp['2023–2026/04'])}、全期 {fmt3(sp['全期'])} → {'✓' if c1 else '✗'}",
          f"2. 迴歸 ESUE 係數全期 t > 2 且兩段同號：{fmtb(rg['2019–2022'])}、{fmtb(rg['2023–2026/04'])}、全期 {fmtb(rg['全期'])} → {'✓' if c2 else '✗'}",
          f"3. 驗證樣本方向相同：{fmt3(vs)} → {'✓' if c3 else '✗'}",
          f"4. 多空兩段 Sharpe > 0（{ls['sh_oos']:.2f} / {ls['sh_is']:.2f}）或濾網版兩段不低於 fv5（{b1['sh_oos']:.2f} / {b1['sh_is']:.2f} vs "
          f"{b0['sh_oos']:.2f} / {b0['sh_is']:.2f}）→ {'✓' if c4 else '✗'}", "",
          f"**結論：{'訊號有效' if c1 and c2 else '訊號未通過'}{'、可交易版本通過' if c1 and c2 and c4 else ''}**"]
    (ROOT / "docs" / "self_earnings_events.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
