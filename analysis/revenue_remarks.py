"""I025 月營收變動原因（備註）與營收驚奇漂移（點子卡 research/ideas/I025-revenue-remark-transitory-sue.md，檢定計畫看結果前固定）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/revenue_remarks.py fetch     # 公開資訊觀測站營收彙總表 t21sc03（上市／上櫃 × 本國／外國公司 × 每月，約 350 次）
    .venv/Scripts/python analysis/revenue_remarks.py sample    # 隨機抽 200 則非空白備註，輸出分類品質檢查表（看報酬前）
    .venv/Scripts/python analysis/revenue_remarks.py           # 檢定，輸出 docs/revenue_remarks.md
原始頁快取在 data_cache/events/corp_raw/t21/。

分類規則（點子卡事前固定，依序判定，先命中者優先；T1、T2 經分類品質檢查後依點子卡修改一次，之後凍結，見下）：
- T1 併購（修改後）：併入|納入合併|收購|購併|併購|新增.{0,4}子公司|合併.{0,6}(子公司|集團)|因合併|停業單位|停業部門|喪失控制|
  取得.{0,8}(子公司|股權)|起.{0,2}合併|未合併|不再.{0,6}合併|處[分份].{0,4}子公司
  （原規則的「合併.{0,6}營收」會誤中「合併營收淨額」而刪除）
- T2 一次性（修改後）：交屋|交房|成屋|餘屋|建案|個案|樓盤|房地|售地|過戶|營建|土地|處分|處份|出售|一次性|權利金|授權金|簽約金|驗收|工程進度|進度認列|完工|補助款
- C 日曆／基期：春節|農曆|工作天|工作日|連假|基期
- O 營運：需求|訂單|拉貨|出貨|新產品|新客戶|市占|景氣|旺季|淡季|價格|運價|報價|售價|產能|稼動
- 其餘非空白為「其他」，空白或「-」為「無備註」。T = T1 或 T2。
分類品質檢查（看報酬前，人工判讀）：200 則隨機樣本，原規則 T 類精確率 92.7%、召回率 66.7%（未達 80%）；修改一次後同一樣本 96.4% / 93.0%；
另抽 100 則新樣本為 90.9% / 66.7%（召回率仍不足，修改有過度配合樣本的成分）。依點子卡凍結修改後規則繼續檢定；召回不足使部分真正的 T 類落入其他類，效果偏向低估。
研究結果，非投資建議。
"""
import html
import math
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import fetch_corp_events as fc  # noqa: E402

RAW = fc.RAW / "t21"
OUT = ROOT / "data_cache" / "events" / "revenue_remarks.csv"
RULES = [("T1", r"併入|納入合併|收購|購併|併購|新增.{0,4}子公司|合併.{0,6}(子公司|集團)|因合併|停業單位|停業部門|喪失控制|取得.{0,8}(子公司|股權)|起.{0,2}合併|未合併|不再.{0,6}合併|處[分份].{0,4}子公司"),
         ("T2", r"交屋|交房|成屋|餘屋|建案|個案|樓盤|房地|售地|過戶|營建|土地|處分|處份|出售|一次性|權利金|授權金|簽約金|驗收|工程進度|進度認列|完工|補助款"),
         ("C", r"春節|農曆|工作天|工作日|連假|基期"),
         ("O", r"需求|訂單|拉貨|出貨|新產品|新客戶|市占|景氣|旺季|淡季|價格|運價|報價|售價|產能|稼動")]


def months():
    return pd.period_range("2018-12", "2026-03", freq="M")


def fetch_page(mkt: str, p: pd.Period, kind: int) -> str | None:
    path = RAW / f"{mkt}_{p.year - 1911}_{p.month}_{kind}.html"
    if path.exists():
        t = path.read_text(encoding="utf-8")
        return t or None
    url = f"https://mopsov.twse.com.tw/nas/t21/{mkt}/t21sc03_{p.year - 1911}_{p.month}_{kind}.html"
    for k in range(4):
        try:
            r = requests.get(url, headers={"User-Agent": fc.UA}, timeout=60)
            time.sleep(3)
            if r.status_code == 404:
                path.write_text("", encoding="utf-8")
                return None
            if r.status_code == 200:
                t = r.content.decode("big5", errors="replace")
                path.write_text(t, encoding="utf-8")
                return t
        except requests.RequestException as e:
            print(f"  {type(e).__name__}，重試", flush=True)
        time.sleep(15 * (k + 1))
    raise RuntimeError(f"多次失敗：{url}")


