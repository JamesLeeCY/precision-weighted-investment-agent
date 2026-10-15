"""I011 董監事／內部人持股轉讓事前申報（點子卡 research/ideas/I011-insider-transfer-predeclaration.md 的檢定計畫，看結果前固定）。

用法（於專案根目錄；先執行 fetch_corp_events.py insider）：
    .venv/Scripts/python analysis/insider_transfer_events.py
輸出 docs/insider_transfer_events.md 與 reports/legs/insider_transfer_events.csv。

- 事件：公開資訊觀測站「董監事持股轉讓事前申報」，申報日 2019-01 ~ 2026-04。
  賣出組：轉讓方式含「一般交易」「鉅額逐筆」「盤後定價」；安慰劑組：「贈與」「信託」；其他（洽特定人、私募股票等）不檢定。
  排除異動情形註記為變更申報者；同一公司 20 個交易日內同組多筆合併為一個事件（第一筆申報日、股數加總）。
- 第 0 日 = 申報日（視為盤後），第 +1 日收盤進場；主視窗 [+2, +21]，次要 [+2, +61]，描述 [−60, −1] 與 [+1]。
- 主統計量：配對差額（同日、同產業、SUE 三分位與事件前 60 日報酬三分位相同、前後 20 日內沒有賣出申報的股票；corp_event_study.py）。
- 分組（描述）：申報股數占持股前已發行股數 ≥ 0.5%（以事件前市值與股價估計股數）、事件前 60 日報酬前三分之一、上市／上櫃。
- 可交易 A：放空 20 日（條件 D）；B：fv5 做多名單排除過去 20 日內有賣出申報者。
- 通過（全部成立）：(1) 主樣本賣出組 [+2, +21] 配對差額兩段皆 < 0、全期 t < −2；(2) 驗證樣本同號且 t < −2；
  (3) 安慰劑組全期 |t| < 2；(4) A 扣成本後兩段 Sharpe > 0 且 2 億時可放空比例 ≥ 70%，或 B 兩段 Sharpe 都高於 fv5。
研究結果，非投資建議。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import borrow_capacity as bc  # noqa: E402
import corp_event_study as ce  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

WINDOWS = {"[−60, −1]": (-60, -1), "[+1]": (1, 1), "[+2, +21]": (2, 21), "[+2, +61]": (2, 61)}
MAIN = "[+2, +21]"
SELL = ("一般交易", "鉅額逐筆", "盤後定價")
PLACEBO = ("贈與", "信託")


def group_of(method: str) -> str:
    m = str(method)
    if any(x in m for x in SELL):
        return "賣出"
    if any(x in m for x in PLACEBO):
        return "安慰劑"
    return ""


def load_events() -> pd.DataFrame:
    d = pd.read_csv(ROOT / "data_cache" / "events" / "insider_transfers.csv", dtype={"stock_id": str}, parse_dates=["date"])
    d = d[d["stock_id"].str.fullmatch(r"\d{4}") & ~d["change"].fillna("").str.startswith("本單為變更")].copy()
    d["grp"] = d["method"].map(group_of)
    d = d[(d["grp"] != "") & (d["date"] >= "2019-01-01") & (d["date"] < lp.HOLDOUT)].sort_values("date")
    days = pd.bdate_range("2018-01-01", "2026-12-31")
    d["k"] = days.searchsorted(d["date"])
    out = []
    for (sid, grp), g in d.groupby(["stock_id", "grp"]):
        start, shares, first = None, 0.0, None
        for r in g.itertuples():
            if start is None or r.k - start > 20:
                if first is not None:
                    out.append(first | {"shares": shares})
                start, shares = r.k, 0.0
                first = {"stock_id": sid, "grp": grp, "date": r.date, "market": r.market, "role": r.role}
            shares += r.transfer_total if r.transfer_total == r.transfer_total else 0.0
        if first is not None:
            out.append(first | {"shares": shares})
    return pd.DataFrame(out).sort_values("date").reset_index(drop=True)


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    raw = load_events()
    lines = ["# I011 董監事／內部人持股轉讓事前申報（自動產生）", "",
             "由 [analysis/insider_transfer_events.py](../analysis/insider_transfer_events.py) 產生；檢定計畫見點子卡 "
             "[I011](../research/ideas/I011-insider-transfer-predeclaration.md)（看結果前固定）。「配對差額」= 事件股 CAR − 同日同產業、"
             "SUE 與事件前 60 日報酬三分位相同的非事件股平均 CAR；括號為 t 值（同一事件日先平均）。研究結果，非投資建議。", "",
             f"申報（合併 20 日內同組多筆後，2019-01 ~ 2026-04）：賣出組 {int((raw['grp'] == '賣出').sum())} 筆、安慰劑組 {int((raw['grp'] == '安慰劑').sum())} 筆。", ""]
    res = {}
    for name, (lo, hi) in (("前 500 名（主樣本）", (1, 500)), ("第 501–1000 名（驗證）", (501, 1000))):
        S = ce.Sample(client, lo, hi, mkt, tx)
        ev_all = S.events(raw)
        sells = ev_all[ev_all["grp"] == "賣出"]
        out = {}
        for grp in ("賣出", "安慰劑"):
            e = ce.matched(S, ev_all[ev_all["grp"] == grp], sells, WINDOWS, exclude_span=20)
            mc = np.exp(np.array([S.lmcap.iat[k, S.col[t]] for t, k in zip(e["ticker"], e["k0"])]))
            px = np.array([S.close.iat[k - 1, S.col[t]] for t, k in zip(e["ticker"], e["k0"])])
            e["pct"] = e["shares"] / (mc / px)
            out[grp] = e
        reg = ce.regression(S, out["賣出"], MAIN, WINDOWS[MAIN])
        res[name] = {"S": S, "ev": out, "reg": reg}
        s_ev, p_ev = out["賣出"], out["安慰劑"]
        lines += [f"## {name}", "", f"賣出組 {len(s_ev)} 筆（有配對 {int((s_ev['n_ctrl'] > 0).sum())}）、安慰劑組 {len(p_ev)} 筆。", "",
                  "| 分組 | 期間 | 事件數 | " + " | ".join(f"{w} 差額" for w in WINDOWS) + " |", "|---|---|---|" + "---|" * len(WINDOWS)]
        q = s_ev["[−60, −1]"].rank(pct=True)
        for g, gdf, segs in (("賣出組", s_ev, True), ("安慰劑組（贈與、信託）", p_ev, False),
                             ("賣出：申報股數 ≥ 0.5%", s_ev[s_ev["pct"] >= 0.005], False), ("賣出：< 0.5%", s_ev[s_ev["pct"] < 0.005], False),
                             ("賣出：事件前 60 日報酬前 1/3", s_ev[q > 2 / 3], False), ("賣出：上市", s_ev[s_ev["market"] == "sii"], False),
                             ("賣出：上櫃", s_ev[s_ev["market"] == "otc"], False)):
            for seg, sdf in ((("2019–2022", gdf[gdf["seg"] == "2019–2022"]), ("2023–2026/04", gdf[gdf["seg"] == "2023–2026/04"])) if segs else ()) + (("全期", gdf),):
                lines.append(f"| {g} | {seg} | {len(sdf)} | " + " | ".join(ce.fmt(ce.clustered(sdf, f'{w}_diff')) for w in WINDOWS) + " |")
        lines += ["", f"未配對的原始 CAR（賣出組，全期）：" + "、".join(f"{w} {ce.fmt(ce.clustered(s_ev, w))}" for w in WINDOWS) + "。",
                  f"截面迴歸（{MAIN}，控制 SUE、事件前 20／60 日報酬、log 市值，事件日分群）：賣出事件係數 {reg['b']:+.2%}（t {reg['t']:.1f}），事件 {reg['n']} 筆。", ""]
        if lo == 1:
            fee = hc.lending_fees(client, S.tickers, S.days)
            quota, lend60 = bc.load_short_data(client, S.tickers, S.days)
            A = ce.short_version(S, s_ev, 20, fee, quota, lend60)
            res[name]["A"] = A
            lines += ["可交易 A（第 +1 日收盤放空 20 日，只放空條件 D 通過者，台指期對沖，扣成本與借券費）：", "",
                      "| 資金 | 可放空比例 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 最大回撤 | 有部位的日子 |", "|---|---|---|---|---|---|---|"]
            for lab, a in A.items():
                s = a["stats"]
                lines.append(f"| {lab} | {a['cover']:.0%} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} | {a['active']:.0%} |")
            lines.append("")
    B = ce.fv5_filter(res["前 500 名（主樣本）"]["ev"]["賣出"][["ticker", "t0"]], 20)
    lines += ["## 可交易 B：fv5 做多名單排除過去 20 日內有賣出申報者", "", f"被排除的做多權重平均 {B['share']:.1%}。", "",
              "| 版本 | Sharpe 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|"]
    for k in ("fv5 建構（基準）", "濾網版"):
        lines.append(f"| {k} | {B[k]['sh_oos']:.2f} | {B[k]['sh_is']:.2f} | {B[k]['full']:.2f} |")
    m = res["前 500 名（主樣本）"]["ev"]
    v = res["第 501–1000 名（驗證）"]["ev"]["賣出"]
    a = ce.clustered(m["賣出"][m["賣出"]["seg"] == "2019–2022"], f"{MAIN}_diff")
    b = ce.clustered(m["賣出"][m["賣出"]["seg"] == "2023–2026/04"], f"{MAIN}_diff")
    f = ce.clustered(m["賣出"], f"{MAIN}_diff")
    vv = ce.clustered(v, f"{MAIN}_diff")
    pl = ce.clustered(m["安慰劑"], f"{MAIN}_diff")
    c1 = a[0] < 0 and b[0] < 0 and f[1] < -2
    c2 = vv[0] < 0 and vv[1] < -2
    c3 = pl[1] == pl[1] and abs(pl[1]) < 2
    A2 = res["前 500 名（主樣本）"]["A"]["2 億"]
    c4 = (A2["stats"]["sh_oos"] > 0 and A2["stats"]["sh_is"] > 0 and A2["cover"] >= 0.7) or \
         (B["濾網版"]["sh_oos"] > B["fv5 建構（基準）"]["sh_oos"] and B["濾網版"]["sh_is"] > B["fv5 建構（基準）"]["sh_is"])
    lines += ["", "## 判定", "",
              f"1. 主樣本賣出組 {MAIN} 配對差額兩段 < 0、全期 t < −2：{ce.fmt(a)}、{ce.fmt(b)}、全期 {ce.fmt(f)} → {'✓' if c1 else '✗'}",
              f"2. 驗證樣本同號且 t < −2：{ce.fmt(vv)} → {'✓' if c2 else '✗'}",
              f"3. 安慰劑組全期 |t| < 2：{ce.fmt(pl)} → {'✓' if c3 else '✗'}",
              f"4. 可交易（A：2 億兩段 Sharpe > 0 且可放空 ≥ 70%；或 B 兩段優於 fv5）：{'✓' if c4 else '✗'}", "",
              f"**結論：{'通過' if c1 and c2 and c3 and c4 else '未通過'}**"]
    pd.DataFrame({k: x["ret"] for k, x in res["前 500 名（主樣本）"]["A"].items()}).to_csv(ROOT / "reports" / "legs" / "insider_transfer_events.csv")
    (ROOT / "docs" / "insider_transfer_events.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
