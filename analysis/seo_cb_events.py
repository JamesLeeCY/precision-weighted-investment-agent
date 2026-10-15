"""I012 現金增資與可轉債發行公告（點子卡 research/ideas/I012-seo-cb-issuance-underperformance.md 的檢定計畫，看結果前固定）。

用法（於專案根目錄；先執行 fetch_corp_events.py headlines）：
    .venv/Scripts/python analysis/seo_cb_events.py classify   # 只做主旨分類，印出 2019 年抽查樣本（看報酬前）
    .venv/Scripts/python analysis/seo_cb_events.py            # 完整檢定
輸出 docs/seo_cb_events.md 與 reports/legs/seo_cb_events.csv。

- 事件：公開資訊觀測站重大訊息主旨（董事會），發言日期 2019-01 ~ 2026-04。分類（點子卡規則）：
  CB = 主旨含「董事會」且含「發行」與「轉換公司債」，排除含「子公司」「代子公司」「取得」「停止轉換」「海外」「私募」；
  SEO = 主旨含「現金增資」且含「發行新股」或「發行普通股」或「辦理現金增資」，排除含「子公司」「代」「參與」「私募」「初次上市」「上櫃前」
  「海外存託憑證」「不繼續」；主旨含「修正」「補充」者不另成事件；同公司 120 個交易日內同類只取第一筆。
  依點子卡用 2019 年抽查 50 筆修正一次（看報酬前）：CB 另排除「變更」「調整」，SEO 另排除「調整」「變更」「授權」「基準日」
  （抽查發現「調整 107 年現金增資發行股數及價格」被誤列為新事件）；之後凍結。
- 第 0 日 = 發言日（盤後也算第 0 日），第 +1 日收盤進場；主視窗 [+2, +61]，次要 [+2, +21]、[+2, +121]，描述 [−60, −1] 與 [+1]。
- 主統計量：配對差額（同日、同產業、SUE 三分位與事件前 60 日報酬三分位相同的非事件股；corp_event_study.py）。
- 可交易 A：放空 60 日（條件 D）；B：fv5 做多名單排除過去 60 日內有 CB／SEO 公告者。
- 通過（全部成立）：(1) 主樣本 CB＋SEO 的 [+2, +61] 配對差額兩段皆 < 0、全期 t < −2；(2) 第 501–1000 名同號且 t < −2；
  (3) A 扣成本後兩段 Sharpe > 0 且 2 億時可放空比例 ≥ 70%，或 B 兩段 Sharpe 都高於 fv5。
- 未做（點子卡列為描述或次要）：競價拍賣／詢價圈購與發行規模分組（需逐則明細約 1,000 次請求）、CB 申報生效日的發行期賣壓（日期未取得，依卡片規定不做）。
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
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import borrow_capacity as bc  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

WINDOWS = {"[−60, −1]": (-60, -1), "[+1]": (1, 1), "[+2, +21]": (2, 21), "[+2, +61]": (2, 61), "[+2, +121]": (2, 121)}
MAIN = "[+2, +61]"
CB_EX = ("子公司", "代子公司", "取得", "停止轉換", "海外", "私募", "變更", "調整")
SEO_EX = ("子公司", "代", "參與", "私募", "初次上市", "上櫃前", "海外存託憑證", "不繼續", "調整", "變更", "授權", "基準日")


def classify(subject: str) -> str:
    s = str(subject)
    if "修正" in s or "補充" in s:
        return ""
    if "董事會" in s and "發行" in s and "轉換公司債" in s and not any(x in s for x in CB_EX):
        return "CB"
    if "現金增資" in s and any(x in s for x in ("發行新股", "發行普通股", "辦理現金增資")) and not any(x in s for x in SEO_EX):
        return "SEO"
    return ""


def load_events() -> pd.DataFrame:
    h = pd.read_csv(ROOT / "data_cache" / "events" / "corp_headlines.csv", dtype={"stock_id": str, "spoke_time": str}, parse_dates=["date"])
    h = h[h["stock_id"].str.fullmatch(r"\d{4}")].copy()
    h["type"] = h["subject"].map(classify)
    h = h[h["type"] != ""].drop_duplicates(["stock_id", "date", "type"]).sort_values("date")
    h = h[(h["date"] >= "2019-01-01") & (h["date"] < lp.HOLDOUT)]
    keep, last = [], {}
    days = pd.bdate_range("2018-01-01", "2026-12-31")
    for i, r in h.iterrows():
        key = (r["stock_id"], r["type"])
        k = days.searchsorted(r["date"])
        if key in last and k - last[key] <= 120:
            continue
        last[key] = k
        keep.append(i)
    return h.loc[keep].reset_index(drop=True)


def cmd_classify():
    h = pd.read_csv(ROOT / "data_cache" / "events" / "corp_headlines.csv", dtype={"stock_id": str}, parse_dates=["date"])
    h["type"] = h["subject"].map(classify)
    print("全部主旨", len(h), "；分類", h["type"].value_counts().to_dict())
    y19 = h[h["date"].dt.year == 2019]
    for lab, g in (("分到 CB／SEO 的（抽 30）", y19[y19["type"] != ""]), ("沒分到的（抽 20）", y19[y19["type"] == ""])):
        print("====", lab)
        for _, r in g.sample(min(len(g), 30 if "分到" in lab else 20), random_state=0).iterrows():
            print(f"{r['type'] or '—':>3} {r['stock_id']} {r['date']:%Y-%m-%d} {r['subject'][:80]}")
    ev = load_events()
    print("去重後事件", len(ev), ev["type"].value_counts().to_dict(), "；年分布", ev["date"].dt.year.value_counts().sort_index().to_dict())


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    raw = load_events()
    lines = ["# I012 現金增資與可轉債發行公告（自動產生）", "",
             "由 [analysis/seo_cb_events.py](../analysis/seo_cb_events.py) 產生；檢定計畫見點子卡 "
             "[I012](../research/ideas/I012-seo-cb-issuance-underperformance.md)（看結果前固定）。CAR = 累積異常報酬（個股 − β × 加權指數含息）；"
             "「配對差額」= 事件股 CAR − 同日同產業、SUE 與事件前 60 日報酬三分位相同的非事件股平均 CAR；括號為 t 值（同一事件日先平均）。研究結果，非投資建議。", "",
             f"董事會決議公告（去重後，2019-01 ~ 2026-04）：CB {int((raw['type'] == 'CB').sum())} 筆、SEO {int((raw['type'] == 'SEO').sum())} 筆。", ""]
    res = {}
    for name, (lo, hi) in (("前 500 名（主樣本）", (1, 500)), ("第 501–1000 名（驗證）", (501, 1000))):
        S = ce.Sample(client, lo, hi, mkt, tx)
        ev = S.events(raw)
        ev = ce.matched(S, ev, ev, WINDOWS, exclude_span=121)
        reg = ce.regression(S, ev, MAIN, WINDOWS[MAIN])
        res[name] = {"S": S, "ev": ev, "reg": reg}
        lines += [f"## {name}", "", f"事件 {len(ev)} 筆（CB {int((ev['type'] == 'CB').sum())}、SEO {int((ev['type'] == 'SEO').sum())}）；"
                  f"有配對股者 {int((ev['n_ctrl'] > 0).sum())} 筆，平均配對 {ev.loc[ev['n_ctrl'] > 0, 'n_ctrl'].mean():.1f} 檔。", "",
                  "| 分組 | 期間 | 事件數 | " + " | ".join(f"{w} 差額" for w in WINDOWS) + " |", "|---|---|---|" + "---|" * len(WINDOWS)]
        for g, gdf in (("CB＋SEO", ev), ("CB", ev[ev["type"] == "CB"]), ("SEO", ev[ev["type"] == "SEO"]),
                       ("上市", ev[ev["market"] == "sii"]), ("上櫃", ev[ev["market"] == "otc"])):
            for seg, sdf in (("2019–2022", gdf[gdf["seg"] == "2019–2022"]), ("2023–2026/04", gdf[gdf["seg"] == "2023–2026/04"]), ("全期", gdf)):
                if g != "CB＋SEO" and seg != "全期":
                    continue
                lines.append(f"| {g} | {seg} | {len(sdf)} | " + " | ".join(ce.fmt(ce.clustered(sdf, f'{w}_diff')) for w in WINDOWS) + " |")
        lines += ["", f"未配對的原始 CAR（CB＋SEO，全期）：" + "、".join(f"{w} {ce.fmt(ce.clustered(ev, w))}" for w in WINDOWS) + "。",
                  f"截面迴歸（{MAIN}，控制 SUE、事件前 20／60 日報酬、log 市值，事件日分群）：事件係數 {reg['b']:+.2%}（t {reg['t']:.1f}），事件 {reg['n']} 筆。", ""]
        if lo == 1:
            fee = hc.lending_fees(client, S.tickers, S.days)
            quota, lend60 = bc.load_short_data(client, S.tickers, S.days)
            A = ce.short_version(S, ev, 60, fee, quota, lend60)
            res[name]["A"] = A
            lines += ["可交易 A（第 +1 日收盤放空 60 日，只放空條件 D 通過者，台指期對沖，扣成本與借券費）：", "",
                      "| 資金 | 可放空比例 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 最大回撤 | 有部位的日子 |", "|---|---|---|---|---|---|---|"]
            for lab, a in A.items():
                s = a["stats"]
                lines.append(f"| {lab} | {a['cover']:.0%} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} | {a['active']:.0%} |")
            lines.append("")
    B = ce.fv5_filter(res["前 500 名（主樣本）"]["ev"][["ticker", "t0"]], 60)
    lines += ["## 可交易 B：fv5 做多名單排除過去 60 日內有 CB／SEO 公告者", "",
              f"被排除的做多權重平均 {B['share']:.1%}。", "", "| 版本 | Sharpe 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|"]
    for k in ("fv5 建構（基準）", "濾網版"):
        lines.append(f"| {k} | {B[k]['sh_oos']:.2f} | {B[k]['sh_is']:.2f} | {B[k]['full']:.2f} |")
    m, v = res["前 500 名（主樣本）"]["ev"], res["第 501–1000 名（驗證）"]["ev"]
    a = ce.clustered(m[m["seg"] == "2019–2022"], f"{MAIN}_diff")
    b = ce.clustered(m[m["seg"] == "2023–2026/04"], f"{MAIN}_diff")
    f = ce.clustered(m, f"{MAIN}_diff")
    vv = ce.clustered(v, f"{MAIN}_diff")
    c1 = a[0] < 0 and b[0] < 0 and f[1] < -2
    c2 = vv[0] < 0 and vv[1] < -2
    A2 = res["前 500 名（主樣本）"]["A"]["2 億"]
    c3 = (A2["stats"]["sh_oos"] > 0 and A2["stats"]["sh_is"] > 0 and A2["cover"] >= 0.7) or \
         (B["濾網版"]["sh_oos"] > B["fv5 建構（基準）"]["sh_oos"] and B["濾網版"]["sh_is"] > B["fv5 建構（基準）"]["sh_is"])
    lines += ["", "## 判定", "",
              f"1. 主樣本 {MAIN} 配對差額兩段 < 0、全期 t < −2：{ce.fmt(a)}、{ce.fmt(b)}、全期 {ce.fmt(f)} → {'✓' if c1 else '✗'}",
              f"2. 驗證樣本同號且 t < −2：{ce.fmt(vv)} → {'✓' if c2 else '✗'}",
              f"3. 可交易（A：2 億兩段 Sharpe > 0 且可放空 ≥ 70%；或 B 兩段優於 fv5）：{'✓' if c3 else '✗'}", "",
              f"**結論：{'通過' if c1 and c2 and c3 else '未通過'}**"]
    pd.DataFrame({k: x["ret"] for k, x in res["前 500 名（主樣本）"]["A"].items()}).to_csv(ROOT / "reports" / "legs" / "seo_cb_events.csv")
    (ROOT / "docs" / "seo_cb_events.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    cmd_classify() if sys.argv[1:] == ["classify"] else main()
