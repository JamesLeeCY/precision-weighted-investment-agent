"""I016 美股大型科技公司財報反應 → 台股連結股（點子卡 research/ideas/I016-us-earnings-to-taiwan-linked-stocks.md 的檢定計畫，看結果前固定）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/us_earnings_link.py
輸出 docs/us_earnings_link.md 與 reports/legs/us_earnings_link.csv。

- 美股 15 家（事前固定）：AAPL、MSFT、AMZN、GOOGL、META、NVDA、AMD、AVGO、QCOM、INTC、MU、TXN、AMAT、LRCX、CSCO。
  財報事件 = SEC EDGAR 8-K Item 2.02（2019-01 ~ 2026-04），acceptanceDateTime（UTC）換成美東時間判斷盤前／盤後。
  8-K 常在新聞稿後數小時才受理（例如 NVDA 16:20 發布、20–21 時受理），所以受理時間在美東 16:00 後或跨日者，
  發布時間視為申報日 16:30（盤後，台北隔日 04:30／05:30，台股開盤前）；盤前、盤中受理者用受理時間。
  SEC 要求請求標頭附聯絡資訊（使用者同意使用其學校信箱；只送到 data.sec.gov）。
- EAR = 公司報酬 − SPY 報酬：盤後（≥ 16:00）公告取下一個美股交易日，盤前（< 9:30）取當日，盤中取當日。美股價格：FinMind USStockPrice。
- 台股第 0 日 = 公告時間之後第一個開盤（台北 09:00）的台股交易日；第 +1 日收盤進場；主視窗 CAR[+2, +21]（相對加權指數含息），
  另報告 [0, +1] 與 [0, +21]。
- 連結度：事件前第 271 ~ 第 21 個台股交易日（250 日），台股個股殘差（個股 − 加權指數含息）對美股公司前一個美股交易日殘差（公司 − SPY）迴歸的斜率 t 值；
  只用當日成員；每個產業（成員 ≥ 6）內分三組。
- 主統計量 D = sign(EAR) ×（高連結組平均 CAR − 低連結組平均 CAR），各產業的差先平均；事件依台股第 0 日所在週群集計算 t。
- 輔助：(a) 個股迴歸 CAR = a + b·(EAR × 連結度) + c·EAR + d·連結度 + SUE + 事件前 60 日報酬（排名），依週群集；
  (b) 只取 |EAR| 高於該公司過去 8 次中位數的事件。（c）Apple 官方供應商名單未做（名單 PDF 不完整，屬次要、只報告方向）。
- 驗證：市值第 501–1000 名，同樣方法。
- 可交易：第 +1 日收盤，EAR > 0 做多高連結、放空低連結（EAR < 0 相反），持有 20 日；同時進行的事件等權合併；
  放空只用借券條件 D；台指期對沖；扣成本與借券費（只做主樣本）。
- 通過（全部成立）：(1) D 兩段 > 0、全期 t > 2；(2) 迴歸 EAR × 連結度係數全期 t > 2；(3) 驗證樣本 D 同號；(4) 可交易兩段 Sharpe > 0。
  若 [0, +1] 反應占 [0, +21] 大部分且 (1) 不成立 → 判定為「開盤即反映」。
研究結果，非投資建議。
"""
import json
import math
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import borrow_capacity as bc  # noqa: E402
import corp_event_study as ce  # noqa: E402
import dividend_surprise as dsu  # noqa: E402
import event_study as es  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

CIK = {"AAPL": 320193, "MSFT": 789019, "AMZN": 1018724, "GOOGL": 1652044, "META": 1326801, "NVDA": 1045810, "AMD": 2488,
       "AVGO": 1730168, "QCOM": 804328, "INTC": 50863, "MU": 723125, "TXN": 97476, "AMAT": 6951, "LRCX": 707549, "CSCO": 858877}
SEC_UA = "precision-weighted-investment-agent research d10b49003@ntu.edu.tw"
SEC_DIR = ROOT / "data_cache" / "events" / "sec"
WINDOWS = {"[0, +1]": (0, 1), "[+2, +21]": (2, 21), "[0, +21]": (0, 21)}
MAIN = "[+2, +21]"