def classify(s: str) -> str:
    s = (s or "").strip()
    if s in ("", "-", "－"):
        return "無備註"
    for lab, pat in RULES:
        if re.search(pat, s):
            return lab
    return "其他"


def parse(t: str, p: pd.Period) -> list[dict]:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S | re.I):
        c = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S | re.I)]
        if len(c) >= 10 and re.fullmatch(r"\d{4}", c[0]):
            rows.append({"stock_id": c[0], "name": c[1], "rev_month": str(p), "revenue": c[2], "remark": c[-1] if len(c) >= 11 else ""})
    return rows


def cmd_fetch():
    RAW.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in months():
        for mkt in ("sii", "otc"):
            for kind in (0, 1):
                t = fetch_page(mkt, p, kind)
                if t:
                    rows += parse(t, p)
        print(f"{p}：累計 {len(rows):,} 列", flush=True)
    df = pd.DataFrame(rows).drop_duplicates(["stock_id", "rev_month"])
    df["cls"] = df["remark"].map(classify)
    df.to_csv(OUT, index=False)
    print(df["cls"].value_counts().to_string())
    print("DONE", flush=True)


def cmd_sample():
    df = pd.read_csv(OUT, dtype={"stock_id": str}).fillna({"remark": ""})
    nz = df[df["cls"] != "無備註"].sample(200, random_state=20261018)
    path = ROOT / "data_cache" / "events" / "revenue_remarks_sample.csv"
    nz[["stock_id", "name", "rev_month", "remark", "cls"]].to_csv(path, index=False)
    print(path)


# ---------------------------------------------------------------------------
# 檢定（設計見點子卡；補：SUE、log 市值用當月橫斷面百分位 − 0.5；非金融股 = 產業不是「金融保險」「金融業」）
# ---------------------------------------------------------------------------

FIN = ("金融保險", "金融業")


def load_cls() -> dict:
    df = pd.read_csv(OUT, dtype={"stock_id": str}).fillna({"remark": ""})
    avail = pd.PeriodIndex(df["rev_month"], freq="M").to_timestamp() + pd.offsets.MonthBegin(1)
    return {(a, s + ".TW"): c for a, s, c in zip(avail, df["stock_id"], df["cls"])}


def panel(adj, member, sector, sue, sched, limit, cls, logcap):
    rows = []
    for d in sched:
        k = int(adj.index.searchsorted(d))
        mo = d.to_period("M").to_timestamp()
        if k + 20 >= limit or mo not in sue.index:
            continue
        mem = member.loc[d].to_numpy(bool)
        s = sue.loc[mo].reindex(adj.columns)[mem].dropna()
        s = s[~sector.reindex(s.index).isin(FIN).to_numpy()]
        if len(s) < 50:
            continue
        f60 = (adj.iloc[k + 60] / adj.iloc[k] - 1).reindex(s.index) if k + 60 < limit else pd.Series(np.nan, index=s.index)
        rows.append(pd.DataFrame({"sue": s, "rank": s.groupby(sector.reindex(s.index)).rank(pct=True),
                                  "cls": [cls.get((mo, t), "無備註") for t in s.index],
                                  "f20": (adj.iloc[k + 20] / adj.iloc[k] - 1).reindex(s.index), "f60": f60,
                                  "sec": sector.reindex(s.index), "lm": logcap.loc[d].reindex(s.index), "d": d}))
    return pd.concat(rows)


def group_diff(P, h, tset=("T1", "T2")):
    out = {}
    for d, g in P.groupby("d"):
        isT = g["cls"].isin(tset)
        res = []
        for m in (g["rank"] > 0.7, g["rank"] <= 0.3):
            a, b = g.loc[m & isT, h].dropna(), g.loc[m & (g["cls"] == "O"), h].dropna()
            res.append(a.mean() - b.mean() if len(a) and len(b) else np.nan)
        out[d] = res
    X = pd.DataFrame(out, index=["top", "bot"]).T
    X["signed"] = X["top"] - X["bot"]
    return X


