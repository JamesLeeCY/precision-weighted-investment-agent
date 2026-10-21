"""I037 營收已知下的利潤率驚奇（點子卡 research/ideas/I037-operating-margin-surprise-given-revenue.md，檢定計畫看結果前固定）。

用法（於專案根目錄；FinMind 約 1,100 次，額度不足會自動等待）：
    .venv/Scripts/python analysis/margin_surprise.py
輸出 docs/margin_surprise.md。

設計（依點子卡；點子卡沒寫清楚、在看結果前補上的細節以「補」標示）：
- 樣本：前 500 名非金融股（產業不是「金融保險」「金融業」），驗證第 501–1000 名；事件日在 2019-01 ~ 2026-04，
  60 日視窗須在 2026-05 前結束（補：20 日 IC 用所有 20 日視窗在 2026-05 前結束的季）。兩段 2019–2022 / 2023–2026/04。
- 資料：FinMind TaiwanStockFinancialStatements（單季 Revenue、OperatingIncome、GrossProfit）；季營收年增率用月營收三個月加總。
- 訊號：OPM = 營業利益 ÷ 營收（營收 ≤ 0 剔除）；ΔOPM = OPM_q − OPM_(q−4)，|ΔOPM| > 50 個百分點剔除。
  每季、每產業做截面迴歸 ΔOPM = a + b·季營收年增率，取殘差（補：該季該產業少於 8 家者合併成一組「其他」再迴歸；
  季營收年增率先截在 ±100%）；MS = 殘差 ÷ 該公司過去 8 季 ΔOPM 標準差（不含當季、至少 4 季）。
  次要（只報告）：毛利率版本 MS_gm（同樣做法）。
- 時點：法定期限（Q1 5/15、Q2 8/14、Q3 11/14、Q4 隔年 3/31）的次一交易日為 +0，+1 收盤進場；成員以 +0 當日為準。
- 評估：每季一個截面，產業內 Spearman IC（MS vs 第 +2 ~ +21、+2 ~ +61 日報酬），季平均與 Newey-West t（落後 1）。
  Fama-MacBeth（60 日報酬）：MS、最新月營收 SUE、季營收年增率、前 20 日報酬、log 市值、帳面市值比（同季權益 ÷ 市值）、產業固定效果；
  補：各變數用當季橫斷面百分位 − 0.5，缺值以 0 計（MS 缺值的股票不納入）。
- 可交易（IC 與 Fama-MacBeth 都成立才做）：fv5 分數改為 SUE 與 MS 產業內百分位 0.75 / 0.25 加權（MS 缺值含金融股以 0.5 計；
  換倉日只用期限次一交易日 ≤ 換倉日的最新一季），其餘同 fv5（借券條件 D、每 3 個換倉日三份錯開、台指期對沖、單邊 0.29625% ＋ 借券費）。
- 通過（事前固定）：60 日 IC 兩段皆 > 0、全期 t > 2；Fama-MacBeth 控制 SUE 後 MS 全期 t > 2；驗證樣本 60 日 IC 同號；
  合成版兩段 Sharpe 都不低於 fv5。任一不成立即停止。
- 只報告：MS_gm、20 日 IC、電子與非電子分組。
研究結果，非投資建議。
"""
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
ELEC = ("半導體業", "電子零組件業", "電腦及週邊設備業", "光電業", "通信網路業", "電子通路業", "資訊服務業", "其他電子業")
DEADLINE = {3: (5, 15), 6: (8, 14), 9: (11, 14), 12: (3, 31)}
MIN_SECTOR = 8


def deadline(q: pd.Timestamp) -> pd.Timestamp:
    m, d = DEADLINE[q.month]
    return pd.Timestamp(q.year + (1 if q.month == 12 else 0), m, d)


