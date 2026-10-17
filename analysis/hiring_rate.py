"""I022 員工人數成長（雇用率；點子卡 research/ideas/I022-employee-hiring-rate.md，檢定計畫看結果前固定）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/hiring_rate.py
輸出 docs/hiring_rate.md；原始頁快取在 data_cache/events/corp_raw/t100sb15_<市場>_<民國年>.html（每年每市場 1 次請求）。

設計（依點子卡；點子卡沒寫清楚、在看結果前補上的細節以「補」標示）：
- 資料：公開資訊觀測站 ajax_t100sb15（經 /mops/api/redirectToOld）「非擔任主管職務之全時員工薪資」，取「員工人數－年度平均」；
  每頁只有當年度人數，前一年度人數取前一年度的查詢（補）。資料年度 106 ~ 113（2017 ~ 2024）。
- 揭示日：點子卡事前固定為 7 月第一個交易日進場（每年 6 月底前申報）。
- 訊號：HR = (N_t − N_t−1) ÷ [(N_t + N_t−1)/2]；兩年度人數都 ≥ 100 人；形成年 Y = 資料年度 + 1（2019 ~ 2025），持有 12 個月。
- 樣本：7 月第一個交易日的市值前 500 名成員（成員檔當年），排除「金融保險」「金融業」；驗證第 501–1000 名。兩段：形成年 2019–2022 / 2023–2025。
- 主檢定：持有期間每月最後一個交易日的產業內 Spearman IC（−HR vs 之後 20 個交易日報酬；視窗須在 2026-05 前結束），
  兩段平均與 Newey-West t（落後 11）；另列每次形成的 12 個月報酬 IC。
- 增量：每月 Fama-MacBeth：20 日報酬 = a + b·(−HR) + c·AG + d·SUE + e·log 市值 + 產業固定效果（百分位 − 0.5；AG 同 analysis/asset_growth.py）；
  報告 HR 與 AG、年營收成長的平均等級相關。
- 可交易：每年 7 月第一個交易日換倉，產業內 −HR 前 30% 做多、後 30% 放空（ls_turnover.ew_ls_buffer，q_in = 0.3），借券條件 D（2 億）、
  台指期對沖，單邊 0.29625% ＋ 借券費；最後一次持有到 2026-04。
- 通過：(1) 月頻 IC 兩段 > 0、全期 t > 2；(2) Fama-MacBeth b 全期 t > 2、兩段同號；(3) 驗證樣本全期 IC 同號；(4) 多空兩段 Sharpe > 0。
  形成只有 7 次，即使通過也只建議前瞻記錄。
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
import asset_growth as agm  # noqa: E402
import borrow_capacity as bc  # noqa: E402
import corp_event_study as ce  # noqa: E402
import fetch_corp_events as fc  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from sue_attention import nw_t  # noqa: E402

FIN = ("金融保險", "金融業")
YEARS = range(106, 114)


def fetch(typek: str, y: int) -> str:
    def get():
        s = requests.Session()
        s.headers.update({"User-Agent": fc.UA, "Origin": "https://mops.twse.com.tw", "Referer": "https://mops.twse.com.tw/mops/",
                          "Accept": "application/json, text/plain, */*"})
        for k in range(4):
            try:
                body = {"apiName": "ajax_t100sb15", "parameters": {"TYPEK": typek, "RYEAR": str(y), "year": str(y),
                                                                    "encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1}}
                url = s.post("https://mops.twse.com.tw/mops/api/redirectToOld", json=body, timeout=60).json()["result"]["url"]
                time.sleep(2.5)
                h = s.get(url, timeout=120, headers={"Accept": "text/html"})
                h.encoding = "utf-8"
                if h.status_code == 200 and len(h.content) > 1000:
                    time.sleep(2.5)
                    return h.text
            except (requests.RequestException, KeyError, ValueError) as e:
                print(f"  {type(e).__name__}，重試", flush=True)
            time.sleep(15 * (k + 1))
        raise RuntimeError(f"員工薪資 {typek} {y} 多次失敗")
    return fc.cached(f"t100sb15_{typek}_{y}.html", get)


def employees() -> pd.DataFrame:
    """[stock_id, year（西元資料年度）, n]。"""
    rows = []
    for y in YEARS:
        for typek in ("sii", "otc"):
            t = fetch(typek, y)
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S | re.I):
                c = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S | re.I)]
                if len(c) >= 6 and re.fullmatch(r"\d{4}", c[1] or ""):
                    n = re.sub(r"[^\d.]", "", c[4])
                    if n:
                        rows.append({"stock_id": c[1], "year": y + 1911, "n": float(n)})
            print(f"員工人數 {typek} {y}：累計 {len(rows)} 筆", flush=True)
    return pd.DataFrame(rows).drop_duplicates(["stock_id", "year"])


def hr_table(emp: pd.DataFrame) -> pd.DataFrame:
    p = emp.pivot(index="year", columns="stock_id", values="n")
    prev = p.shift(1)
    hr = (p - prev) / ((p + prev) / 2)
    hr = hr.where((p >= 100) & (prev >= 100))
    hr.index = hr.index + 1                                          # 形成年 = 資料年度 + 1
    return hr


def first_july(days: pd.DatetimeIndex, y: int):
    k = int(days.searchsorted(pd.Timestamp(y, 7, 1)))
    return k if k < len(days) else None


def signal_daily(S, hr: pd.DataFrame, sector) -> pd.DataFrame:
    """每日可用的 HR（7 月第一個交易日起持有 12 個月），只填非金融成員。"""
    out = pd.DataFrame(np.nan, index=S.days, columns=S.tickers)
    for y in range(2019, 2026):
        k = first_july(S.days, y)
        k2 = first_july(S.days, y + 1)
        if k is None or y not in hr.index:
            continue
        k2 = k2 if k2 is not None else len(S.days)
        mem = S.member.iloc[k]
        v = pd.Series({t: hr.loc[y].get(t.split(".")[0], np.nan) for t in S.tickers})
        v = v.where(mem.to_numpy(bool) & ~sector.reindex(S.tickers).isin(FIN).to_numpy())
        out.iloc[k:k2] = np.tile(v.to_numpy(), (k2 - k, 1))
    return out


def month_ic(S, sig, sector, h=20) -> pd.Series:
    out = {}
    for d in agm.month_ends(S.days, S.limit):
        k = int(S.days.searchsorted(d))
        if k + h >= S.limit:
            continue
        x = sig.iloc[k].dropna()
        if len(x) < 30:
            continue
        fwd = S.adj.iloc[k + h] / S.adj.iloc[k] - 1
        out[d] = lp.within_ic(-x, fwd, sector)
    return pd.Series(out).dropna()


def seg_form(d: pd.Timestamp) -> str:
    y = d.year if d.month >= 7 else d.year - 1                       # 形成年
    return "2019–2022" if y <= 2022 else "2023–2025"


def segs(x: pd.Series, lag: int) -> dict:
    f = lambda y: (float(y.mean()), nw_t(y, lag), len(y)) if len(y) > 2 else (float("nan"), float("nan"), len(y))  # noqa: E731
    return {s: f(x[[seg_form(d) == s for d in x.index]]) for s in ("2019–2022", "2023–2025")} | {"全期": f(x)}


def fmt(x, pct=False) -> str:
    m, t, n = x
    return "—" if m != m else (f"{m:+.2%}" if pct else f"{m:+.3f}") + f"（{t:.1f}，{n}）"


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    emp = employees()
    hr = hr_table(emp)
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    S = ce.Sample(client, 1, 500, mkt, tx)
    sector = pd.Series({t: S.sector.get(t.split(".")[0], "NA") for t in S.tickers})
    sig = signal_daily(S, hr, sector)
    ic = month_ic(S, sig, sector)
    # 每次形成的 12 個月 IC
    yearly = {}
    for y in range(2019, 2026):
        k = first_july(S.days, y)
        if k is None:
            continue
        k2 = min(k + 250, S.limit - 1)
        x = sig.iloc[k].dropna()
        fwd = S.adj.iloc[k2] / S.adj.iloc[k] - 1
        yearly[y] = (lp.within_ic(-x, fwd, sector), len(x), S.days[k2].date())
    # Fama-MacBeth
    ag, _, _, _ = agm.sample_ag(S, client)
    fm, c_ag = {}, []
    for d in agm.month_ends(S.days, S.limit):
        k = int(S.days.searchsorted(d))
        if k + 20 >= S.limit:
            continue
        df = pd.DataFrame({"y": S.adj.iloc[k + 20] / S.adj.iloc[k] - 1, "hr": sig.iloc[k], "ag": ag.iloc[k], "sue": S.sue.iloc[k],
                           "lm": S.lmcap.iloc[k], "sec": sector}).dropna()
        if len(df) < 50:
            continue
        X = np.column_stack([np.ones(len(df)), -(df["hr"].rank(pct=True) - 0.5), df["ag"].rank(pct=True) - 0.5, df["sue"].rank(pct=True) - 0.5,
                             df["lm"].rank(pct=True) - 0.5, pd.get_dummies(df["sec"], drop_first=True, dtype=float).to_numpy()])
        beta, *_ = np.linalg.lstsq(X, df["y"].to_numpy(float), rcond=None)
        fm[d] = beta[1]
        c_ag.append(df["hr"].rank().corr(df["ag"].rank()))
    fm = pd.Series(fm)
    # 年營收成長相關
    c_rev = []
    revs = {t.split(".")[0]: client.get("TaiwanStockMonthRevenue", t.split(".")[0], "2017-01-01") for t in S.tickers}
    for y in range(2019, 2026):
        g = {}
        for t, r in revs.items():
            if r.empty:
                continue
            a = r[r["revenue_year"] == y - 1]["revenue"].astype(float).sum()
            b = r[r["revenue_year"] == y - 2]["revenue"].astype(float).sum()
            if a > 0 and b > 0:
                g[t] = a / b - 1
        x = pd.concat([hr.loc[y], pd.Series(g)], axis=1).dropna() if y in hr.index else pd.DataFrame()
        if len(x) > 30:
            c_rev.append(x.iloc[:, 0].rank().corr(x.iloc[:, 1].rank()))
    # 驗證
    V = ce.Sample(client, 501, 1000, mkt, tx)
    vsec = pd.Series({t: V.sector.get(t.split(".")[0], "NA") for t in V.tickers})
    vic = month_ic(V, signal_daily(V, hr, vsec), vsec)
    # 可交易
    fee = hc.lending_fees(client, S.tickers, S.days)
    quota, lend60 = bc.load_short_data(client, S.tickers, S.days)
    wd, sched = {}, []
    for y in range(2019, 2026):
        k = first_july(S.days, y)
        if k is None or k >= S.limit:
            continue
        d = S.days[k]
        x = -sig.iloc[k].dropna()
        n_short = max(1, int(len(x) * 0.3))
        need = 2e8 / n_short / S.close.iloc[k]
        sh = (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)
        wd[d] = lt.ew_ls_buffer(x, sector, sh, q_in=0.3, q_keep=None)
        sched.append(d)
    sim = hc.simulate_weights(wd, S.rets, S.betas, S.tx, sched, fee=fee)
    r = sim["ret"]
    st = {"2019–2022": lp.sharpe(r[[seg_form(d) == "2019–2022" for d in r.index]].dropna()),
          "2023–2025": lp.sharpe(r[[seg_form(d) == "2023–2025" for d in r.index]].dropna())}
    full = hc.stats(r, sim)

    a, afm, av = segs(ic, 11), segs(fm, 11), segs(vic, 11)
    c1 = a["2019–2022"][0] > 0 and a["2023–2025"][0] > 0 and a["全期"][1] > 2
    c2 = afm["全期"][1] > 2 and np.sign(afm["2019–2022"][0]) == np.sign(afm["2023–2025"][0])
    c3 = av["全期"][0] > 0
    c4 = st["2019–2022"] > 0 and st["2023–2025"] > 0
    n_firms = int(hr.loc[2019:2025].notna().sum(axis=1).mean())
    L = ["# I022 員工人數成長（自動產生）", "",
         "由 [analysis/hiring_rate.py](../analysis/hiring_rate.py) 產生；設計見程式開頭（看結果前固定）。"
         "IC 為產業內 Spearman（−HR vs 之後報酬，−1～1，0 為無預測力；正值代表員工增加少的公司較好），括號為（Newey-West t 值（落後 11），月份數）；"
         "Fama-MacBeth 係數為 −HR 百分位差 1 對應的 20 日報酬差；兩段以形成年區分（2019–2022 / 2023–2025）。研究結果，非投資建議。", "",
         f"員工人數資料：{emp['year'].min()} ~ {emp['year'].max()} 年度、{emp['stock_id'].nunique():,} 家；每年有 HR 的上市櫃公司平均 {n_firms:,} 家。"
         f"HR 與資產成長的平均等級相關 {np.mean(c_ag):+.2f}、與年營收成長 {np.mean(c_rev) if c_rev else float('nan'):+.2f}。", "",
         "| 統計量 | 形成 2019–2022 | 形成 2023–2025 | 全期 |", "|---|---|---|---|",
         "| 主樣本月頻 IC（20 日） | " + " | ".join(fmt(a[s]) for s in a) + " |",
         "| Fama-MacBeth −HR 係數（控制 AG、SUE、市值、產業） | " + " | ".join(fmt(afm[s], True) for s in afm) + " |",
         "| 驗證樣本月頻 IC（20 日） | " + " | ".join(fmt(av[s]) for s in av) + " |", "",
         "**每次形成的 12 個月報酬 IC（主樣本）**：" + "、".join(f"{y} {v[0]:+.3f}（{v[1]} 檔）" for y, v in yearly.items()), "",
         f"**可交易版本**（每年 7 月換倉，產業內前／後 30%，借券條件 D、2 億）：Sharpe {st['2019–2022']:.2f} / {st['2023–2025']:.2f}，"
         f"年化 {full['ann']:+.1%}，最大回撤 {full['mdd']:.1%}。", "", "## 判定", "",
         f"1. 月頻 IC 兩段 > 0、全期 t > 2：{fmt(a['2019–2022'])}、{fmt(a['2023–2025'])}、全期 {fmt(a['全期'])} → {'✓' if c1 else '✗'}",
         f"2. Fama-MacBeth 全期 t > 2、兩段同號：{fmt(afm['全期'], True)} → {'✓' if c2 else '✗'}",
         f"3. 驗證樣本全期 IC > 0：{fmt(av['全期'])} → {'✓' if c3 else '✗'}",
         f"4. 多空兩段 Sharpe > 0：{st['2019–2022']:.2f} / {st['2023–2025']:.2f} → {'✓' if c4 else '✗'}", "",
         f"**結論：{'通過（只建議前瞻記錄）' if c1 and c2 and c3 and c4 else '未通過'}**"]
    (ROOT / "docs" / "hiring_rate.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