def sec_json(url: str, name: str) -> dict:
    SEC_DIR.mkdir(parents=True, exist_ok=True)
    p = SEC_DIR / name
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    time.sleep(0.5)
    r = requests.get(url, headers={"User-Agent": SEC_UA, "Accept-Encoding": "gzip, deflate"}, timeout=60)
    r.raise_for_status()
    p.write_text(r.text, encoding="utf-8")
    return r.json()


def earnings_events() -> pd.DataFrame:
    rows = []
    for tk, cik in CIK.items():
        sub = sec_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", f"CIK{cik:010d}.json")
        blocks = [sub["filings"]["recent"]]
        for f in sub["filings"].get("files", []):
            if f.get("filingTo", "9999") >= "2018-12-01":
                blocks.append(sec_json(f"https://data.sec.gov/submissions/{f['name']}", f["name"]))
        for b in blocks:
            for form, items, acc, fdate in zip(b["form"], b["items"], b["acceptanceDateTime"], b["filingDate"]):
                if form == "8-K" and "2.02" in str(items):
                    rows.append({"ticker_us": tk, "filing_date": fdate, "accept": acc})
    ev = pd.DataFrame(rows).drop_duplicates(["ticker_us", "filing_date"])
    utc = pd.to_datetime(ev["accept"].str[:19]).dt.tz_localize("UTC")      # acceptanceDateTime 為 UTC
    acc_et = utc.dt.tz_convert("America/New_York").dt.tz_localize(None)
    fdate = pd.to_datetime(ev["filing_date"])
    # 8-K 常在新聞稿後數小時才受理：受理時間在美東 16:00 後或跨日者，視為申報日 16:30（盤後）發布；盤前、盤中用受理時間
    after = (acc_et.dt.hour >= 16) | (acc_et.dt.normalize() > fdate)
    rel_et = acc_et.where(~after, fdate + pd.Timedelta(hours=16, minutes=30))
    ev["accept"] = rel_et
    ev["accept_tpe"] = rel_et.dt.tz_localize("America/New_York").dt.tz_convert("Asia/Taipei").dt.tz_localize(None)
    ev = ev[(ev["accept"] >= "2019-01-01") & (ev["accept"] < "2026-05-01")]
    return ev.sort_values("accept").reset_index(drop=True)


def us_prices(client, tickers) -> pd.DataFrame:
    out = {}
    for t in tickers:
        d = client.get("USStockPrice", t, "2017-06-01")
        if not d.empty:
            out[t] = pd.Series(d["Adj_Close"].astype(float).to_numpy(), index=pd.to_datetime(d["date"]))
    return pd.DataFrame(out).sort_index()


def reaction_day(us_days: pd.DatetimeIndex, accept: pd.Timestamp) -> pd.Timestamp | None:
    d = accept.normalize()
    after = accept.hour >= 16                                            # accept 為美東時間
    k = us_days.searchsorted(d, side="right" if after else "left")
    return us_days[k] if k < len(us_days) else None


def taipei_open_after(tw_days: pd.DatetimeIndex, tpe: pd.Timestamp) -> int:
    """台北時間，找之後第一個台股開盤（09:00）的交易日位置。"""
    k = int(tw_days.searchsorted(tpe.normalize(), side="left"))
    if k < len(tw_days) and tw_days[k] == tpe.normalize() and tpe.hour >= 9:
        k += 1
    return k