def firm_quarters(client, sid: str) -> pd.DataFrame:
    fs = client.get("TaiwanStockFinancialStatements", sid, "2017-01-01")
    if fs.empty:
        return pd.DataFrame()
    p = fs.assign(date=pd.to_datetime(fs["date"])).pivot_table(index="date", columns="type", values="value", aggfunc="last")
    p = p[p.index.month.isin([3, 6, 9, 12])]
    if "Revenue" not in p or "OperatingIncome" not in p or p.empty:
        return pd.DataFrame()
    p = p.asfreq("QE-DEC")
    rev = p["Revenue"].astype(float).where(lambda x: x > 0)
    out = pd.DataFrame(index=p.index)
    for name, col in (("d_opm", "OperatingIncome"), ("d_gpm", "GrossProfit")):
        if col not in p:
            out[name], out[name + "_sd"] = np.nan, np.nan
            continue
        m = p[col].astype(float) / rev
        d = m - m.shift(4)
        out[name] = d.where(d.abs() <= 0.5)
        out[name + "_sd"] = out[name].shift(1).rolling(8, min_periods=4).std()
    mr = client.get("TaiwanStockMonthRevenue", sid, "2017-01-01")
    if not mr.empty:
        r = pd.Series(mr["revenue"].astype(float).to_numpy(),
                      index=pd.PeriodIndex([pd.Period(f"{y}-{m:02d}", "M") for y, m in zip(mr["revenue_year"], mr["revenue_month"])]))
        r = r[~r.index.duplicated(keep="last")]
        qs = r.groupby(r.index.asfreq("Q")).agg(["sum", "count"])
        qs = qs["sum"].where(qs["count"] == 3)
        qs.index = qs.index.to_timestamp(how="end").normalize()
        qs = qs.reindex(pd.period_range(qs.index.min(), qs.index.max(), freq="Q").to_timestamp(how="end").normalize())
        g = (qs / qs.shift(4) - 1).clip(-1, 1)
        out["rev_yoy"] = g.reindex(out.index.normalize()).to_numpy()
    else:
        out["rev_yoy"] = np.nan
    return out


def balance_equity(client, sid: str) -> pd.Series:
    d = client.get("TaiwanStockBalanceSheet", sid, "2017-01-01")
    if d.empty:
        return pd.Series(dtype=float)
    d = d[d["type"] == "Equity"].assign(date=lambda x: pd.to_datetime(x["date"]))
    return d.drop_duplicates("date", keep="last").set_index("date")["value"].astype(float)


def build(S, client) -> pd.DataFrame:
    """每檔每季一列：q、ticker、sector、d_opm、d_gpm、sd、rev_yoy、equity、k0（期限次一交易日）。"""
    rows = []
    for t in S.tickers:
        sec = S.sector.get(t.split(".")[0], "NA")
        if sec in FIN:
            continue
        f = firm_quarters(client, t.split(".")[0])
        if f.empty:
            continue
        eq = balance_equity(client, t.split(".")[0])
        f["equity"] = eq.reindex(f.index).to_numpy() if len(eq) else np.nan
        f = f.reset_index().rename(columns={"date": "q", "index": "q"})
        f["ticker"], f["sector"] = t, sec
        rows.append(f)
    df = pd.concat(rows, ignore_index=True)
    df["k0"] = [int(S.days.searchsorted(deadline(q), side="right")) for q in df["q"]]
    df = df[(df["k0"] < len(S.days))].copy()
    df["t0"] = S.days[df["k0"].to_numpy()]
    df = df[(df["t0"] >= "2019-01-01") & (df["t0"] < lp.HOLDOUT)]
    df = df[[bool(S.member.iat[k, S.col[t]]) for k, t in zip(df["k0"], df["ticker"])]].copy()
    for name in ("opm", "gpm"):
        df[f"ms_{name[0]}"] = np.nan
        for q, g in df.groupby("q"):
            g = g.dropna(subset=[f"d_{name}", "rev_yoy"])
            if len(g) < 10:
                continue
            grp = g["sector"].where(g.groupby("sector")["sector"].transform("size") >= MIN_SECTOR, "其他")
            for _, h in g.groupby(grp):
                if len(h) < 3:
                    continue
                X = np.column_stack([np.ones(len(h)), h["rev_yoy"].to_numpy(float)])
                b, *_ = np.linalg.lstsq(X, h[f"d_{name}"].to_numpy(float), rcond=None)
                res = h[f"d_{name}"] - X @ b
                sd = h[f"d_{name}_sd"]
                df.loc[h.index, f"ms_{name[0]}"] = (res / sd.where(sd > 0)).to_numpy()
    return df.rename(columns={"ms_o": "ms", "ms_g": "ms_gm"})


