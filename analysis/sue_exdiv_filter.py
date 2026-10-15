"""除息後偏弱當作 SUE 做多濾網（HANDOFF 待辦 4；假設來自 docs/dividend_events_report.md）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/sue_exdiv_filter.py
輸出 docs/sue_exdiv_filter.md 與 reports/legs/sue_exdiv_filter_top{300,500}.csv。

設計（看結果前固定）：
- 基準：fv3 建構（等權多空、每 3 個月換倉、三份錯開取平均、不含緩衝、可借條件 D、資金 2 億、台指期對沖、扣成本與借券費），
  前 300 名為主、前 500 名為次。比較期間從第 3 個換倉日之後開始（同 ls_offsets.py）。
- 濾網：換倉日 d 時，若某檔在 d 之前 40 個交易日內（[d−40, d−1]）有現金除息、且殖利率 ≥ 5%（1 − 除息參考價 ÷ 前一日收盤），
  就不列入做多名單（只影響做多端；放空端不變）。被排除後做多端的總權重重新正規化為原本的總額（產業內等權，產業之間按剩餘權重等比例放大）。
  除息日與殖利率來自 TaiwanStockDividendResult（已快取），在 d 之前都已發生，沒有前視。
- 為什麼是 40 日：除息後偏弱在第 +1 ~ +20 日約 −1.6%、+1 ~ +60 日約 −2.5%（主樣本），40 日取中間，只測這一個長度。
- 指標：兩段 Sharpe、年化報酬、年換手、濾網生效比例（被排除的做多權重占比，平均與最大）。
- 通過：前 300 名濾網版兩段 Sharpe 都高於基準，且前 500 名全期 Sharpe 也高於基準（同號）。只在通過時才建議修改 fv3／fv5（需另立前瞻版本，不改凍結規格）。
研究結果，非投資建議。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import borrow_capacity as bc  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402

LOOKBACK, MIN_YIELD = 40, 0.05


def exdiv_flags(c) -> pd.DataFrame:
    """布林矩陣：d 日之前 LOOKBACK 個交易日內有殖利率 ≥ MIN_YIELD 的現金除息。"""
    days = c.adj.index
    ev = np.zeros((len(days), len(c.tickers)), dtype=bool)
    col = {t: j for j, t in enumerate(c.tickers)}
    for t in c.tickers:
        d = c.client.get("TaiwanStockDividendResult", t.split(".")[0], lp.EV_START, lp.EV_END)
        if d.empty:
            continue
        d = d[(d["before_price"].astype(float) > 0) & (d["after_price"].astype(float) > 0)]
        y = 1 - d["after_price"].astype(float) / d["before_price"].astype(float)
        for x in pd.to_datetime(d.loc[y >= MIN_YIELD, "date"]):
            k = int(days.searchsorted(x))
            if k < len(days) and days[k] == x:
                ev[k, col[t]] = True
    E = pd.DataFrame(ev, index=days, columns=c.tickers).astype(int)
    recent = E.rolling(LOOKBACK, min_periods=1).sum().shift(1).fillna(0) > 0     # [d−40, d−1]
    return recent


def filter_long(w: pd.Series, flagged: pd.Series) -> tuple[pd.Series, float]:
    if w.empty:
        return w, 0.0
    longs, shorts = w[w > 0], w[w < 0]
    bad = flagged.reindex(longs.index).fillna(False).to_numpy(bool)
    share = float(longs[bad].sum() / longs.sum()) if longs.sum() > 0 else 0.0
    keep = longs[~bad]
    if keep.empty:
        return shorts, share
    keep = keep * (longs.sum() / keep.sum())
    return pd.concat([keep, shorts]), share


def analyse(top_n: int) -> dict:
    c = lp.prepare(top_n)
    scores = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
    close = bc.raw_close(c)
    sched = c.schedule
    flags = exdiv_flags(c)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    start = sched[2]
    out, turn, shares = {}, {}, []
    for name, filt in (("fv3 建構（基準）", False), ("濾網：排除 40 日內高殖利率除息股的做多", True)):
        sims = []
        for off in (0, 1, 2):
            wd = {}
            for d in sched[off::3]:
                w = lt.ew_ls_buffer(scores[d], c.sector, shortable_at(d), q_keep=None)
                if filt:
                    w, sh = filter_long(w, flags.loc[d])
                    shares.append((d, sh))
                wd[d] = w
            sims.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee))
        r = pd.concat([s["ret"][s.index > start] for s in sims], axis=1).mean(axis=1)
        out[name] = r
        turn[name] = float(np.mean([s["turnover"][s.index > start].sum() for s in sims]) / (len(r) / 252))
    sh = pd.Series(dict(shares))
    return {"series": out, "turn": turn, "share_mean": float(sh.mean()), "share_max": float(sh.max()),
            "share_active": float((sh > 0).mean()), "share_by_month": sh.groupby(sh.index.month).mean()}


def main():
    res = {n: analyse(n) for n in (300, 500)}
    lines = ["# 除息後偏弱當作 SUE 做多濾網（自動產生）", "",
             "由 [analysis/sue_exdiv_filter.py](../analysis/sue_exdiv_filter.py) 產生；設計見程式開頭（看結果前固定）。"
             "Sharpe = 年化報酬 ÷ 波動，格式 2019–2022 / 2023–2026/04；fv3 建構不含緩衝，扣交易成本與借券費、台指期對沖。研究結果，非投資建議。", ""]
    st_all = {}
    for n, r in res.items():
        lines += [f"## 市值前 {n} 名", "",
                  "| 版本 | Sharpe 2019–2022 | 2023–2026/04 | 全期 | 年化報酬 | 最大回撤 | 年換手（倍） |", "|---|---|---|---|---|---|---|"]
        st = {}
        for name, x in r["series"].items():
            s = hc.stats(x)
            s["full"] = lp.sharpe(x.dropna())
            st[name] = s
            lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} | {r['turn'][name]:.1f} |")
        bm = "、".join(f"{m} 月 {v:.0%}" for m, v in r["share_by_month"].items() if v > 0)
        lines += ["", f"濾網生效：被排除的做多權重平均 {r['share_mean']:.1%}、最多 {r['share_max']:.0%}，"
                  f"{r['share_active']:.0%} 的換倉日有排除；依換倉月份：{bm or '無'}。", ""]
        st_all[n] = st
        pd.DataFrame(r["series"]).to_csv(ROOT / "reports" / "legs" / f"sue_exdiv_filter_top{n}.csv")
    b3, f3 = st_all[300].values()
    b5, f5 = st_all[500].values()
    c1 = f3["sh_oos"] > b3["sh_oos"] and f3["sh_is"] > b3["sh_is"]
    c2 = f5["full"] > b5["full"]
    lines += ["## 判定", "", f"1. 前 300 名濾網版兩段 Sharpe 都高於基準：{'✓' if c1 else '✗'}",
              f"2. 前 500 名全期 Sharpe 高於基準：{'✓' if c2 else '✗'}", "",
              f"**結論：{'通過' if c1 and c2 else '未通過'}**"]
    (ROOT / "docs" / "sue_exdiv_filter.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
