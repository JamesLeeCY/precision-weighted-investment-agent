"""I014 台指選擇權 Put/Call 比逆向擇時（點子卡 research/ideas/I014-txo-put-call-ratio-timing.md 的檢定計畫，看結果前固定）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/pcr_timing.py
輸出 docs/pcr_timing.md 與 reports/legs/pcr_timing.csv。

- 資料：快取的 TaiwanOptionDaily TXO（2007 起），只用一般交易時段（2008 年的資料沒有時段欄位，全部視為一般時段）。
- 核對：先比對 2026-09-01 ~ 2026-10-14 自算的「週＋月契約合併」未平倉 Put/Call 比與期交所官方值（pcRatio），
  平均絕對差需 < 2 個百分點才進行回測（期交所 2 次請求）。第一次核對 3.4 個百分點，差異都在週選擇權到期日；
  查證後官方未平倉排除當日到期契約，依同一定義計算後完全相同（只改資料定義，未看任何回測結果）。
- 訊號：P = 月契約賣權未平倉 ÷ 買權未平倉，5 日平均，再換成過去 250 日的百分位（含當日）。副訊號：成交量版本。
- 規則：逆向 e = 100%（百分位 ≥ 80%）、60%（≤ 20%）、其餘 80%；順向把 100% 與 60% 對調。第 t 日收盤後計算，第 t+1 日起生效
  （以收盤到收盤報酬近似開盤調整）。
- 執行：持有 0050，以放空台指期調整淨曝險（timing_futures.futures_overlay；期貨變動 × 0.005%、每月轉倉）；
  對照為同平均曝險的固定比例（同樣以期貨執行）。
- 期間：樣本內 2008–2015、樣本外 2016 ~ 2026/04；滾動前進 2012 起：8 種候選（未平倉／成交量 × 逆向／順向 × 5／20 日平均），
  每年 1 月用之前資料選 Sharpe 最高者持有一年。
- 預測迴歸：加權指數含息報酬（未來 5、20 日，從 t+1 起）對 P 百分位迴歸，控制自算台指 VIX 與過去 20 日報酬，Newey-West（落後 20）。
- 通過（全部成立）：(1) 主規則（未平倉、逆向、5 日）樣本外相對固定比例年化差 > 0 且 t > 2；(2) 樣本內也 > 0；
  (3) 滾動前進樣本外 > 固定比例；(4) 預測迴歸控制 VIX 後 P 係數兩段同號、全期 t > 2。
研究結果，非投資建議。
"""
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import timing_futures as tf  # noqa: E402
from data.fetch_financials import FinMindClient, get_total_return_prices  # noqa: E402
from sue_attention import nw_t  # noqa: E402

START, END, SPLIT = "2008-01-01", "2026-04-30", pd.Timestamp("2016-01-01")
CHECK_START, CHECK_END = "2026-09-01", "2026-10-14"


def load_pc(client, start="2007-01-01", end=CHECK_END) -> pd.DataFrame:
    """每日 [月契約 P_oi, P_vol, 全部契約 P_oi_all, P_vol_all]。
    未平倉排除當日到期的契約（與期交所官方定義一致：核對時排除後 28／28 日完全相同）；成交量包含到期契約。
    到期日為事先公布的契約規格，沒有前視。"""
    parts = []
    for m in pd.period_range(start, end, freq="M"):
        s, e = max(pd.Timestamp(start), m.start_time).strftime("%Y-%m-%d"), min(pd.Timestamp(end), m.end_time).strftime("%Y-%m-%d")
        d = client.get("TaiwanOptionDaily", "TXO", s, e)
        if d.empty:
            continue
        if "trading_session" in d.columns:
            d = d[d["trading_session"] == "position"]
        parts.append(pd.DataFrame({"date": pd.to_datetime(d["date"]), "contract": d["contract_date"].astype(str), "cp": d["call_put"],
                                   "oi": d["open_interest"].astype(float), "vol": d["volume"].astype(float)}))
    d = pd.concat(parts, ignore_index=True)
    last = d.groupby("contract")["date"].max()
    d["expiring"] = d["contract"].map(last) == d["date"]
    d["monthly"] = d["contract"].str.fullmatch(r"\d{6}")
    out = {}
    for scope, g in (("m", d[d["monthly"]]), ("all", d)):
        oi = g[~g["expiring"]].groupby(["date", "cp"])["oi"].sum().unstack("cp")
        vol = g.groupby(["date", "cp"])["vol"].sum().unstack("cp")
        out[f"p_oi_{scope}"] = oi["put"] / oi["call"]
        out[f"p_vol_{scope}"] = vol["put"] / vol["call"]
    return pd.DataFrame(out).sort_index()


