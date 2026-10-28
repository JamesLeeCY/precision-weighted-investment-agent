"""I081 研發密度（研發費用 ÷ 市值）的年度訊號（點子卡 research/ideas/I081-rd-intensity-annual-low-turnover.md，檢定計畫看結果前固定）。

用法（於專案根目錄；先跑 analysis/fetch_rd.py）：
    .venv/Scripts/python analysis/rd_intensity.py
輸出 docs/rd_intensity.md。

設計（依點子卡；補充以「補」標示）：
- 研發費用：公開資訊觀測站綜合損益表年度數（data_cache/events/rd_expense.csv，千元）。
- 訊號：形成年 Y = 2019 ~ 2025，形成日為 Y 年 4 月第 2 個交易日；RDME = Y−1 年度研發費用 ÷ Y 年 3 月最後一個交易日市值，固定 12 個月到下一個形成日。
- 樣本：月底為成員、上一年度研發費用 > 0；每個月底只用研發公司數 ≥ 5 家的產業。前 500 名為主樣本，第 501–1000 名為確認樣本。
- H1：每月最後一個交易日（2019-04 ~ 2026-04，且之後 20 個交易日在 2026-05 前結束），被解釋變數 = 之後 20 個交易日產業調整報酬的產業內百分位 − 0.5；
  自變數 RDME 與控制（log 市值、淨值市價比、12-1 動能、最新月營收 SUE）皆為產業內百分位 − 0.5；Fama-MacBeth、Newey-West 落後 3。
  補：產業調整報酬以月底該產業研發樣本的平均扣除；淨值市價比用法定期限後可得的最近一季股東權益 ÷ 前一日市值。
  兩段 2019-04 ~ 2022 / 2023 ~ 2026/04。通過：全期 t ≥ 2.58（正向）、兩段皆 > 0 且第二段 t ≥ 1.5、第 501–1000 名 > 0 且 t ≥ 2.0。
- H2 只在 H1 通過時做（本程式只在 H1 通過時提示）。
- 只報告：研發／營收版本；研發大幅增加事件（研發年增 ≥ 5% 且研發／年底總資產 ≥ 5%）之後 250 個交易日相對同產業非事件研發公司的 CAR；
  電子業 vs 非電子業；RDME 與 SUE、淨值市價比的每月等級相關；產業內前／後 1/3 等權多空每年換倉的年換手。
研究結果，非投資建議。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import asset_growth as agm  # noqa: E402
import corp_event_study as ce  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import margin_surprise as msm  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from sue_attention import nw_t  # noqa: E402

RD = ROOT / "data_cache" / "events" / "rd_expense.csv"
SEG = ("2019-04 ~ 2022", "2023 ~ 2026/04")
ELEC = ("半導體業", "電子零組件業", "電腦及週邊設備業", "光電業", "通信網路業", "電子通路業", "資訊服務業", "其他電子業")


def rd_table() -> pd.DataFrame:
    r = pd.read_csv(RD, dtype={"stock_id": str}).drop_duplicates(["stock_id", "fy"], keep="first")
    return r.set_index(["stock_id", "fy"])


def formations(days) -> dict:
    """{形成年 Y: (形成日位置, 3 月最後交易日位置)}。"""
    out = {}
    for y in range(2019, 2026):
        apr = np.flatnonzero((days.year == y) & (days.month == 4))
        mar = np.flatnonzero((days.year == y) & (days.month == 3))
        out[y] = (int(apr[1]), int(mar[-1]))
    return out


def signals(S, rd: pd.DataFrame, form: dict) -> dict:
    """{形成年: DataFrame[rdme, rds, rd, rd_prev]}（只含研發 > 0 的股票）。"""
    out = {}
    mc = np.exp(S.lmcap)
    for y, (k, km) in form.items():
        rows = {}
        for t in S.tickers:
            sid = t.split(".")[0]
            if (sid, y - 1) not in rd.index:
                continue
            x = rd.loc[(sid, y - 1)]
            cap = mc.iloc[km + 1][t] if km + 1 < len(mc) else np.nan
            if not (x["rd"] > 0) or not (cap > 0):
                continue
            prev = rd.loc[(sid, y - 2), "rd"] if (sid, y - 2) in rd.index else np.nan
            rows[t] = {"rdme": x["rd"] * 1000 / cap, "rds": x["rd"] / x["revenue"] if x["revenue"] > 0 else np.nan,
                       "rd": x["rd"], "rd_prev": prev}
        out[y] = pd.DataFrame(rows).T
    return out


def equity_daily(S, client) -> pd.DataFrame:
    eq = {}
    for t in S.tickers:
        e = msm.balance_equity(client, t.split(".")[0])
        if len(e):
            eq[t] = e[e.index.month.isin([3, 6, 9, 12])]
    return agm.to_daily(pd.DataFrame(eq).sort_index(), S.days).reindex(columns=S.tickers)


def panel(S, sig: dict, form: dict, equity: pd.DataFrame) -> pd.DataFrame:
    days = S.days
    A = S.adj
    sec = pd.Series({t: S.sector.get(t.split(".")[0], "NA") for t in S.tickers})
    starts = sorted((days[k], y) for y, (k, _) in form.items())
    me = pd.Series(days, index=days).groupby(days.to_period("M")).max()
    rows = []
    for d in me:
        if d < starts[0][0]:
            continue
        k = int(days.searchsorted(d))
        if k + 20 >= S.limit:
            continue
        y = [yy for dd, yy in starts if dd <= d][-1]
        g = sig[y]
        mem = S.member.iloc[k]
        tk = [t for t in g.index if mem.get(t, False)]
        df = pd.DataFrame({"rdme": g.loc[tk, "rdme"], "rds": g.loc[tk, "rds"], "sector": sec.reindex(tk),
                           "fwd": A.iloc[k + 20].reindex(tk) / A.iloc[k].reindex(tk) - 1,
                           "lm": S.lmcap.iloc[k].reindex(tk), "mom": (A.iloc[k - 21] / A.iloc[k - 252] - 1).reindex(tk),
                           "sue": S.sue.iloc[k].reindex(tk),
                           "bm": equity.iloc[k].reindex(tk).astype(float) / np.exp(S.lmcap.iloc[k].reindex(tk))}, index=tk)
        df = df.dropna(subset=["fwd", "rdme"])
        df = df[df.groupby("sector")["rdme"].transform("size") >= 5]
        df["fwd"] = df["fwd"] - df.groupby("sector")["fwd"].transform("mean")
        df["d"], df["y"] = d, y
        rows.append(df.rename_axis("ticker").reset_index())
    return pd.concat(rows, ignore_index=True)


def fm(P, var="rdme", controls=True) -> pd.Series:
    out = {}
    for d, g in P.groupby("d"):
        g = g.dropna(subset=[var])
        if len(g) < 30:
            continue
        sec = g["sector"]
        r = lambda c: (g[c].groupby(sec).rank(pct=True) - 0.5).fillna(0.0).to_numpy(float)  # noqa: E731
        cols = [r(var)] + ([r("lm"), r("bm"), r("mom"), r("sue")] if controls else [])
        X = np.column_stack([np.ones(len(g))] + cols)
        b, *_ = np.linalg.lstsq(X, r("fwd"), rcond=None)
        out[d] = b[1]
    s = pd.Series(out, dtype=float)
    s.index = pd.DatetimeIndex(s.index)
    return s.sort_index()


def segs(x):
    f = lambda y: (float(y.mean()), nw_t(y, 3), len(y)) if len(y) > 4 else (np.nan, np.nan, len(y))  # noqa: E731
    return {SEG[0]: f(x[x.index < lp.SPLIT]), SEG[1]: f(x[x.index >= lp.SPLIT]), "全期": f(x)}


def fmt(v):
    return "—" if v[0] != v[0] else f"{v[0]:+.4f}（{v[1]:.2f}，{v[2]}）"


def events_car(S, sig, form, client) -> tuple[float, float, int, int]:
    """研發大幅增加事件：形成日起 250 個交易日（只到 2026-05 前）報酬 − 同產業非事件研發公司平均；回傳（平均, 依形成年的 t, 事件數, 年數）。"""
    sec = pd.Series({t: S.sector.get(t.split(".")[0], "NA") for t in S.tickers})
    A = S.adj
    per_year, n = {}, 0
    for y, (k, _) in form.items():
        g = sig[y]
        mem = S.member.iloc[k]
        g = g[[mem.get(t, False) for t in g.index]]
        if g.empty:
            continue
        ta = {}
        for t in g.index:
            b = client.get("TaiwanStockBalanceSheet", t.split(".")[0], "2017-01-01")
            if b.empty:
                continue
            b = b[(b["type"] == "TotalAssets") & (b["date"] == f"{y - 1}-12-31")]
            if len(b):
                ta[t] = float(b["value"].iloc[-1])
        g = g.assign(ta=pd.Series(ta), sector=sec.reindex(g.index))
        e = end = min(k + 250, S.limit - 1)
        if end - k < 60:
            continue
        g["ret"] = A.iloc[e].reindex(g.index) / A.iloc[k].reindex(g.index) - 1
        g["ev"] = (g["rd"] / g["rd_prev"] - 1 >= 0.05) & (g["rd"] * 1000 / g["ta"] >= 0.05)
        diffs = []
        for s, h in g.dropna(subset=["ret"]).groupby("sector"):
            ctl = h.loc[~h["ev"], "ret"]
            if len(ctl) == 0:
                continue
            diffs += list(h.loc[h["ev"], "ret"] - ctl.mean())
        if diffs:
            per_year[y] = float(np.mean(diffs))
            n += len(diffs)
    x = pd.Series(per_year)
    t = float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 1 else np.nan
    return float(x.mean()), t, n, len(x)


def ls_turnover(S, sig, form) -> float:
    sec = pd.Series({t: S.sector.get(t.split(".")[0], "NA") for t in S.tickers})
    allok = pd.Series(True, index=S.tickers)
    prev, tos = None, []
    for y, (k, _) in sorted(form.items()):
        g = sig[y]
        mem = S.member.iloc[k]
        s = g["rdme"][[mem.get(t, False) for t in g.index]].astype(float)
        s = s[s.groupby(sec.reindex(s.index)).transform("size") >= 5]
        w = lt.ew_ls_buffer(s, sec, allok, q_keep=None)
        if prev is not None:
            tos.append(float(w.sub(prev, fill_value=0).abs().sum()))
        prev = w
    return float(np.mean(tos))


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    rd = rd_table()
    res = {}
    for name, lo, hi in (("前 500 名", 1, 500), ("第 501–1000 名", 501, 1000)):
        S = ce.Sample(client, lo, hi, mkt, tx)
        form = formations(S.days)
        sig = signals(S, rd, form)
        P = panel(S, sig, form, equity_daily(S, client))
        print(name, len(P), P["d"].nunique(), flush=True)
        res[name] = (S, form, sig, P)
    S1, form1, sig1, P1 = res["前 500 名"]
    P2 = res["第 501–1000 名"][3]
    h1, h2 = segs(fm(P1)), segs(fm(P2))
    k1 = h1["全期"][1] >= 2.58
    k2 = h1[SEG[0]][0] > 0 and h1[SEG[1]][0] > 0 and h1[SEG[1]][1] >= 1.5
    k3 = h2["全期"][0] > 0 and h2["全期"][1] >= 2.0
    ok = k1 and k2 and k3
    # 只報告
    extra = {"前 500 名 原始產業內 IC（不控制）": segs(fm(P1, controls=False)),
             "前 500 名 研發／營收": segs(fm(P1, "rds")),
             "第 501–1000 名 研發／營收": segs(fm(P2, "rds")),
             "前 500 名 電子業": segs(fm(P1[P1["sector"].isin(ELEC)])),
             "前 500 名 非電子業": segs(fm(P1[~P1["sector"].isin(ELEC)]))}
    rc = {c: float(P1.groupby("d").apply(lambda g: g.groupby("sector")["rdme"].rank(pct=True).corr(g.groupby("sector")[c].rank(pct=True))).mean())
          for c in ("sue", "bm", "lm")}
    car = events_car(S1, sig1, form1, client)
    to = ls_turnover(S1, sig1, form1)
    nsec = P1.groupby("d")["sector"].nunique().median()
    nfirm = P1.groupby("d").size().median()
    L = ["# I081 研發密度（研發費用 ÷ 市值）年度訊號（自動產生）", "",
         "由 [analysis/rd_intensity.py](../analysis/rd_intensity.py) 產生；設計見程式開頭（看結果前固定）。研發費用來自公開資訊觀測站綜合損益表"
         "（[analysis/fetch_rd.py](../analysis/fetch_rd.py)）。係數為每月 Fama-MacBeth（被解釋變數為之後 20 個交易日產業調整報酬的產業內百分位 − 0.5，"
         "控制 log 市值、淨值市價比、12-1 動能、SUE，皆為產業內百分位 − 0.5），括號為（Newey-West t，月數）；正值 = 研發密度高的股票之後表現較好。研究結果，非投資建議。", "",
         f"前 500 名每月樣本中位數 {nfirm:.0f} 檔、{nsec:.0f} 個產業（研發公司 ≥ 5 家的產業）；觀測 {len(P1):,}；第 501–1000 名觀測 {len(P2):,}。", "",
         "| 樣本 | " + " | ".join(SEG) + " | 全期 |", "|---|---|---|---|",
         "| **前 500 名 RDME 係數** | " + " | ".join(fmt(v) for v in h1.values()) + " |",
         "| **確認：第 501–1000 名** | " + " | ".join(fmt(v) for v in h2.values()) + " |"]
    L += [f"| 只報告：{k} | " + " | ".join(fmt(v) for v in x.values()) + " |" for k, x in extra.items()]
    L += ["", f"只報告：RDME 與 SUE 的產業內每月等級相關平均 {rc['sue']:+.2f}、與淨值市價比 {rc['bm']:+.2f}、與 log 市值 {rc['lm']:+.2f}。",
          f"只報告：研發大幅增加事件（年增 ≥ 5% 且研發／總資產 ≥ 5%）之後 250 個交易日相對同產業非事件研發公司 {car[0]:+.2%}"
          f"（依形成年 t {car[1]:.2f}，{car[2]} 件、{car[3]} 年）。",
          f"只報告：產業內前／後 1/3 等權多空每年 4 月換倉，每次換倉的換手（Σ|Δw|，多空合計最大 4）平均 {to:.2f}。", "",
          "## 判定（H1）", "",
          f"- 全期 t ≥ 2.58（{h1['全期'][1]:.2f}）→ {'✓' if k1 else '✗'}",
          f"- 兩段皆 > 0 且第二段 t ≥ 1.5（{h1[SEG[0]][0]:+.4f} / {h1[SEG[1]][0]:+.4f}，t {h1[SEG[1]][1]:.2f}）→ {'✓' if k2 else '✗'}",
          f"- 第 501–1000 名 > 0 且 t ≥ 2.0（{h2['全期'][0]:+.4f}，t {h2['全期'][1]:.2f}）→ {'✓' if k3 else '✗'}", "",
          f"**結論：{'H1 通過（接著做 H2 獨立低換手多空）' if ok else '未通過（H1 不成立，不做 H2）'}**"]
    (ROOT / "docs" / "rd_intensity.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