def attach_returns(S, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    j = np.array([S.col[t] for t in df["ticker"]])
    k = df["k0"].to_numpy()
    A = S.adj.to_numpy()
    for h, name in ((21, "r20"), (61, "r60")):
        ok = k + h < S.limit
        v = np.full(len(df), np.nan)
        v[ok] = A[k[ok] + h, j[ok]] / A[k[ok] + 1, j[ok]] - 1
        df[name] = v
    df["sue"] = [S.sue.iat[kk, jj] for kk, jj in zip(k, j)]
    df["lm"] = [S.lmcap.iat[kk, jj] for kk, jj in zip(k, j)]
    df["p20"] = [S.pre20.iat[kk, jj] for kk, jj in zip(k, j)]
    df["seg"] = np.where(df["t0"] < lp.SPLIT, "2019–2022", "2023–2026/04")
    return df


def ic_by_q(df, sig, ret, mask=None):
    out = {}
    d = df if mask is None else df[mask]
    for q, g in d.dropna(subset=[sig, ret]).groupby("t0"):
        out[q] = lp.within_ic(g.set_index("ticker")[sig], g.set_index("ticker")[ret], g.set_index("ticker")["sector"])
    return pd.Series(out).dropna()


def segs(x: pd.Series) -> dict:
    f = lambda y: (float(y.mean()), nw_t(y, 1), len(y))  # noqa: E731
    return {"2019–2022": f(x[x.index < lp.SPLIT]), "2023–2026/04": f(x[x.index >= lp.SPLIT]), "全期": f(x)}


def fmt(x, pct=False) -> str:
    m, t, n = x
    return "—" if m != m else (f"{m:+.2%}" if pct else f"{m:+.3f}") + f"（{t:.1f}，{n}）"


def fama_macbeth(df) -> pd.Series:
    out = {}
    for q, g in df.dropna(subset=["ms", "r60"]).groupby("t0"):
        if len(g) < 50:
            continue
        g = g.assign(bm=g["equity"] / np.exp(g["lm"]))
        r = lambda c: (g[c].rank(pct=True) - 0.5).fillna(0.0).to_numpy(float)  # noqa: E731
        X = np.column_stack([np.ones(len(g)), r("ms"), r("sue"), r("rev_yoy"), r("p20"), r("lm"), r("bm"),
                             pd.get_dummies(g["sector"], drop_first=True, dtype=float).to_numpy()])
        b, *_ = np.linalg.lstsq(X, g["r60"].to_numpy(float), rcond=None)
        out[q] = b[1]
    return pd.Series(out)


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    S = ce.Sample(client, 1, 500, mkt, tx)
    df = attach_returns(S, build(S, client))
    print(f"[I037] 主樣本 {len(df)} 列、MS 有值 {df['ms'].notna().sum()}", flush=True)
    V = ce.Sample(client, 501, 1000, mkt, tx)
    vf = attach_returns(V, build(V, client))
    ic60, ic20 = ic_by_q(df, "ms", "r60"), ic_by_q(df, "ms", "r20")
    fm = fama_macbeth(df)
    v60, v20 = ic_by_q(vf, "ms", "r60"), ic_by_q(vf, "ms", "r20")
    a60, a20, afm, av60, av20 = segs(ic60), segs(ic20), segs(fm), segs(v60), segs(v20)
    corr = df.dropna(subset=["ms", "sue"]).groupby("t0").apply(lambda g: g["ms"].rank().corr(g["sue"].rank())).mean()
    L = ["# I037 營收已知下的利潤率驚奇（自動產生）", "",
         "由 [analysis/margin_surprise.py](../analysis/margin_surprise.py) 產生；設計見程式開頭（看結果前固定）。"
         "IC 為產業內 Spearman（MS vs 法定期限次一交易日 +1 收盤起的報酬，−1～1，0 為無預測力），每季一個截面，括號為（Newey-West t 值，季數）；"
         "Fama-MacBeth 係數為 MS 百分位差 1 對應的 60 日報酬差；Sharpe 為扣成本與台指期對沖後，格式 2019–2022 / 2023–2026/04。研究結果，非投資建議。", "",
         f"主樣本 MS 有值 {df['ms'].notna().sum():,} 個公司季（每季平均 {df.groupby('t0')['ms'].count().mean():.0f} 家）；"
         f"MS 與 SUE 的平均截面等級相關 {corr:+.2f}。", "",
         "| 統計量 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         "| **主樣本 IC 60 日（主檢定）** | " + " | ".join(fmt(a60[s]) for s in a60) + " |",
         "| **Fama-MacBeth MS 係數（控制 SUE、季營收年增率、前 20 日報酬、市值、帳面市值比、產業）** | " + " | ".join(fmt(afm[s], True) for s in afm) + " |",
         "| 驗證樣本 IC 60 日 | " + " | ".join(fmt(av60[s]) for s in av60) + " |",
         "| 只報告：主樣本 IC 20 日 | " + " | ".join(fmt(a20[s]) for s in a20) + " |",
         "| 只報告：驗證樣本 IC 20 日 | " + " | ".join(fmt(av20[s]) for s in av20) + " |",
         "| 只報告：毛利率版 MS_gm IC 60 日 | " + " | ".join(fmt(v) for v in segs(ic_by_q(df, "ms_gm", "r60")).values()) + " |",
         "| 只報告：電子 IC 60 日 | " + " | ".join(fmt(v) for v in segs(ic_by_q(df, "ms", "r60", df["sector"].isin(ELEC))).values()) + " |",
         "| 只報告：非電子 IC 60 日 | " + " | ".join(fmt(v) for v in segs(ic_by_q(df, "ms", "r60", ~df["sector"].isin(ELEC))).values()) + " |", ""]
    c1 = a60["2019–2022"][0] > 0 and a60["2023–2026/04"][0] > 0 and a60["全期"][1] > 2
    c2 = afm["全期"][1] > 2
    c3 = av60["全期"][0] > 0
    c4 = None
    if c1 and c2:
        c = lp.prepare(500)
        sched = c.schedule
        fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
        quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
        close = bc.raw_close(c)
        sue = lp.leg_scores(c, "sue")
        ms = df.dropna(subset=["ms"]).sort_values("t0")

        def shortable_at(d):
            n_short = max(1, int(c.member.loc[d].sum() / 3))
            need = lt.K_CAPITAL / n_short / close.loc[d]
            return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

        def comp(d):
            s = sue[d].dropna()
            sec = c.sector.reindex(s.index)
            known = ms[ms["t0"] <= d].drop_duplicates("ticker", keep="last").set_index("ticker")["ms"].reindex(s.index)
            ps = s.groupby(sec).rank(pct=True)
            pm = known.groupby(sec).rank(pct=True).fillna(0.5)
            return 0.75 * ps + 0.25 * pm

        def book(fn):
            parts = []
            for off in range(3):
                wd = {d: lt.ew_ls_buffer(fn(d), c.sector, shortable_at(d), q_keep=None) for d in sched[off::3]}
                parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)["ret"])
            x = pd.concat(parts, axis=1).mean(axis=1)
            x = x[x.index > sched[2]]
            return hc.stats(x) | {"full": lp.sharpe(x.dropna())}
        port = {"fv5 原版（SUE）": book(lambda d: sue[d]), "合成：0.75 SUE ＋ 0.25 MS": book(comp)}
        L += ["| 建構 | Sharpe | 全期 | 年化報酬 | 最大回撤 |", "|---|---|---|---|---|"]
        for k, s in port.items():
            L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} |")
        pb, p0 = port["合成：0.75 SUE ＋ 0.25 MS"], port["fv5 原版（SUE）"]
        c4 = pb["sh_oos"] >= p0["sh_oos"] and pb["sh_is"] >= p0["sh_is"]
        L.append("")
    mark = lambda b: "—（未執行）" if b is None else ("✓" if b else "✗")  # noqa: E731
    L += ["## 判定", "",
          f"1. 60 日 IC 兩段 > 0、全期 t > 2 → {mark(c1)}",
          f"2. Fama-MacBeth 控制 SUE 後 MS 全期 t > 2：{fmt(afm['全期'], True)} → {mark(c2)}",
          f"3. 驗證樣本 60 日 IC 同號：{fmt(av60['全期'])} → {mark(c3)}",
          f"4. 合成兩段 Sharpe 不低於 fv5 → {mark(c4)}{'（1、2 未全部成立，依點子卡停止）' if c4 is None else ''}", "",
          f"**結論：{'通過' if c1 and c2 and c3 and c4 else '未通過'}**"]
    (ROOT / "docs" / "margin_surprise.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
