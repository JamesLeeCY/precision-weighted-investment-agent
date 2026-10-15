"""放空高殖利率除息股（除息後偏弱，策略 D）的可借量檢查（HANDOFF 待辦 5，決定是否凍結為 fv6）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/exdiv_short_borrow.py
輸出 docs/exdiv_short_borrow.md 與 reports/legs/exdiv_short_borrow.csv。

設計（看結果前固定）：
- 事件：市值前 500 名、2019-01 ~ 2026-04 的現金除息，殖利率 ≥ 5%（同 docs/dividend_events_report.md 的策略 D）；
  除息日收盤放空、持有 20 個交易日，同時持有者等權，剩餘 β 以台指期對沖，扣交易成本與借券費。
- 可借條件（同 borrow_capacity.py，只用除息日前一日以前的資料）：A 前 60 日有借券成交；B 需借股數 ≤ 前一日借券賣出額度；
  C 需借股數 ≤ 前 60 日借券成交量的 10%；D = A 且 B 且 C 且前 60 日借券費率 ≤ 5%／年。
  需借股數 = 資金 K ÷ 當日同時持有的檔數 ÷ 除息日收盤價；K = 1,000 萬、5,000 萬、2 億。
- 回測：(i) 原策略 D（借券費以市場中位數補缺值，不限制可借）；(ii) 只放空通過條件 D 的事件（K = 1,000 萬、2 億）。
- 凍結為 fv6 的建議門檻（事前寫下）：K = 2 億時條件 D 覆蓋率 ≥ 70%（以事件數計），且限制可借後兩段 Sharpe 皆 > 0.5。
  另需注意：策略 D 是看過結果後才加的，即使通過也只能以前瞻記錄驗證。
研究結果，非投資建議。
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import borrow_capacity as bc  # noqa: E402
import dividend_events as de  # noqa: E402
import event_study as es  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

HOLD, MIN_YIELD = 20, 0.05
CAPITALS = {"1,000 萬": 1e7, "5,000 萬": 5e7, "2 億": 2e8}


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    adj, close, member, divs = de.load_sample(client, 1, 500)
    tickers = list(adj.columns)
    rets = adj.pct_change()
    days = rets.index
    limit = int(days.searchsorted(lp.HOLDOUT))
    m = lp.market_tri(client).pct_change().reindex(days)
    betas = rets.rolling(250, min_periods=120).cov(m).div(m.rolling(250, min_periods=120).var(), axis=0).shift(1)
    col = {t: j for j, t in enumerate(tickers)}

    d = divs.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["before"], d["after"] = d["before_price"].astype(float), d["after_price"].astype(float)
    d = d[(d["before"] > 0) & (d["after"] > 0) & (d["after"] < d["before"])]
    d["yield"] = 1 - d["after"] / d["before"]
    d = d[(d["yield"] >= MIN_YIELD) & (d["date"] >= "2019-01-01") & (d["date"] < lp.HOLDOUT)].drop_duplicates(["ticker", "date"])
    d["k0"] = [int(days.searchsorted(x)) for x in d["date"]]
    d = d[(d["k0"] < limit - 1).to_numpy() & np.array([days[k] == x if k < len(days) else False for k, x in zip(d["k0"], d["date"])], dtype=bool)]
    d = d[[bool(member.iat[k, col[t]]) for k, t in zip(d["k0"], d["ticker"])]].reset_index(drop=True)
    d["seg"] = np.where(d["date"] < lp.SPLIT, "2019–2022", "2023–2026/04")

    fee = hc.lending_fees(client, tickers, days)
    quota, lend60 = bc.load_short_data(client, tickers, days)
    active = np.zeros(len(days))
    for k in d["k0"]:
        active[k:min(k + HOLD, limit)] += 1
    rows = []
    for r in d.itertuples():
        k, t = r.k0, r.ticker
        n_act = max(active[k], 1)
        px = close.iat[k, col[t]]
        a = lend60.iat[k, col[t]] > 0
        f = fee.iat[k, col[t]]
        row = {"ticker": t, "date": r.date, "seg": r.seg, "A": bool(a), "fee": f}
        for lab, K in CAPITALS.items():
            need = K / n_act / px if px > 0 else np.inf
            q = quota.iat[k, col[t]]
            b = bool(q == q and q >= need)
            c_ = bool(need <= bc.DEPTH_FRAC * lend60.iat[k, col[t]])
            row[f"B_{lab}"], row[f"C_{lab}"] = b, c_
            row[f"D_{lab}"] = bool(a and b and c_ and f == f and f <= bc.FEE_MAX)
        rows.append(row)
    R = pd.DataFrame(rows)
    d = pd.concat([d, R[[c for c in R.columns if c[:2] in ("A", "B_", "C_", "D_") or c == "fee"]]], axis=1)

    cs = SimpleNamespace(rets=rets, betas=betas, tx=lp.tx_continuous(client))

    def short_book(ev):
        pos = {}
        for r in ev.itertuples():
            for k in range(r.k0, min(r.k0 + HOLD, limit - 1)):
                pos.setdefault(days[k], set()).add(r.ticker)
        return {dd: pd.Series(-1 / len(v), index=sorted(v)) for dd, v in pos.items()}
    sims = {"原策略 D（不限制可借）": es.simulate_daily(short_book(d), cs, fee),
            "只放空通過條件 D（資金 1,000 萬）": es.simulate_daily(short_book(d[d["D_1,000 萬"]]), cs, fee),
            "只放空通過條件 D（資金 2 億）": es.simulate_daily(short_book(d[d["D_2 億"]]), cs, fee)}
    pd.DataFrame({k: v["ret"] for k, v in sims.items()}).to_csv(ROOT / "reports" / "legs" / "exdiv_short_borrow.csv")

    lines = ["# 放空高殖利率除息股的可借量檢查（自動產生）", "",
             "由 [analysis/exdiv_short_borrow.py](../analysis/exdiv_short_borrow.py) 產生；設計見程式開頭（看結果前固定）。"
             "覆蓋率 = 通過條件的事件占比（0–100%）。Sharpe = 年化報酬 ÷ 波動，格式 2019–2022 / 2023–2026/04。研究結果，非投資建議。", "",
             f"事件：市值前 500 名、殖利率 ≥ 5% 的現金除息 {len(d)} 筆（2019–2022 {int((d['seg'] == '2019–2022').sum())}、"
             f"2023–2026/04 {int((d['seg'] != '2019–2022').sum())}）；同時持有檔數平均 {active[active > 0].mean():.1f}、最多 {int(active.max())}。", "",
             "## 1. 可借條件覆蓋率", "",
             f"A 前 60 日有借券成交：{d['A'].mean():.0%}；借券費率中位數 {d['fee'].median():.2f}%／年，費率 > 5% 的占比 {(d['fee'] > 5).mean():.0%}。", "",
             "| 資金 | B 借券賣出額度足夠 | C ≤ 60 日借券量 10% | D 全部條件 | D：2019–2022 | D：2023–2026/04 |", "|---|---|---|---|---|---|"]
    for lab in CAPITALS:
        by = d.groupby("seg")[f"D_{lab}"].mean()
        lines.append(f"| {lab} | {d[f'B_{lab}'].mean():.0%} | {d[f'C_{lab}'].mean():.0%} | {d[f'D_{lab}'].mean():.0%} | "
                     f"{by.get('2019–2022', np.nan):.0%} | {by.get('2023–2026/04', np.nan):.0%} |")
    lines += ["", "## 2. 回測（除息日收盤放空、持有 20 日，台指期對沖，扣交易成本與借券費）", "",
              "| 版本 | 事件數 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 年化波動 | 最大回撤 | 有部位的日子 | 借券成本／年 |", "|---|---|---|---|---|---|---|---|---|"]
    st = {}
    for name, sim in sims.items():
        s = hc.stats(sim["ret"])
        st[name] = s
        n_ev = len(d) if "原策略" in name else int(d["D_1,000 萬" if "1,000" in name else "D_2 億"].sum())
        yrs = len(sim) / 252
        lines.append(f"| {name} | {n_ev} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} | "
                     f"{(sim['n'] > 0).mean():.0%} | — |")
    lines += ["", "逐年 Sharpe：", ""]
    for name, s in st.items():
        lines.append(f"- {name}：" + "、".join(f"{y}:{v:+.1f}" for y, v in s["yearly"].items() if v == v))
    cov = d["D_2 億"].mean()
    s2 = st["只放空通過條件 D（資金 2 億）"]
    ok = cov >= 0.7 and s2["sh_oos"] > 0.5 and s2["sh_is"] > 0.5
    lines += ["", "## 3. 判定（凍結為 fv6 的建議門檻）", "",
              f"- K = 2 億時條件 D 覆蓋率 ≥ 70%：{cov:.0%} {'✓' if cov >= 0.7 else '✗'}",
              f"- 限制可借後兩段 Sharpe 皆 > 0.5：{s2['sh_oos']:.2f} / {s2['sh_is']:.2f} {'✓' if s2['sh_oos'] > 0.5 and s2['sh_is'] > 0.5 else '✗'}", "",
              f"**結論：{'建議凍結為前瞻規格 fv6（需使用者確認）' if ok else '不建議凍結'}**"]
    (ROOT / "docs" / "exdiv_short_borrow.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