def fm(P, exclude_build=False):
    out = {}
    for d, g in P.groupby("d"):
        if exclude_build:
            g = g[g["sec"] != "建材營造"]
        g = g.dropna(subset=["f20", "sue", "lm"])
        if len(g) < 50:
            continue
        rs = g["sue"].rank(pct=True) - 0.5
        iT, iC = g["cls"].isin(["T1", "T2"]).astype(float), (g["cls"] == "C").astype(float)
        X = np.column_stack([np.ones(len(g)), rs, rs * iT, rs * iC, iT, g["lm"].rank(pct=True) - 0.5,
                             pd.get_dummies(g["sec"], drop_first=True, dtype=float).to_numpy()])
        beta, *_ = np.linalg.lstsq(X, g["f20"].to_numpy(float), rcond=None)
        out[d] = beta[1:5]
    return pd.DataFrame(out, index=["b1", "b2", "b3", "b4"]).T


def tstat(x):
    x = pd.Series(x, dtype=float).dropna()
    return (float(x.mean()), float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan"), len(x))


def segs(x):
    cut = pd.Timestamp("2023-01-01")
    return {"2019–2022": tstat(x[x.index < cut]), "2023–2026/04": tstat(x[x.index >= cut]), "全期": tstat(x)}


def fmt(x):
    m, t, n = x
    return "—" if m != m else f"{m:+.2%}（{t:.1f}，{n}）"


def main():
    import borrow_capacity as bc
    import corp_event_study as ce
    import dotenv
    import hedge_construction as hc
    import leg_probe as lp
    import ls_turnover as lt
    import sue_streak as ss

    cls = load_cls()
    c = lp.prepare(500)
    limit = int(c.adj.index.searchsorted(lp.HOLDOUT))
    P = panel(c.adj, c.member, c.sector, c.sue, c.schedule, limit, cls, c.logcap)
    ds = P["d"].unique()
    nT_top = P[(P["rank"] > 0.7) & P["cls"].isin(["T1", "T2"])].groupby("d").size().reindex(ds, fill_value=0).mean()
    nT_bot = P[(P["rank"] <= 0.3) & P["cls"].isin(["T1", "T2"])].groupby("d").size().reindex(ds, fill_value=0).mean()
    share = P["cls"].value_counts(normalize=True)
    G20, G60 = group_diff(P, "f20"), group_diff(P, "f60")
    G1, G2 = group_diff(P, "f20", ("T1",)), group_diff(P, "f20", ("T2",))
    F, Fx = fm(P), fm(P, exclude_build=True)
    dotenv.load_dotenv(ROOT / ".env")
    V = ce.Sample(c.client, 501, 1000, lp.market_tri(c.client), lp.tx_continuous(c.client))
    vsec = pd.Series({t: V.sector.get(t.split(".")[0], "NA") for t in V.tickers})
    VP = panel(V.adj, V.member, vsec, ss.sue_monthly(c.client, V.tickers), [d for d in c.schedule if d in V.days], V.limit, cls, V.lmcap)
    VF = fm(VP)

    s_sig, s_b2, v_b2 = segs(G20["signed"]), segs(F["b2"]), segs(VF["b2"])
    insufficient = nT_top < 5 or nT_bot < 5
    c1 = s_sig["2019–2022"][0] < 0 and s_sig["2023–2026/04"][0] < 0 and s_sig["全期"][1] < -2
    c2 = s_b2["2019–2022"][0] < 0 and s_b2["2023–2026/04"][0] < 0 and s_b2["全期"][1] < -2
    c3 = v_b2["全期"][0] < 0
    port = None
    if c1 and c2 and not insufficient:
        fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
        quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
        close = bc.raw_close(c)
        sue = lp.leg_scores(c, "sue")

        def shortable_at(d):
            n_short = max(1, int(c.member.loc[d].sum() / 3))
            need = lt.K_CAPITAL / n_short / close.loc[d]
            return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

        def drop_t(d):
            mo = d.to_period("M").to_timestamp()
            s = sue[d]
            return s[[cls.get((mo, t), "") not in ("T1", "T2") for t in s.index]]

        def book(fn):
            parts = []
            for off in range(3):
                w = {d: lt.ew_ls_buffer(fn(d), c.sector, shortable_at(d), q_keep=None) for d in c.schedule[off::3]}
                parts.append(hc.simulate_weights(w, c.rets, c.betas, c.tx, list(w), fee=fee)["ret"])
            x = pd.concat(parts, axis=1).mean(axis=1)
            x = x[x.index > c.schedule[2]]
            return hc.stats(x) | {"full": lp.sharpe(x.dropna())}
        port = {"fv5 原版": book(lambda d: sue[d]), "排除 T 類（多空兩邊）": book(drop_t)}
    c4 = port is not None and port["排除 T 類（多空兩邊）"]["sh_oos"] >= port["fv5 原版"]["sh_oos"] \
        and port["排除 T 類（多空兩邊）"]["sh_is"] >= port["fv5 原版"]["sh_is"]

    L = ["# I025 月營收變動原因與營收驚奇漂移（自動產生）", "",
         "由 [analysis/revenue_remarks.py](../analysis/revenue_remarks.py) 產生；設計見點子卡與程式開頭（看結果前固定）。"
         "差額為同一 SUE 組（產業內前或後 30%）中 T 類（併購或一次性）減 O 類（營運因素）的等權平均報酬；帶符號 = 前 30% 組差額 − 後 30% 組差額（預期 < 0）；"
         "括號為（t 值，月份數，依月份群集）；Fama-MacBeth 係數為 SUE 百分位差 1 對應的 20 日報酬變化。非金融股。研究結果，非投資建議。", "",
         f"主樣本非金融股公司月 {len(P):,} 筆；備註分類占比：" + "、".join(f"{k} {v:.1%}" for k, v in share.items()) + "。"
         f"每月 T 類在 SUE 前 30% 組平均 {nT_top:.1f} 檔、後 30% 組 {nT_bot:.1f} 檔（門檻 5）。", "",
         "| 統計量 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         "| (1) 帶符號 (T − O)，20 日 | " + " | ".join(fmt(s_sig[k]) for k in s_sig) + " |",
         "| 前 30% 組 T − O，20 日 | " + " | ".join(fmt(v) for v in segs(G20["top"]).values()) + " |",
         "| 後 30% 組 T − O，20 日 | " + " | ".join(fmt(v) for v in segs(G20["bot"]).values()) + " |",
         "| 只報告：帶符號 (T − O)，60 日 | " + " | ".join(fmt(v) for v in segs(G60["signed"]).values()) + " |",
         "| 只報告：帶符號，只看 T1 併購 | " + " | ".join(fmt(v) for v in segs(G1["signed"]).values()) + " |",
         "| 只報告：帶符號，只看 T2 一次性 | " + " | ".join(fmt(v) for v in segs(G2["signed"]).values()) + " |",
         "| (2) Fama-MacBeth b2：SUE × I(T) | " + " | ".join(fmt(s_b2[k]) for k in s_b2) + " |",
         "| Fama-MacBeth b1：SUE | " + " | ".join(fmt(v) for v in segs(F["b1"]).values()) + " |",
         "| 只報告：b3 SUE × I(日曆／基期) | " + " | ".join(fmt(v) for v in segs(F["b3"]).values()) + " |",
         "| 只報告：b2，排除建材營造 | " + " | ".join(fmt(v) for v in segs(Fx["b2"]).values()) + " |",
         "| (3) 驗證樣本 b2 | " + " | ".join(fmt(v_b2[k]) for k in v_b2) + " |", ""]
    if port:
        L += ["| 建構（fv5） | Sharpe | 全期 | 年化報酬 |", "|---|---|---|---|"]
        for k, s in port.items():
            L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} |")
        L.append("")
    L += ["## 判定", "",
          f"0. 樣本量：T 類每月在前／後 30% 組平均 {nT_top:.1f} / {nT_bot:.1f} 檔 → {'不足（只報告、不下結論）' if insufficient else '足夠'}",
          f"1. 帶符號差兩段 < 0、全期 t < −2：{fmt(s_sig['全期'])} → {'✓' if c1 else '✗'}",
          f"2. b2 兩段 < 0、全期 t < −2：{fmt(s_b2['全期'])} → {'✓' if c2 else '✗'}",
          f"3. 驗證樣本 b2 同號（< 0）：{fmt(v_b2['全期'])} → {'✓' if c3 else '✗'}",
          f"4. 濾網版兩段 Sharpe 不低於 fv5：{'未執行' if port is None else ('✓' if c4 else '✗')}", "",
          f"**結論：{'樣本不足，不下結論' if insufficient else ('通過' if c1 and c2 and c3 and c4 else '未通過')}**"]
    (ROOT / "docs" / "revenue_remarks.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "fetch":
        cmd_fetch()
    elif len(sys.argv) > 1 and sys.argv[1] == "sample":
        cmd_sample()
    else:
        main()
