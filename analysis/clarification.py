"""I035 媒體報導法人財測的澄清公告：樂觀預估見報後的報酬反轉（點子卡 research/ideas/I035-media-forecast-clarification-reversal.md，檢定計畫看結果前固定）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/clarification.py fetch   # 公開資訊觀測站主旨（keyWord=澄清，2019–2026，上市／上櫃，約 150 次）
    .venv/Scripts/python analysis/clarification.py         # 檢定，輸出 docs/clarification.md

設計（依點子卡；補充以「補」標示）：
- 事件：主旨含「澄清」且含 媒體|報導|報載|新聞|日報|時報|晚報|週刊|雜誌|財訊|報紙；排除主旨含「更正」「補充」；
  同公司 20 個交易日內只取第一則；發言時間 13:30 以後者事件日 0 為次一交易日。2019-01 ~ 2026-04，事件日為當年前 500 名成員；驗證第 501–1000 名。
- 異常報酬：corp_event_study.Sample 的 CAR（個股 − β × 加權指數含息）；第 +1 日收盤進場，主視窗 [+2, +21]，次要 [+2, +60]。
- 配對控制：同事件日、同產業、市值五分位與前 20 日報酬三分位相同、前後 21 個交易日內沒有澄清事件的股票平均 CAR（補：成員中的五分位／三分位）；
  主統計量 = 事件 CAR − 配對 CAR；每月（事件日所在月）先平均，再算 Newey-West t（落後 5）。
- 第 +1 日漲跌幅 ≥ 9.5% 的事件記為無法交易，另列件數（仍納入主檢定，補）。
- 次要：(a) [+2,+60]；(b) 依事件前 20 日報酬三分組，最高 − 最低組的配對差額（預期 < 0）。內文分類 (c) 與 Fama-MacBeth (d) 只在主條件成立後才做。
- 可交易（只在主條件成立時）：日曆時間空頭組合（corp_event_study.short_version，持有 20 日，條件 D）與 fv5 做多排除濾網（corp_event_study.fv5_filter，20 日）。
- 通過：主檢定兩段同為負、全期 t < −2；驗證同號；全期配對差額絕對值 ≥ 1%；可交易：濾網兩段不低於 fv5 或空頭組合兩段 Sharpe > 0.5。
  事件數：前 500 名每段至少 600 則，否則停止。
研究結果，非投資建議。
"""
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import fetch_corp_events as fc  # noqa: E402

OUT = ROOT / "data_cache" / "events" / "clarification_headlines.csv"
MEDIA = re.compile(r"媒體|報導|報載|新聞|日報|時報|晚報|週刊|雜誌|財訊|報紙")


def year_rows(kind: str, y: int) -> list[dict]:
    rows, page = [], 1
    while True:
        data = {"pagenum": str(page), "Stp": "4", "r1": "1", "KIND": kind, "CODE": "", "month1": "0", "begin_day": "1", "end_day": "31",
                "keyWord": "澄清", "Condition2": "1", "keyWord2": "", "Orderby": "", "step": "2", "colorchg": "1", "co_id": "",
                "TYPEK": "", "off": "1", "firstin": "1", "i": "", "year": str(y), "month": "0", "spoke_date": "", "spoke_time": "",
                "seq_no": "", "b_date": "1", "e_date": "31", "PCount": "100"}
        t = fc.cached(f"t51_clar_{kind}_{y}_p{page}.html",
                      lambda: fc.post("https://mopsov.twse.com.tw/mops/web/ajax_t51sb10", data, "https://mopsov.twse.com.tw/mops/web/t51sb10_q1"))
        if "資料筆數過多" in t:
            raise RuntimeError(f"澄清 {kind} {y} 資料過多")
        got = fc.parse_headlines(t)
        rows += got
        pages = [int(x) for x in re.findall(r"pagenum\.value='(\d+)'", t)]
        if len(got) < 100 or not pages or page >= max(pages):
            return rows
        page += 1


def cmd_fetch():
    rows = []
    for kind in ("L", "O"):
        for y in range(2019, 2027):
            rows += year_rows(kind, y)
            print(f"{kind} {y}：累計 {len(rows)}", flush=True)
    h = pd.DataFrame(rows).drop_duplicates(["stock_id", "date", "seq", "subject"])
    h = h[h["stock_id"].astype(str).str.fullmatch(r"\d{4}")]
    h.to_csv(OUT, index=False)
    print(f"DONE {len(h)}", flush=True)


