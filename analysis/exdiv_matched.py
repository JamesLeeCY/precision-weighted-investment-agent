"""除息後偏弱的配對控制重做（docs/conference_report.md 的方法提醒：單邊 CAR 在 2023 年後會混入「一般股票落後加權指數」）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/exdiv_matched.py
輸出 docs/exdiv_matched.md。

設計（看結果前固定）：
- 事件：與 docs/dividend_events_report.md 相同——現金除息（除息前收盤 > 參考價），除息日 2019-01 ~ 2026-04，除息日為股票池成員；
  主樣本市值前 500 名、驗證第 501–1000 名。殖利率 = 1 − 參考價 ÷ 前一日收盤。
- 第 0 日 = 除息日（還原報酬含股利）；視窗 [+1, +5]、[+1, +20]（主要，對應原策略 D 持有 20 日）、[+1, +60]。
- 配對差額：同日、同產業、SUE 三分位與事件前 60 日報酬三分位相同、且前後 60 個交易日內沒有除息的股票（corp_event_study.matched），
  主統計量 = 事件 CAR − 配對 CAR；另報告「事件 − 同日全部成員平均」。t 值以除息日聚集。
- 通過（現象成立）：殖利率 ≥ 5% 的 [+1, +20] 配對差額，主樣本兩段皆 < 0、全期 t < −2，驗證樣本同號且 t < −2。
  不成立時，原本的「除息後偏弱」主要是一般股票落後加權指數（市場結構），不是除息本身。
研究結果，非投資建議。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import corp_event_study as ce  # noqa: E402
import leg_probe as lp  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

WINDOWS = {"[+1, +5]": (1, 5), "[+1, +20]": (1, 20), "[+1, +60]": (1, 60)}
MAIN = "[+1, +20]"


def dividend_events(S: ce.Sample) -> pd.DataFrame:
    rows = []
    for t in S.tickers:
        d = S.client.get("TaiwanStockDividendResult", t.split(".")[0], lp.EV_START, lp.EV_END)
        if d.empty:
            continue
        d = d.assign(before=d["before_price"].astype(float), after=d["after_price"].astype(float))
        d = d[(d["before"] > 0) & (d["after"] > 0) & (d["after"] < d["before"])]
        for _, r in d.iterrows():
            rows.append({"stock_id": t.split(".")[0], "date": pd.Timestamp(r["date"]), "yield": 1 - r["after"] / r["before"]})
    ev = pd.DataFrame(rows).drop_duplicates(["stock_id", "date"])
    ev = ev[(ev["date"] >= "2019-01-01") & (ev["date"] < lp.HOLDOUT)]
    ev = ev[[S.days.searchsorted(x) < len(S.days) and S.days[S.days.searchsorted(x)] == x for x in ev["date"]]]
    return ev.reset_index(drop=True)


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    lines = ["# 除息後偏弱的配對控制重做（自動產生）", "",
             "由 [analysis/exdiv_matched.py](../analysis/exdiv_matched.py) 產生；設計見程式開頭（看結果前固定）。CAR = 累積異常報酬（個股 − β × 加權指數含息）；"
             "「配對差額」= 事件股 CAR − 同日同產業、SUE 與事件前 60 日報酬三分位相同、前後 60 日內沒有除息的股票平均 CAR；括號為 t 值（同一除息日先平均）。"
             "研究結果，非投資建議。", ""]
    res = {}
    for name, (lo, hi) in (("前 500 名（主樣本）", (1, 500)), ("第 501–1000 名（驗證）", (501, 1000))):
        S = ce.Sample(client, lo, hi, mkt, tx)
        raw = dividend_events(S)
        ev = S.events(raw)
        ev = ev[ev["k0"] + 1 < S.limit]
        m = ce.matched(S, ev, ev, WINDOWS, exclude_span=60)
        mem = S.member.to_numpy()
        for w, (a, b) in WINDOWS.items():
            m[f"{w}_all"] = [float(np.nanmean(S.car(np.where(mem[k])[0], k + a, k + b))) for k in m["k0"]]
            m[f"{w}_vs_all"] = m[w] - m[f"{w}_all"]
        res[name] = m
        hy = m[m["yield"] >= 0.05]
        lines += [f"## {name}", "", f"現金除息事件 {len(m)} 筆（殖利率 ≥ 5%：{len(hy)} 筆）；有配對者 {int((m['n_ctrl'] > 0).sum())} 筆，平均配對 {m.loc[m['n_ctrl'] > 0, 'n_ctrl'].mean():.1f} 檔。", "",
                  "| 分組 | 統計量 | 期間 | " + " | ".join(WINDOWS) + " |", "|---|---|---|" + "---|" * len(WINDOWS)]
        for g, gdf in (("殖利率 ≥ 5%", hy), ("全部除息", m)):
            for lab, suf in (("原始 CAR（原研究）", ""), ("同日全部成員平均", "_all"), ("事件 − 全部成員平均", "_vs_all"), ("配對差額", "_diff")):
                for seg, s in (("2019–2022", gdf[gdf["seg"] == "2019–2022"]), ("2023–2026/04", gdf[gdf["seg"] == "2023–2026/04"]), ("全期", gdf)):
                    lines.append(f"| {g} | {lab} | {seg} | " + " | ".join(ce.fmt(ce.clustered(s, f"{w}{suf}")) for w in WINDOWS) + " |")
        lines.append("")
    hy = res["前 500 名（主樣本）"]
    hy = hy[hy["yield"] >= 0.05]
    v = res["第 501–1000 名（驗證）"]
    v = v[v["yield"] >= 0.05]
    a = ce.clustered(hy[hy["seg"] == "2019–2022"], f"{MAIN}_diff")
    b = ce.clustered(hy[hy["seg"] == "2023–2026/04"], f"{MAIN}_diff")
    f = ce.clustered(hy, f"{MAIN}_diff")
    vv = ce.clustered(v, f"{MAIN}_diff")
    c1 = a[0] < 0 and b[0] < 0 and f[1] < -2
    c2 = vv[0] < 0 and vv[1] < -2
    lines += ["## 判定（殖利率 ≥ 5%、[+1, +20] 配對差額）", "",
              f"1. 主樣本兩段 < 0、全期 t < −2：{ce.fmt(a)}、{ce.fmt(b)}、全期 {ce.fmt(f)} → {'✓' if c1 else '✗'}",
              f"2. 驗證樣本同號且 t < −2：{ce.fmt(vv)} → {'✓' if c2 else '✗'}", "",
              f"**結論：{'除息後偏弱在配對控制後仍成立' if c1 and c2 else '配對控制後不成立，原本的除息後偏弱主要是市場結構（一般股票落後加權指數）'}**"]
    (ROOT / "docs" / "exdiv_matched.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