def official_pc() -> pd.DataFrame:
    """期交所 pcRatio（週＋月合併）；CSV 下載端點一次最多約一個月，分月查（2 次請求）。"""
    import time
    rows = []
    for s, e in (("2026/09/01", "2026/09/30"), ("2026/10/01", "2026/10/14")):
        r = requests.post("https://www.taifex.com.tw/cht/3/pcRatioDown", data={"queryStartDate": s, "queryEndDate": e, "down_type": ""},
                          headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        for line in r.content.decode("big5", errors="replace").splitlines()[1:]:
            c = line.split(",")
            if len(c) >= 7 and re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", c[0]):
                rows.append({"date": pd.Timestamp(c[0].replace("/", "-")), "off_vol": float(c[3]) / 100, "off_oi": float(c[6]) / 100})
        time.sleep(3)
    return pd.DataFrame(rows).set_index("date").sort_index()


def pct_rank(x: pd.Series, n: int = 250) -> pd.Series:
    return x.rolling(n, min_periods=n // 2).apply(lambda w: (w <= w[-1]).mean(), raw=True)


def exposure(pct: pd.Series, contrarian: bool) -> pd.Series:
    hi, lo = (1.0, 0.6) if contrarian else (0.6, 1.0)
    e = pd.Series(0.8, index=pct.index)
    e[pct >= 0.8] = hi
    e[pct <= 0.2] = lo
    e[pct.isna()] = np.nan
    return e.shift(1)                                          # 第 t 日收盤計算 → 第 t+1 日生效


def compare(e: pd.Series, r, rtx, mask) -> dict:
    e = e.reindex(r.index).ffill().fillna(0.8)
    fut = tf.futures_overlay(e, r, rtx)
    fixed = tf.futures_overlay(pd.Series(float(e[mask].mean()), index=r.index), r, rtx)
    d = (fut - fixed)[mask].dropna()
    return {"avg": float(e[mask].mean()), "diff": float(d.mean() * 252), "t": nw_t(d, 20),
            "sh": tf.summary(fut[mask])["sharpe"], "sh_fixed": tf.summary(fixed[mask])["sharpe"], "mdd": tf.summary(fut[mask])["mdd"],
            "turn": float((1 - e[mask]).diff().abs().sum() / (mask.sum() / 252))}


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    pc = load_pc(client)
    off = official_pc()
    chk = pc.join(off, how="inner")
    mad_oi = float((chk["p_oi_all"] - chk["off_oi"]).abs().mean() * 100)
    mad_vol = float((chk["p_vol_all"] - chk["off_vol"]).abs().mean() * 100)
    lines = ["# I014 台指選擇權 Put/Call 比擇時（自動產生）", "",
             "由 [analysis/pcr_timing.py](../analysis/pcr_timing.py) 產生；檢定計畫見點子卡 [I014](../research/ideas/I014-txo-put-call-ratio-timing.md)（看結果前固定）。"
             "差額 = 擇時規則 − 同平均曝險固定比例（皆以台指期執行，扣期貨成本與轉倉）的年化報酬差，括號為 Newey-West t 值；"
             "Sharpe = 年化報酬 ÷ 波動。研究結果，非投資建議。", "",
             "## 0. 自算值與期交所官方值核對（2026-09-01 ~ 2026-10-14，週＋月合併）", "",
             f"共 {len(chk)} 個交易日；未平倉 Put/Call 比平均絕對差 {mad_oi:.2f} 個百分點、成交量版本 {mad_vol:.2f} 個百分點"
             f"（門檻 < 2）→ {'通過，進行回測' if mad_oi < 2 else '未通過，停止'}。", ""]
    if mad_oi >= 2:
        (ROOT / "docs" / "pcr_timing.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("CHECK FAILED", flush=True)
        return

    px = get_total_return_prices(client, "0050.TW", "2003-06-30", "2026-05-31").set_index("date")["adj_close"].astype(float)
    r_all = px.pct_change()
    r = r_all[(r_all.index >= START) & (r_all.index <= END)]
    rtx = tf.tx_returns(client)
    pc = pc[pc.index <= END]
    cands = {}
    for field, lab in (("p_oi_m", "未平倉"), ("p_vol_m", "成交量")):
        for win in (5, 20):
            pct = pct_rank(pc[field].rolling(win, min_periods=win).mean())
            for contra in (True, False):
                cands[f"{lab}・{'逆向' if contra else '順向'}・{win} 日"] = exposure(pct, contra)
    ins, oos = r.index < SPLIT, r.index >= SPLIT
    lines += ["## 1. 規則（台指期執行）相對同平均曝險固定比例", "",
              "| 規則 | 期間 | 平均曝險 | 年化差額（t） | Sharpe：規則 / 固定 | 最大回撤 | 期貨年換手（倍） |", "|---|---|---|---|---|---|---|"]
    main_key = "未平倉・逆向・5 日"
    res = {}
    for k, e in cands.items():
        for lab, m in (("樣本內 2008–2015", ins), ("樣本外 2016 ~ 2026/04", oos)):
            c = compare(e, r, rtx, m)
            res[(k, lab)] = c
            lines.append(f"| {k}{'（主規則）' if k == main_key else ''} | {lab} | {c['avg']:.0%} | {c['diff']:+.2%}（{c['t']:.1f}） | "
                         f"{c['sh']:.2f} / {c['sh_fixed']:.2f} | {c['mdd']:.1%} | {c['turn']:.1f} |")
    # 滾動前進
    wf = pd.Series(np.nan, index=r.index)
    picks = []
    for y in range(2012, 2027):
        hist = (r.index >= START) & (r.index < f"{y}-01-01")
        best = max(cands, key=lambda k: tf.summary(tf.futures_overlay(cands[k].reindex(r.index).ffill().fillna(0.8), r, rtx)[hist])["sharpe"])
        picks.append((y, best))
        yr = (r.index >= f"{y}-01-01") & (r.index < f"{y + 1}-01-01")
        wf[yr] = cands[best].reindex(r.index)[yr]
    wf_mask = (r.index >= SPLIT)
    cw = compare(wf, r, rtx, wf_mask)
    lines += ["", "## 2. 滾動前進（每年 1 月用之前資料選 8 種候選中 Sharpe 最高者）", "",
              f"樣本外 2016 ~ 2026/04：年化差額 {cw['diff']:+.2%}（t {cw['t']:.1f}），Sharpe {cw['sh']:.2f} vs 固定 {cw['sh_fixed']:.2f}。", "",
              "每年選中的規則：" + "、".join(f"{y} {k}" for y, k in picks) + "。", ""]
    # 預測迴歸
    tri = client.get("TaiwanStockTotalReturnIndex", "TAIEX", "2007-01-01", "2026-05-31")
    idx = pd.Series(tri["price"].astype(float).to_numpy(), index=pd.to_datetime(tri["date"])).sort_index()
    vix = pd.read_csv(ROOT / "reports" / "txo_vix.csv", index_col=0, parse_dates=True)["vix"]
    p_main = pct_rank(pc["p_oi_m"].rolling(5, min_periods=5).mean())
    lines += ["## 3. 預測迴歸（加權指數含息未來報酬 ~ P 百分位 + 台指 VIX + 過去 20 日報酬；Newey-West 落後 20）", "",
              "| 未來報酬 | 期間 | P 係數（t） | VIX 係數（t） | 樣本日數 |", "|---|---|---|---|---|"]
    reg = {}
    for h in (5, 20):
        fwd = idx.shift(-h) / idx - 1
        past = idx / idx.shift(20) - 1
        df = pd.DataFrame({"y": fwd, "p": p_main, "vix": vix, "past": past}).dropna()
        df = df[(df.index >= START) & (df.index <= END)]
        for lab, g in (("2008–2015", df[df.index < SPLIT]), ("2016 ~ 2026/04", df[df.index >= SPLIT]), ("全期", df)):
            Z = (g[["p", "vix", "past"]] - g[["p", "vix", "past"]].mean()) / g[["p", "vix", "past"]].std()
            X = np.column_stack([np.ones(len(g)), Z.to_numpy()])
            beta, *_ = np.linalg.lstsq(X, g["y"].to_numpy(), rcond=None)
            e = g["y"].to_numpy() - X @ beta
            n, L = len(g), 20
            S = (X * e[:, None]).T @ (X * e[:, None])
            for l in range(1, L + 1):
                G = (X[l:] * e[l:, None]).T @ (X[:-l] * e[:-l, None])
                S += (1 - l / (L + 1)) * (G + G.T)
            V = np.linalg.pinv(X.T @ X) @ S @ np.linalg.pinv(X.T @ X)
            se = np.sqrt(np.diag(V))
            reg[(h, lab)] = (beta[1], beta[1] / se[1])
            lines.append(f"| {h} 日 | {lab} | {beta[1]:+.3%}（{beta[1] / se[1]:.1f}） | {beta[2]:+.3%}（{beta[2] / se[2]:.1f}） | {n} |")
    m_in, m_out = res[(main_key, "樣本內 2008–2015")], res[(main_key, "樣本外 2016 ~ 2026/04")]
    c1 = m_out["diff"] > 0 and m_out["t"] > 2
    c2 = m_in["diff"] > 0
    c3 = cw["diff"] > 0
    a, b, f = reg[(20, "2008–2015")], reg[(20, "2016 ~ 2026/04")], reg[(20, "全期")]
    c4 = np.sign(a[0]) == np.sign(b[0]) and abs(f[1]) > 2
    lines += ["", "## 判定", "",
              f"1. 主規則樣本外年化差額 > 0 且 t > 2：{m_out['diff']:+.2%}（{m_out['t']:.1f}） → {'✓' if c1 else '✗'}",
              f"2. 主規則樣本內 > 0：{m_in['diff']:+.2%} → {'✓' if c2 else '✗'}",
              f"3. 滾動前進樣本外 > 固定比例：{cw['diff']:+.2%} → {'✓' if c3 else '✗'}",
              f"4. 預測迴歸（20 日）控制 VIX 後 P 係數兩段同號、全期 |t| > 2：{a[0]:+.3%} / {b[0]:+.3%}，全期 t {f[1]:.1f} → {'✓' if c4 else '✗'}", "",
              f"**結論：{'通過' if c1 and c2 and c3 and c4 else '未通過'}**"]
    pd.DataFrame({k: v for k, v in cands.items()}).to_csv(ROOT / "reports" / "legs" / "pcr_timing.csv")
    (ROOT / "docs" / "pcr_timing.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
