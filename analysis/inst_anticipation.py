"""I036 法人公告前交易是否預告營收驚奇（點子卡 research/ideas/I036-institutional-anticipation-sue.md，檢定計畫看結果前固定）。

用法（於專案根目錄；前 500 名資料已快取；第二步成立才抓驗證樣本約 582 次 FinMind）：
    .venv/Scripts/python analysis/inst_anticipation.py
輸出 docs/inst_anticipation.md。

設計（依點子卡；補充以「補」標示）：
- 樣本：前 500 名非金融股（產業不是「金融保險」「金融業」），換倉日 = 營收公告期限次一交易日（leg_probe schedule），2019-01 ~ 2026-04。
- PreFlow = 窗口內外資（Foreign_Investor + Foreign_Dealer_Self）＋投信淨買股數合計 ÷ 窗口結束日已發行股數；
  主窗口：上月 21 日 ~ 本月 5 日；次要：上月 21 日 ~ 本月 10 日（只報告）。外資、投信分開只報告。
- 第一步：每月 Fama-MacBeth，本月 SUE（原始）= a + b·PreFlow + 上月 SUE + 窗口前 20 日報酬 + 窗口內報酬 + log 市值
  （除 SUE 外皆為橫斷面百分位 − 0.5，補）；b 兩段 > 0、全期 t > 2 才進第二步。
- 第二步：+0 = 換倉日，第 +1 日收盤進場，報酬至第 +21 日收盤。SUE 產業內前 30% 組：PreFlow 後三分之一 − 前三分之一（預期 > 0）；
  後 30% 組：PreFlow 前三分之一 − 後三分之一（預期 < 0）；帶符號差 = 前者 − 後者（預期 > 0），依月份群集 t。
  Fama-MacBeth 交互項 SUE × PreFlow（預期 < 0）。驗證樣本同樣計算。
- 可交易（第二步成立才做）：fv5 做多名單排除 PreFlow 前三分之一、放空名單排除 PreFlow 後三分之一並遞補。
- 通過：第一步如上；第二步帶符號差兩段同號、全期 t > 2，驗證同號；可交易兩段不低於 fv5 且全期 ≥ 1.70。方向相反也判為未通過。
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
import leg_probe as lp  # noqa: E402
import lending_legs as ll  # noqa: E402

FIN = ("金融保險", "金融業")


def flows(client, tickers, index):
    fo, tr = {}, {}
    for t in tickers:
        d = client.get("TaiwanStockInstitutionalInvestorsBuySell", t.split(".")[0], lp.EV_START, lp.EV_END)
        if d.empty:
            continue
        d = d.assign(date=pd.to_datetime(d["date"]), net=d["buy"].astype(float) - d["sell"].astype(float))
        fo[t] = d[d["name"].isin(["Foreign_Investor", "Foreign_Dealer_Self"])].groupby("date")["net"].sum()
        tr[t] = d[d["name"] == "Investment_Trust"].groupby("date")["net"].sum()
    f = lambda m: pd.DataFrame(m).reindex(index=index, columns=tickers).fillna(0.0)  # noqa: E731
    return f(fo), f(tr)


def panel(c, fo, tr, shares, limit, endday):
    days = c.adj.index
    rows = []
    cs_f, cs_t = fo.cumsum(), tr.cumsum()
    for d in c.schedule:
        k = int(days.searchsorted(d))
        mo = d.to_period("M").to_timestamp()
        prev = mo - pd.offsets.MonthBegin(1)
        if k + 21 >= limit or mo not in c.sue.index or prev not in c.sue.index:
            continue
        ka = int(days.searchsorted(prev + pd.Timedelta(days=20)))           # 上月 21 日當天或之後
        kb = int(days.searchsorted(mo + pd.Timedelta(days=endday), side="right")) - 1   # 本月 endday 日當天或之前
        if not (20 <= ka <= kb < k):
            continue
        mem = c.member.loc[d]
        tk = [t for t in c.tickers if bool(mem[t]) and c.sector.get(t) not in FIN]
        sh = shares.iloc[kb].reindex(tk)
        pf = (cs_f.iloc[kb] - cs_f.iloc[ka - 1]).reindex(tk) / sh
        pt = (cs_t.iloc[kb] - cs_t.iloc[ka - 1]).reindex(tk) / sh
        adj = c.adj
        rows.append(pd.DataFrame({"d": d, "sue": c.sue.loc[mo].reindex(tk), "sue_lag": c.sue.loc[prev].reindex(tk),
                                  "pre": pf + pt, "pre_f": pf, "pre_t": pt,
                                  "r_pre20": (adj.iloc[ka - 1] / adj.iloc[ka - 21] - 1).reindex(tk),
                                  "r_win": (adj.iloc[kb] / adj.iloc[ka - 1] - 1).reindex(tk),
                                  "lm": c.logcap.iloc[k].reindex(tk), "sec": c.sector.reindex(tk),
                                  "f": (adj.iloc[k + 21] / adj.iloc[k + 1] - 1).reindex(tk)}, index=tk))
    P = pd.concat(rows)
    P["r_prepct"] = P.groupby(["d", "sec"])["pre"].rank(pct=True)
    return P


def fm_step1(P, col="pre"):
    out = {}
    R = lambda x: x.rank(pct=True) - 0.5  # noqa: E731
    for d, g in P.groupby("d"):
        g = g.dropna(subset=["sue", "sue_lag", col, "r_pre20", "r_win", "lm"])
        if len(g) < 50:
            continue
        X = np.column_stack([np.ones(len(g)), R(g[col]), g["sue_lag"], R(g["r_pre20"]), R(g["r_win"]), R(g["lm"])])
        beta, *_ = np.linalg.lstsq(X, g["sue"].to_numpy(float), rcond=None)
        out[d] = beta[1]
    return pd.Series(out)


def step2(P):
    out = {}
    for d, g in P.groupby("d"):
        g = g.dropna(subset=["sue", "pre", "f"])
        sr = g.groupby("sec")["sue"].rank(pct=True)
        res = []
        for m, sign in ((sr > 0.7, 1), (sr <= 0.3, -1)):
            h = g[m]
            if len(h) < 9:
                res.append(np.nan)
                continue
            r = h["pre"].rank(pct=True)
            lo, hi = h.loc[r <= 1 / 3, "f"].mean(), h.loc[r > 2 / 3, "f"].mean()
            res.append((lo - hi) if sign > 0 else (hi - lo))
        out[d] = res
    X = pd.DataFrame(out, index=["top", "bot"]).T
    X["signed"] = X["top"] - X["bot"]
    return X


def tstat(x):
    x = pd.Series(x, dtype=float).dropna()
    return (float(x.mean()), float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan"), len(x))


def segs(x):
    return {"2019–2022": tstat(x[x.index < lp.SPLIT]), "2023–2026/04": tstat(x[x.index >= lp.SPLIT]), "全期": tstat(x)}


def main():
    c = lp.prepare(500)
    limit = int(c.adj.index.searchsorted(lp.HOLDOUT))
    fo, tr = flows(c.client, c.tickers, c.adj.index)
    shares = ll.load_shares(c.client, c.tickers, c.adj.index)
    P = panel(c, fo, tr, shares, limit, 5)
    P10 = panel(c, fo, tr, shares, limit, 10)
    s1 = segs(fm_step1(P))
    s1_10 = segs(fm_step1(P10))
    s1_f, s1_t = segs(fm_step1(P, "pre_f")), segs(fm_step1(P, "pre_t"))
    ok1 = s1["2019–2022"][0] > 0 and s1["2023–2026/04"][0] > 0 and s1["全期"][1] > 2
    fmt = lambda x, p=False: "—" if x[0] != x[0] else (f"{x[0]:+.2%}" if p else f"{x[0]:+.3f}") + f"（{x[1]:.1f}，{x[2]}）"  # noqa: E731
    L = ["# I036 法人公告前交易與營收驚奇（自動產生）", "",
         "由 [analysis/inst_anticipation.py](../analysis/inst_anticipation.py) 產生；設計見程式開頭（看結果前固定）。"
         "第一步係數為 PreFlow 百分位差 1 對應的 SUE 變化（SUE 為標準化驚奇，單位為標準差）；第二步為同一 SUE 組內依 PreFlow 分組的 20 日報酬差；"
         "括號為（t 值，月份數）。非金融股。研究結果，非投資建議。", "",
         f"主樣本公司月 {len(P):,} 筆。", "",
         "| 第一步：本月 SUE 對 PreFlow（控制上月 SUE、窗口前與窗口內報酬、市值） | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         "| 主窗口（上月 21 日 ~ 本月 5 日），外資＋投信 | " + " | ".join(fmt(s1[k]) for k in s1) + " |",
         "| 只報告：次要窗口（至本月 10 日） | " + " | ".join(fmt(s1_10[k]) for k in s1_10) + " |",
         "| 只報告：只看外資 | " + " | ".join(fmt(s1_f[k]) for k in s1_f) + " |",
         "| 只報告：只看投信 | " + " | ".join(fmt(s1_t[k]) for k in s1_t) + " |", ""]
    if not ok1:
        L += ["## 判定", "", f"1. 第一步 PreFlow 係數兩段 > 0、全期 t > 2：{fmt(s1['全期'])} → ✗", "",
              "**結論：未通過（第一步不成立，依點子卡停止；未看報酬、未抓驗證樣本）**"]
    else:
        X = step2(P)
        s2 = segs(X["signed"])
        L += ["| 第二步：20 日報酬差 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
              "| 帶符號差（預期 > 0） | " + " | ".join(fmt(s2[k], True) for k in s2) + " |",
              "| SUE 前 30%：未預先買 − 已預先買 | " + " | ".join(fmt(v, True) for v in segs(X["top"]).values()) + " |",
              "| SUE 後 30%：未預先賣 − 已預先賣 | " + " | ".join(fmt(v, True) for v in segs(X["bot"]).values()) + " |", ""]
        ok2 = s2["2019–2022"][0] > 0 and s2["2023–2026/04"][0] > 0 and s2["全期"][1] > 2
        L += ["## 判定", "", f"1. 第一步：{fmt(s1['全期'])} → ✓", f"2. 第二步帶符號差兩段 > 0、全期 t > 2：{fmt(s2['全期'], True)} → {'✓' if ok2 else '✗'}", "",
              f"**結論：{'第二步成立，需再做驗證樣本與可交易版本' if ok2 else '未通過（第二步不成立）'}**"]
    (ROOT / "docs" / "inst_anticipation.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
