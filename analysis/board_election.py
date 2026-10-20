"""I027 董監改選年：最後過戶日前的改選行情（點子卡 research/ideas/I027-board-election-year-runup.md，檢定計畫看結果前固定）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/board_election.py fetch    # 公開資訊觀測站重大訊息主旨（keyWord=董事、keyWord2=改選／選任，2016–2026，上市／上櫃）
    .venv/Scripts/python analysis/board_election.py          # 檢定，輸出 docs/board_election.md

設計（依點子卡；點子卡沒寫清楚、在看結果前補上的細節以「補」標示）：
- 改選年：主旨含「本公司」「股東」「董事」，且含「改選」或「選任」，排除「代子公司」「董事長」「臨時會」，另排除「補選」（補：補選不是全面改選）；
  公告年份即為改選年。預測 t 年改選 = t−3 年改選且 t−2、t−1 年沒有改選。先報告命中率（預測名單中 t 年實際有改選公告的比例）；
  命中率 < 80% 時依點子卡改用當年 1–3 月公告為事件（本程式會停在命中率報告，需另行處理）。
- 股東會日期：股利分派情形彙總表（data_cache/events/mops_dividend，年度別、股東會日期欄）；同一公司同一年取最早的常會日期。
- 最後過戶日 L = 股東會日期前 60 個日曆日當天之前的最後一個交易日（補：searchsorted 取嚴格早於該日）。
  主視窗：第 L−46 日收盤 → 第 L−1 日收盤；次要視窗：第 L−1 日收盤 → 第 L+20 日收盤。報酬為還原含息。
- 配對：同年、同產業、市值三分位與事件前 60 日報酬三分位相同（以 L−46 日、當年成員計算）、當年不改選（預測與實際皆否）、股東會月份相同，
  取 log 市值最接近者 1 檔；同產業找不到時放寬為同三分位（不限產業）。CAR 差 = 事件股 − 配對股；標準誤依（年度 × 產業）群集。
- 樣本：前 500 名（t 年成員檔）與第 501–1000 名驗證；股東會 2019–2026；視窗須在 2026-05 前結束；排除股東會日期缺值；兩段以股東會年份 2019–2022 / 2023–2026。
- 可交易：每家預測改選股在主視窗內等權持有（同時持有者等權），台指期對沖 β，進出各扣 0.29625%；Sharpe 以每日報酬計（空手日報酬 0）。
- 通過：(1) 主視窗 CAR 差兩段 > 0、全期 t > 2；(2) 驗證同號；(3) 可交易兩段為正且主視窗平均 CAR 差 > 1%；(4) 次要視窗 CAR 差 t < 2。
  前 500 名任一段事件數 < 200 → 樣本不足，只報告。
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

OUT = ROOT / "data_cache" / "events" / "board_election_headlines.csv"
INC = re.compile(r"本公司.*股東|股東.*本公司")
EXC = re.compile(r"代子公司|董事長|臨時會|補選")


def year_rows(kw2: str, kind: str, y: int) -> list[dict]:
    rows, page = [], 1
    while True:
        data = {"pagenum": str(page), "Stp": "4", "r1": "1", "KIND": kind, "CODE": "", "month1": "0", "begin_day": "1", "end_day": "31",
                "keyWord": "董事", "Condition2": "1", "keyWord2": kw2, "Orderby": "", "step": "2", "colorchg": "1", "co_id": "",
                "TYPEK": "", "off": "1", "firstin": "1", "i": "", "year": str(y), "month": "0", "spoke_date": "", "spoke_time": "",
                "seq_no": "", "b_date": "1", "e_date": "31", "PCount": "100"}
        t = fc.cached(f"t51_board_{kw2}_{kind}_{y}_p{page}.html",
                      lambda: fc.post("https://mopsov.twse.com.tw/mops/web/ajax_t51sb10", data, "https://mopsov.twse.com.tw/mops/web/t51sb10_q1"))
        got = fc.parse_headlines(t)
        rows += got
        pages = [int(x) for x in re.findall(r"pagenum\.value='(\d+)'", t)]
        if len(got) < 100 or not pages or page >= max(pages):
            return rows
        page += 1


def cmd_fetch():
    rows = []
    for kw2 in ("改選", "選任"):
        for kind in ("L", "O"):
            for y in range(2016, 2027):
                rows += year_rows(kw2, kind, y)
            print(f"{kw2} {kind}：累計 {len(rows)} 筆", flush=True)
    h = pd.DataFrame(rows).drop_duplicates(["stock_id", "date", "seq", "subject"])
    h = h[h["stock_id"].astype(str).str.fullmatch(r"\d{4}")]
    h.to_csv(OUT, index=False)
    print(f"DONE {len(h)}", flush=True)


def election_years() -> dict:
    h = pd.read_csv(OUT, dtype={"stock_id": str}, parse_dates=["date"])
    s = h["subject"].astype(str)
    ok = s.str.contains(INC) & s.str.contains("董事") & s.str.contains("改選|選任") & ~s.str.contains(EXC)
    g = h[ok].assign(y=lambda x: x["date"].dt.year)
    return g.groupby("stock_id")["y"].apply(set).to_dict()


def meetings() -> pd.DataFrame:
    import dividend_surprise as dsu
    import html as _h
    rows = []
    for p in sorted((ROOT / "data_cache" / "events" / "mops_dividend").glob("t05st09_*_*.html")):
        t = p.read_text(encoding="utf-8")
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S | re.I):
            c = [_h.unescape(re.sub(r"<[^>]+>", " ", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S | re.I)]
            if len(c) > 6 and re.match(r"^\d{4} - ", c[0]) and "年度" in c[2]:
                d = dsu.roc_date(c[6])
                if d == d:
                    rows.append({"stock_id": c[0][:4], "meeting": d})
    m = pd.DataFrame(rows)
    m = m[m["meeting"].dt.month <= 8]                                   # 股東常會（補：排除 9 月後的臨時會日期）
    return m.assign(y=m["meeting"].dt.year).groupby(["stock_id", "y"])["meeting"].min().reset_index()


def main():
    import corp_event_study as ce
    import dividend_surprise as dsu
    import dotenv
    import leg_probe as lp
    from data.fetch_financials import FinMindClient

    dotenv.load_dotenv(ROOT / ".env")
    E = election_years()
    M = meetings()
    pred, hit = [], []
    for sid, ys in E.items():
        for t in range(2019, 2027):
            if (t - 3) in ys and (t - 2) not in ys and (t - 1) not in ys:
                pred.append((sid, t))
                if t <= 2026:
                    hit.append(t in ys)
    hit_rate = float(np.mean(hit)) if hit else float("nan")
    P = pd.DataFrame(pred, columns=["stock_id", "y"])
    pred_set = set(pred)
    actual = {(s, y) for s, ys in E.items() for y in ys}
    L = ["# I027 董監改選年行情（自動產生）", "",
         "由 [analysis/board_election.py](../analysis/board_election.py) 產生；設計見程式開頭（看結果前固定）。"
         "CAR 差 = 事件股 − 配對股的累積還原報酬，括號為（t 值，依年度 × 產業群集，事件數）。研究結果，非投資建議。", "",
         f"改選公告涵蓋 {len(E):,} 家；依三年任期預測的改選（2019–2026）{len(P):,} 筆，命中率 {hit_rate:.1%}（門檻 80%）。", ""]
    if not hit_rate >= 0.8:
        L.append("**命中率低於 80%**：依點子卡應改用當年 1–3 月公告為事件，本程式停在此處（未看報酬）。")
        (ROOT / "docs" / "board_election.md").write_text("\n".join(L) + "\n", encoding="utf-8")
        print("STOP hit rate", hit_rate, flush=True)
        return
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    res = {}
    for name, (lo, hi) in (("前 500 名（主樣本）", (1, 500)), ("第 501–1000 名（驗證）", (501, 1000))):
        S = ce.Sample(client, lo, hi, mkt, tx)
        days = S.days
        sector = pd.Series({t: S.sector.get(t.split(".")[0], "NA") for t in S.tickers})
        mm = M.set_index(["stock_id", "y"])["meeting"]
        rows = []
        for y in range(2019, 2027):
            cand = [t for t in S.tickers]
            info = {}
            for t in cand:
                sid = t.split(".")[0]
                if (sid, y) not in mm.index:
                    continue
                kL = int(days.searchsorted(mm[(sid, y)] - pd.Timedelta(days=60), side="left")) - 1
                if kL - 46 < 61 or kL - 1 >= S.limit:
                    continue
                if not bool(S.member.iat[kL - 46, S.col[t]]):
                    continue
                info[t] = kL
            if not info:
                continue
            ts = list(info)
            k_ref = {t: info[t] - 46 for t in ts}
            lmc = pd.Series({t: S.lmcap.iat[k_ref[t], S.col[t]] for t in ts})
            p60 = pd.Series({t: S.pre60.iat[k_ref[t], S.col[t]] for t in ts})
            tc = pd.qcut(lmc.rank(method="first"), 3, labels=False) if lmc.notna().sum() > 10 else pd.Series(0, index=ts)
            tp = pd.qcut(p60.rank(method="first"), 3, labels=False) if p60.notna().sum() > 10 else pd.Series(0, index=ts)
            month = pd.Series({t: mm[(t.split(".")[0], y)].month for t in ts})
            is_ev = pd.Series({t: (t.split(".")[0], y) in pred_set for t in ts})
            is_act = pd.Series({t: (t.split(".")[0], y) in actual for t in ts})
            ctrl_pool = [t for t in ts if not is_ev[t] and not is_act[t]]

            def car(t, a, b):
                j = S.col[t]
                pa, pb = S.adj.iat[a, j], S.adj.iat[min(b, S.limit - 1), j]
                return pb / pa - 1 if pa > 0 and pb == pb else np.nan
            for t in [t for t in ts if is_ev[t]]:
                kL = info[t]
                same = [c for c in ctrl_pool if month[c] == month[t] and tc.get(c) == tc.get(t) and tp.get(c) == tp.get(t)]
                pool = [c for c in same if sector[c] == sector[t]] or same
                if not pool:
                    continue
                c = min(pool, key=lambda x: abs(lmc[x] - lmc[t]) if lmc[x] == lmc[x] else 9e9)
                main_d = car(t, kL - 46, kL - 1) - car(c, kL - 46, kL - 1)
                post_d = car(t, kL - 1, kL + 20) - car(c, kL - 1, kL + 20) if kL + 20 < S.limit else np.nan
                rows.append({"ticker": t, "y": y, "sec": sector[t], "kL": kL, "main": main_d, "post": post_d,
                             "rank_pos": 0, "lm": lmc[t]})
        ev = pd.DataFrame(rows)
        res[name] = (S, ev)

    def cl(df, col):
        d = df.dropna(subset=[col])
        if len(d) < 10:
            return (float(d[col].mean()) if len(d) else float("nan"), float("nan"), len(d))
        g = (d["y"].astype(str) + "_" + d["sec"].astype(str)).to_numpy()
        b, se = dsu.ols_cluster(d[col].to_numpy(float), np.ones((len(d), 1)), g)
        return float(b[0]), float(b[0] / se[0]), len(d)
    fm = lambda x: "—" if x[0] != x[0] else f"{x[0]:+.2%}（{x[1]:.1f}，{x[2]}）"  # noqa: E731
    S, ev = res["前 500 名（主樣本）"]
    _, vev = res["第 501–1000 名（驗證）"]
    seg = lambda d, s: d[(d["y"] <= 2022) if s == 1 else (d["y"] >= 2023)]  # noqa: E731
    m1, m2, mf = cl(seg(ev, 1), "main"), cl(seg(ev, 2), "main"), cl(ev, "main")
    p1, p2, pf = cl(seg(ev, 1), "post"), cl(seg(ev, 2), "post"), cl(ev, "post")
    v1 = cl(vev, "main")
    n1, n2 = len(seg(ev, 1)), len(seg(ev, 2))
    # 異質性（只報告）：市值前 150 vs 其餘（以事件股 log 市值當年排名近似，補）
    ev["big"] = ev.groupby("y")["lm"].rank(ascending=False) <= 150 * (ev.groupby("y")["lm"].transform("count") / 500)
    hb, hs = cl(ev[ev["big"]], "main"), cl(ev[~ev["big"]], "main")
    # 可交易
    pos = {}
    for r in ev.itertuples():
        for k in range(r.kL - 45, r.kL):
            pos.setdefault(k, []).append((r.ticker, k == r.kL - 45, k == r.kL - 1))
    daily = pd.Series(0.0, index=S.days[:S.limit])
    for k, items in pos.items():
        if k >= S.limit:
            continue
        names = [t for t, _, _ in items]
        cols = [S.col[t] for t in names]
        r = np.nanmean(S.rets.iloc[k, cols].to_numpy(float))
        b = np.nanmean(S.betas.iloc[k, cols].fillna(1.0).to_numpy(float))
        n_trade = sum(1 for _, a, z in items if a) + sum(1 for _, a, z in items if z)
        daily.iloc[k] = r - b * float(S.tx.get(S.days[k], 0.0)) - n_trade / len(items) * lp.STOCK_COST
    daily = daily[daily.index >= "2019-01-01"]
    sh1 = lp.sharpe(daily[daily.index < lp.SPLIT])
    sh2 = lp.sharpe(daily[daily.index >= lp.SPLIT])
    ann = float((1 + daily).prod() ** (252 / len(daily)) - 1)
    insufficient = n1 < 200 or n2 < 200
    c1 = m1[0] > 0 and m2[0] > 0 and mf[1] > 2
    c2 = v1[0] > 0
    c3 = sh1 > 0 and sh2 > 0 and mf[0] > 0.01
    c4 = not (pf[1] >= 2)
    L += ["| 統計量 | 2019–2022 | 2023–2026 | 全期 |", "|---|---|---|---|",
          f"| 主視窗 [L−45, L−1] CAR 差（前 500 名） | {fm(m1)} | {fm(m2)} | {fm(mf)} |",
          f"| 次要視窗 [L, L+20] CAR 差 | {fm(p1)} | {fm(p2)} | {fm(pf)} |",
          f"| 驗證樣本主視窗 CAR 差 | {fm(cl(seg(vev, 1), 'main'))} | {fm(cl(seg(vev, 2), 'main'))} | {fm(v1)} |",
          f"| 只報告：市值較大（約前 150 名） | — | — | {fm(hb)} |",
          f"| 只報告：市值較小（約第 151–500 名） | — | — | {fm(hs)} |", "",
          f"**可交易版本**（主視窗等權持有、台指期對沖、進出各 0.29625%）：Sharpe {sh1:.2f} / {sh2:.2f}，年化 {ann:+.1%}。", "",
          "## 判定", "",
          f"0. 樣本量：前 500 名事件 {n1} / {n2}（門檻每段 200）→ {'不足（只報告、不下結論）' if insufficient else '足夠'}",
          f"1. 主視窗 CAR 差兩段 > 0、全期 t > 2：{fm(mf)} → {'✓' if c1 else '✗'}",
          f"2. 驗證樣本同號：{fm(v1)} → {'✓' if c2 else '✗'}",
          f"3. 可交易兩段 > 0 且平均 CAR 差 > 1%：{sh1:.2f} / {sh2:.2f}、{mf[0]:+.2%} → {'✓' if c3 else '✗'}",
          f"4. 次要視窗不顯著為正（t < 2）：{fm(pf)} → {'✓' if c4 else '✗'}", "",
          f"**結論：{'樣本不足，不下結論' if insufficient else ('通過' if c1 and c2 and c3 and c4 else '未通過')}**"]
    (ROOT / "docs" / "board_election.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "fetch":
        cmd_fetch()
    else:
        main()