def link_t(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """y：T × N，x：T；每欄的 OLS 斜率 t 值（含截距）；缺值逐欄處理。"""
    out = np.full(y.shape[1], np.nan)
    for j in range(y.shape[1]):
        m = np.isfinite(y[:, j]) & np.isfinite(x)
        if m.sum() < 120:
            continue
        xx, yy = x[m] - x[m].mean(), y[m, j] - y[m, j].mean()
        sxx = (xx ** 2).sum()
        if sxx <= 0:
            continue
        b = (xx * yy).sum() / sxx
        e = yy - b * xx
        se = math.sqrt((e ** 2).sum() / (m.sum() - 2) / sxx)
        out[j] = b / se if se > 0 else np.nan
    return out


def analyse(S: ce.Sample, ev: pd.DataFrame, us_res: pd.DataFrame, tw_res: np.ndarray, trade: bool, client) -> dict:
    days = S.days
    rows, stock_rows = [], []
    books = []
    for r in ev.itertuples():
        k0 = r.k0
        if k0 < 272 or k0 + 2 >= S.limit:
            continue
        win = np.arange(k0 - 271, k0 - 20)
        prev_us = us_res[r.ticker_us].reindex(us_res.index)
        # 台股第 t 日對應「前一個美股交易日」（日期嚴格較早）
        usd = us_res.index
        xs = np.array([prev_us.iloc[usd.searchsorted(days[t], side="left") - 1] if usd.searchsorted(days[t], side="left") > 0 else np.nan for t in win])
        mem = S.member.to_numpy()[k0].astype(bool)
        cols = np.where(mem)[0]
        tv = link_t(tw_res[win][:, cols], xs)
        df = pd.DataFrame({"col": cols, "t": tv, "sec": S.sec_arr[cols]}).dropna()
        diffs, longs, shorts = [], [], []
        for sec, g in df.groupby("sec"):
            if len(g) < 6:
                continue
            q = g["t"].rank(pct=True)
            hi, lo = g.loc[q > 2 / 3, "col"].to_numpy(), g.loc[q <= 1 / 3, "col"].to_numpy()
            ch, cl = np.nanmean(S.car(hi, k0 + 2, k0 + 21)), np.nanmean(S.car(lo, k0 + 2, k0 + 21))
            diffs.append((ch - cl, np.nanmean(S.car(hi, k0, k0 + 1)) - np.nanmean(S.car(lo, k0, k0 + 1)),
                          np.nanmean(S.car(hi, k0, k0 + 21)) - np.nanmean(S.car(lo, k0, k0 + 21))))
            longs += list(hi)
            shorts += list(lo)
        if not diffs:
            continue
        sgn = np.sign(r.ear)
        dd = np.nanmean(np.array(diffs), axis=0)
        rows.append({"t0": days[k0], "week": days[k0].to_period("W"), "ticker_us": r.ticker_us, "ear": r.ear, "big": r.big,
                     "seg": "2019–2022" if days[k0] < lp.SPLIT else "2023–2026/04",
                     MAIN: sgn * dd[0], "[0, +1]": sgn * dd[1], "[0, +21]": sgn * dd[2]})
        for c_, tval in zip(df["col"], df["t"]):
            stock_rows.append({"week": days[k0].to_period("W"), "car": float(S.car(int(c_), k0 + 2, k0 + 21)), "ear": r.ear, "link": tval,
                               "sue": S.sue.iat[k0, int(c_)], "p60": S.pre60.iat[k0, int(c_)], "seg": rows[-1]["seg"]})
        if trade:
            L, Sh = (longs, shorts) if r.ear > 0 else (shorts, longs)
            books.append((k0, [S.tickers[c] for c in L], [S.tickers[c] for c in Sh]))
    D = pd.DataFrame(rows)
    out = {"D": D}
    st = pd.DataFrame(stock_rows).dropna()
    reg = {}
    for seg, g in (("2019–2022", st[st["seg"] == "2019–2022"]), ("2023–2026/04", st[st["seg"] == "2023–2026/04"]), ("全期", st)):
        if len(g) < 200:
            continue
        z = lambda v: (v - v.mean()) / v.std()  # noqa: E731
        X = np.column_stack([np.ones(len(g)), z(g["ear"]) * z(g["link"]), z(g["ear"]), z(g["link"]),
                             g["sue"].rank(pct=True) - 0.5, g["p60"].rank(pct=True) - 0.5])
        beta, se = dsu.ols_cluster(g["car"].to_numpy(float), X, g["week"].astype(str).to_numpy())
        reg[seg] = (beta[1], beta[1] / se[1], len(g))
    out["reg"] = reg
    if trade:
        fee = hc.lending_fees(client, S.tickers, days)
        quota, lend60 = bc.load_short_data(client, S.tickers, days)
        pos = {}
        for k0, L, Sh in books:
            kk = k0 + 1
            okS = []
            for t in Sh:
                j = S.col[t]
                px = S.close.iat[kk, j]
                need = 2e8 / max(len(Sh), 1) / px if px > 0 else np.inf
                f = fee.iat[kk, j]
                if lend60.iat[kk, j] > 0 and quota.iat[kk, j] >= need and need <= bc.DEPTH_FRAC * lend60.iat[kk, j] and f == f and f <= bc.FEE_MAX:
                    okS.append(t)
            for k in range(kk, min(kk + 20, S.limit - 1)):
                pos.setdefault(days[k], []).append((L, okS))
        wmap = {}
        for d, lst in pos.items():
            w = {}
            for L, Sh in lst:
                for t in L:
                    w[t] = w.get(t, 0) + 1 / len(L) / len(lst)
                for t in Sh:
                    w[t] = w.get(t, 0) - 1 / len(Sh) / len(lst) if Sh else w.get(t, 0)
            wmap[d] = pd.Series(w, dtype=float)
        sim = es.simulate_daily(wmap, SimpleNamespace(rets=S.rets, betas=S.betas, tx=S.tx), fee)
        out["trade"] = hc.stats(sim["ret"])
        out["ret"] = sim["ret"]
    return out


def wk(D: pd.DataFrame, col: str) -> tuple[float, float, int]:
    g = D.dropna(subset=[col]).groupby("week")[col].mean()
    if len(g) < 5:
        return float("nan"), float("nan"), len(g)
    return float(g.mean()), float(g.mean() / g.std(ddof=1) * math.sqrt(len(g))), len(g)


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    ev = earnings_events()
    us = us_prices(client, list(CIK) + ["SPY"])
    us_ret = us.pct_change()
    us_res = us_ret[list(CIK)].sub(us_ret["SPY"], axis=0)
    ear = []
    for r in ev.itertuples():
        d = reaction_day(us_ret.index, r.accept)
        ear.append(us_res.at[d, r.ticker_us] if d is not None and d in us_res.index else np.nan)
    ev["ear"] = ear
    ev = ev.dropna(subset=["ear"]).reset_index(drop=True)
    ev["big"] = False
    for tk, g in ev.groupby("ticker_us"):
        a = g["ear"].abs()
        med = a.shift(1).rolling(8, min_periods=4).median()
        ev.loc[g.index, "big"] = (a > med).to_numpy()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    lines = ["# I016 美股大型科技公司財報反應 → 台股連結股（自動產生）", "",
             "由 [analysis/us_earnings_link.py](../analysis/us_earnings_link.py) 產生；檢定計畫見點子卡 "
             "[I016](../research/ideas/I016-us-earnings-to-taiwan-linked-stocks.md)（看結果前固定）。"
             "D = sign(美股財報反應) ×（同產業高連結 − 低連結台股的累積異常報酬），括號為 t 值（依事件週群集）。研究結果，非投資建議。", "",
             f"財報事件（SEC 8-K Item 2.02，2019-01 ~ 2026-04）：{len(ev)} 次；美東 16:00 後受理 {int((ev['accept'].dt.hour >= 16).sum())} 次、"
             f"開盤前 {int((ev['accept'].dt.hour < 9).sum())} 次。"
             f"美股財報反應 |EAR| 中位數 {ev['ear'].abs().median():.1%}。", ""]
    res = {}
    for name, (lo, hi) in (("前 500 名（主樣本）", (1, 500)), ("第 501–1000 名（驗證）", (501, 1000))):
        S = ce.Sample(client, lo, hi, mkt, tx)
        m = mkt.pct_change().reindex(S.days)
        tw_res = S.rets.sub(m, axis=0).to_numpy(copy=True)
        e = ev.copy()
        e["k0"] = [taipei_open_after(S.days, a) for a in e["accept_tpe"]]
        r = analyse(S, e, us_res, tw_res, trade=(lo == 1), client=client)
        res[name] = r
        D = r["D"]
        lines += [f"## {name}", "", f"可用事件 {len(D)} 次。", "",
                  "| 分組 | 期間 | 事件數 | " + " | ".join(WINDOWS) + " |", "|---|---|---|" + "---|" * len(WINDOWS)]
        for lab, g in (("全部事件", D), ("|EAR| 大於公司過去 8 次中位數", D[D["big"]])):
            for seg, s in ((("2019–2022", g[g["seg"] == "2019–2022"]), ("2023–2026/04", g[g["seg"] == "2023–2026/04"])) if lab == "全部事件" else ()) + (("全期", g),):
                lines.append(f"| {lab} | {seg} | {len(s)} | " + " | ".join(ce.fmt(wk(s, w)) for w in WINDOWS) + " |")
        lines += ["", "個股迴歸（CAR[+2,+21] ~ EAR × 連結度 + EAR + 連結度 + SUE + 事件前 60 日報酬，依週群集）：", "",
                  "| 期間 | 樣本數 | EAR × 連結度 係數（t） |", "|---|---|---|"]
        for seg, (b, t, n) in r["reg"].items():
            lines.append(f"| {seg} | {n} | {b:+.3%}（{t:.1f}） |")
        if "trade" in r:
            s = r["trade"]
            lines += ["", f"可交易版本（第 +1 日收盤進場、持有 20 日，放空只用條件 D，台指期對沖，扣成本與借券費）：Sharpe {s['sh_oos']:.2f} / {s['sh_is']:.2f}、"
                      f"年化 {s['ann']:+.1%}、最大回撤 {s['mdd']:.1%}。"]
        lines.append("")
    D, V = res["前 500 名（主樣本）"]["D"], res["第 501–1000 名（驗證）"]["D"]
    a, b, f = wk(D[D["seg"] == "2019–2022"], MAIN), wk(D[D["seg"] == "2023–2026/04"], MAIN), wk(D, MAIN)
    reg = res["前 500 名（主樣本）"]["reg"].get("全期", (np.nan, np.nan, 0))
    v = wk(V, MAIN)
    tr = res["前 500 名（主樣本）"]["trade"]
    c1 = a[0] > 0 and b[0] > 0 and f[1] > 2
    c2 = reg[1] > 2
    c3 = np.sign(v[0]) == np.sign(f[0]) and f[0] == f[0]
    c4 = tr["sh_oos"] > 0 and tr["sh_is"] > 0
    open_share = wk(D, "[0, +1]")[0] / wk(D, "[0, +21]")[0] if wk(D, "[0, +21]")[0] else float("nan")
    overall = "通過" if c1 and c2 and c3 and c4 else "未通過"
    if not c1 and open_share == open_share and open_share > 0.5:
        overall += "（開盤即反映：[0, +1] 占 [0, +21] 的 " + f"{open_share:.0%}）"
    lines += ["## 判定", "",
              f"1. D 兩段 > 0、全期 t > 2：{ce.fmt(a)}、{ce.fmt(b)}、全期 {ce.fmt(f)} → {'✓' if c1 else '✗'}",
              f"2. 迴歸 EAR × 連結度全期 t > 2：{reg[0]:+.3%}（{reg[1]:.1f}） → {'✓' if c2 else '✗'}",
              f"3. 驗證樣本 D 同號：{ce.fmt(v)} → {'✓' if c3 else '✗'}",
              f"4. 可交易兩段 Sharpe > 0：{tr['sh_oos']:.2f} / {tr['sh_is']:.2f} → {'✓' if c4 else '✗'}", "",
              f"**結論：{overall}**", "", "未做：Apple 官方供應商名單的次要檢定（名單 PDF 缺 2019、2020 年版本）。"]
    pd.DataFrame({"ret": res["前 500 名（主樣本）"]["ret"]}).to_csv(ROOT / "reports" / "legs" / "us_earnings_link.csv")
    (ROOT / "docs" / "us_earnings_link.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