def events() -> pd.DataFrame:
    h = pd.read_csv(OUT, dtype={"stock_id": str, "spoke_time": str}, parse_dates=["date"])
    s = h["subject"].astype(str)
    h = h[s.str.contains("澄清") & s.str.contains(MEDIA) & ~s.str.contains("更正|補充")].copy()
    late = h["spoke_time"].fillna("0").astype(str).str.zfill(6) >= "133000"
    h["date"] = h["date"] + pd.to_timedelta(late.astype(int), unit="D")
    return h[(h["date"] >= "2019-01-01") & (h["date"] < "2026-05-01")].sort_values("date").reset_index(drop=True)


def main():
    import corp_event_study as ce
    import dotenv
    import leg_probe as lp
    from data.fetch_financials import FinMindClient
    from sue_attention import nw_t

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    raw = events()
    res = {}
    for name, (lo, hi) in (("前 500 名（主樣本）", (1, 500)), ("第 501–1000 名（驗證）", (501, 1000))):
        S = ce.Sample(client, lo, hi, mkt, tx)
        ev = S.events(raw[["stock_id", "date"]])
        ev = ev.sort_values(["ticker", "k0"])
        keep, last = [], {}
        for r in ev.itertuples():
            if r.ticker in last and r.k0 - last[r.ticker] <= 20:
                continue
            last[r.ticker] = r.k0
            keep.append(r.Index)
        ev = ev.loc[keep].sort_values("k0").reset_index(drop=True)
        ev = ev[ev["k0"] + 21 < S.limit].reset_index(drop=True)
        near = {}
        for t, k in zip(ev["ticker"], ev["k0"]):
            near.setdefault(t, []).append(k)
        mem_np, lm_np, p20_np = S.member.to_numpy(), S.lmcap.to_numpy(), S.pre20.to_numpy()
        rows = []
        for r in ev.itertuples():
            k, j = r.k0, S.col[r.ticker]
            mem = mem_np[k].astype(bool)
            q5 = pd.Series(lm_np[k]).where(mem).rank(pct=True).to_numpy()
            q3 = pd.Series(p20_np[k]).where(mem).rank(pct=True).to_numpy()
            b5, b3 = np.ceil(q5 * 5), np.ceil(q3 * 3)
            cand = np.where(mem & (S.sec_arr == S.sec_arr[j]) & (b5 == b5[j]) & (b3 == b3[j]) & np.isfinite(b5) & np.isfinite(b3))[0]
            cand = np.array([c for c in cand if c != j and not any(abs(kk - k) <= 21 for kk in near.get(S.tickers[c], []))], dtype=int)
            out = {"t0": S.days[k], "ticker": r.ticker, "k0": k, "p20": p20_np[k, j], "n_ctrl": len(cand),
                   "lim": abs(S.rets.iat[k + 1, j]) >= 0.095 if k + 1 < len(S.days) else False}
            for w, (a, b) in (("w21", (2, 21)), ("w60", (2, 60))):
                e = float(S.car(j, k + a, k + b))
                cc = float(np.nanmean(S.car(cand, k + a, k + b))) if len(cand) else np.nan
                out[w] = e - cc
                out[w + "_raw"] = e
            rows.append(out)
        D = pd.DataFrame(rows)
        D["month"] = D["t0"].dt.to_period("M")
        res[name] = (S, ev, D)

    def seg_t(D, col, lag=5):
        out = {}
        for lab, m in (("2019–2022", D["t0"] < lp.SPLIT), ("2023–2026/04", D["t0"] >= lp.SPLIT), ("全期", np.ones(len(D), bool))):
            x = D[m].groupby("month")[col].mean().dropna()
            out[lab] = (float(x.mean()), nw_t(x, lag), int(D[m][col].notna().sum()))
        return out
    fm = lambda x: "—" if x[0] != x[0] else f"{x[0]:+.2%}（{x[1]:.1f}，{x[2]}）"  # noqa: E731
    S, ev, D = res["前 500 名（主樣本）"]
    _, _, VD = res["第 501–1000 名（驗證）"]
    n1, n2 = int((D["t0"] < lp.SPLIT).sum()), int((D["t0"] >= lp.SPLIT).sum())
    a, a60, araw, v = seg_t(D, "w21"), seg_t(D, "w60"), seg_t(D, "w21_raw"), seg_t(VD, "w21")
    D["g"] = D.groupby("month")["p20"].transform(lambda x: pd.qcut(x.rank(method="first"), 3, labels=False) if len(x) >= 3 else np.nan)
    sp = D.groupby("month").apply(lambda g: g.loc[g["g"] == 2, "w21"].mean() - g.loc[g["g"] == 0, "w21"].mean())
    insufficient = n1 < 600 or n2 < 600
    c1 = a["2019–2022"][0] < 0 and a["2023–2026/04"][0] < 0 and a["全期"][1] < -2
    c2 = v["全期"][0] < 0
    c3 = abs(a["全期"][0]) >= 0.01
    L = ["# I035 媒體報導澄清公告後的報酬（自動產生）", "",
         "由 [analysis/clarification.py](../analysis/clarification.py) 產生；設計見程式開頭（看結果前固定）。"
         "CAR = 累積異常報酬（個股 − β × 加權指數含息），第 +1 日收盤進場；配對差額 = 事件 CAR − 同日、同產業、市值五分位與前 20 日報酬三分位相同的非事件股平均 CAR；"
         "括號為（Newey-West t 值，月份平均後；事件數）。研究結果，非投資建議。", "",
         f"澄清（媒體）公告 {len(raw):,} 則；前 500 名去重後事件 {len(D):,} 則（2019–2022 {n1}、2023–2026/04 {n2}；門檻每段 600），"
         f"有配對者 {int((D['n_ctrl'] > 0).sum()):,}；第 +1 日漲跌幅 ≥ 9.5%（無法交易）{int(D['lim'].sum())} 則。驗證樣本 {len(VD):,} 則。", "",
         "| 統計量 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         "| 主檢定：[+2,+21] 配對差額 | " + " | ".join(fm(a[k]) for k in a) + " |",
         "| 只報告：[+2,+21] 原始 CAR | " + " | ".join(fm(araw[k]) for k in araw) + " |",
         "| (a) [+2,+60] 配對差額 | " + " | ".join(fm(a60[k]) for k in a60) + " |",
         f"| (b) 事件前 20 日報酬最高 − 最低三分組（[+2,+21]） | — | — | {sp.mean():+.2%}（{nw_t(sp.dropna(), 5):.1f}，{sp.notna().sum()} 個月） |",
         "| 驗證樣本 [+2,+21] 配對差額 | " + " | ".join(fm(v[k]) for k in v) + " |", "",
         "## 判定", "",
         f"0. 事件數：{n1} / {n2}（門檻每段 600）→ {'不足，停止' if insufficient else '足夠'}",
         f"1. 主檢定兩段 < 0、全期 t < −2：{fm(a['全期'])} → {'✓' if c1 else '✗'}",
         f"2. 驗證同號（< 0）：{fm(v['全期'])} → {'✓' if c2 else '✗'}",
         f"3. 全期配對差額絕對值 ≥ 1%：{a['全期'][0]:+.2%} → {'✓' if c3 else '✗'}"]
    if c1 and c2 and c3 and not insufficient:
        fee = hc_fee = None
        import borrow_capacity as bc
        import hedge_construction as hc
        fee = hc.lending_fees(client, S.tickers, S.days)
        quota, lend60 = bc.load_short_data(client, S.tickers, S.days)
        sv = ce.short_version(S, ev.rename(columns={}), 20, fee, quota, lend60)
        fv = ce.fv5_filter(ev[["ticker", "t0"]], 20)
        L += [f"4. 空頭組合（2 億）：Sharpe {sv['2 億']['stats']['sh_oos']:.2f} / {sv['2 億']['stats']['sh_is']:.2f}（可借 {sv['2 億']['cover']:.0%}）；"
              f"fv5 濾網 {fv['濾網版']['sh_oos']:.2f} / {fv['濾網版']['sh_is']:.2f} vs {fv['fv5 建構（基準）']['sh_oos']:.2f} / {fv['fv5 建構（基準）']['sh_is']:.2f}"]
        ok4 = (sv["2 億"]["stats"]["sh_oos"] > 0.5 and sv["2 億"]["stats"]["sh_is"] > 0.5) or \
              (fv["濾網版"]["sh_oos"] >= fv["fv5 建構（基準）"]["sh_oos"] and fv["濾網版"]["sh_is"] >= fv["fv5 建構（基準）"]["sh_is"])
        L += ["", f"**結論：{'通過' if ok4 else '訊號成立、可交易未通過'}**"]
    else:
        L += ["", f"**結論：{'事件數不足，停止' if insufficient else '未通過（主條件不成立，依點子卡停止，不做內文分類與可交易版本）'}**"]
    (ROOT / "docs" / "clarification.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "fetch":
        cmd_fetch()
    else:
        main()
