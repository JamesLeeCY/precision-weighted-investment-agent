"""I033 fv5 腿內逆變異數權重（點子卡 research/ideas/I033-fv5-inverse-volatility-leg-weights.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/fv5_invvol.py
輸出 docs/fv5_invvol.md。

設計（依點子卡；補充以「補」標示）：
- 名單與 fv5 相同（lt.ew_ls_buffer：產業內前／後 1/3、不含緩衝、只放空可借者）；只改各腿內的權重：
  W1 w ∝ 1/σ²、W2 w ∝ 1/σ；σ = 換倉日前 60 個交易日（不含當日）含息日報酬標準差，不足 40 日用該腿中位數。
  各腿總權重不變（= 原等權版本的腿總和）；單檔上限 3 倍、下限 1/3 倍等權，超過或不足部分依比例分給其他股（迭代至收斂）。
- 放空端依新權重重算需借股數（需借 = 2 億 × 權重 ÷ 收盤價），不通過條件 D 者剔除後其餘重新正規化（補：只做一輪）。
- 其餘同 fv5：每 3 個換倉日換倉、三份錯開、台指期對沖、單邊 0.29625% ＋ 借券費。
- 通過：W1 或 W2 兩段 Sharpe ≥ fv5、全期 ≥ fv5 全期 + 0.10、最大回撤不大於 fv5；兩者都通過以 W1 為準。
- 只報告：有效檔數（1/Σw²）、加權平均 60 日波動、只改做多腿、只改放空腿。
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
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402


def capped(raw: pd.Series, total: float) -> pd.Series:
    n = len(raw)
    eq = total / n
    w = raw / raw.sum() * total
    for _ in range(50):
        lo, hi = eq / 3, eq * 3
        cl = w.clip(lo, hi)
        free = (cl > lo) & (cl < hi)
        excess = total - cl.sum()
        if abs(excess) < 1e-12 or not free.any():
            w = cl
            break
        cl[free] += excess * cl[free] / cl[free].sum()
        w = cl
    return w


def main():
    c = lp.prepare(500)
    sched = c.schedule
    fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
    close = bc.raw_close(c)
    sue = lp.leg_scores(c, "sue")
    vol = c.rets.rolling(60, min_periods=40).std().shift(1)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    stats_eff = {}

    def reweight(d, w, power, legs=("long", "short")):
        out = []
        for leg, sign in (("long", 1), ("short", -1)):
            x = w[w * sign > 0].abs()
            if not len(x) or leg not in legs:
                out.append(x * sign)
                continue
            s = vol.loc[d].reindex(x.index)
            s = s.fillna(s.median())
            nw = capped(1 / s ** power, float(x.sum()))
            if sign < 0:
                need = lt.K_CAPITAL * nw / close.loc[d].reindex(nw.index)
                ok = (lend60.loc[d].reindex(nw.index) > 0) & (quota.loc[d].reindex(nw.index) >= need) \
                    & (need <= bc.DEPTH_FRAC * lend60.loc[d].reindex(nw.index)) & (fee.loc[d].reindex(nw.index) <= bc.FEE_MAX)
                nw = nw[ok.to_numpy(bool)]
                nw = nw / nw.sum() * float(x.sum()) if len(nw) else nw
            stats_eff.setdefault((power, legs, leg), []).append((1 / float(((nw / nw.sum()) ** 2).sum()) if len(nw) else np.nan,
                                                                  float((nw / nw.sum() * s.reindex(nw.index)).sum()) * np.sqrt(252) if len(nw) else np.nan))
            out.append(nw * sign)
        return pd.concat(out)

    def book(fn):
        parts = []
        for off in range(3):
            wd = {d: fn(d, lt.ew_ls_buffer(sue[d], c.sector, shortable_at(d), q_keep=None)) for d in sched[off::3]}
            parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)["ret"])
        x = pd.concat(parts, axis=1).mean(axis=1)
        x = x[x.index > sched[2]]
        return hc.stats(x) | {"full": lp.sharpe(x.dropna())}

    base_eff = []

    def base(d, w):
        for sign in (1, -1):
            x = w[w * sign > 0].abs()
            s = vol.loc[d].reindex(x.index)
            base_eff.append((sign, len(x), float((x / x.sum() * s.fillna(s.median())).sum()) * np.sqrt(252)))
        return w
    res = {"fv5（等權）": book(base),
           "W1 逆變異數 1/σ²": book(lambda d, w: reweight(d, w, 2)),
           "W2 逆標準差 1/σ": book(lambda d, w: reweight(d, w, 1)),
           "只報告：W1 只改做多腿": book(lambda d, w: reweight(d, w, 2, ("long",))),
           "只報告：W1 只改放空腿": book(lambda d, w: reweight(d, w, 2, ("short",)))}
    b = res["fv5（等權）"]

    def ok(s):
        return s["sh_oos"] >= b["sh_oos"] and s["sh_is"] >= b["sh_is"] and s["full"] >= b["full"] + 0.10 and s["mdd"] >= b["mdd"]
    p1, p2 = ok(res["W1 逆變異數 1/σ²"]), ok(res["W2 逆標準差 1/σ"])
    be = pd.DataFrame(base_eff, columns=["sign", "n", "vol"])
    L = ["# I033 fv5 腿內逆變異數權重（自動產生）", "",
         "由 [analysis/fv5_invvol.py](../analysis/fv5_invvol.py) 產生；設計見程式開頭（看結果前固定）。"
         "Sharpe 為扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後，格式 2019–2022 / 2023–2026/04；最大回撤為三份錯開組合的日報酬計算。研究結果，非投資建議。", "",
         "| 版本 | Sharpe | 全期 | 年化報酬 | 年化波動 | 最大回撤 |", "|---|---|---|---|---|---|"]
    for k, s in res.items():
        L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} |")
    L += ["", "**腿的特性（換倉日平均）**", "",
          f"- 等權：做多 {be[be.sign > 0].n.mean():.0f} 檔（加權年化波動 {be[be.sign > 0].vol.mean():.0%}）、放空 {be[be.sign < 0].n.mean():.0f} 檔（{be[be.sign < 0].vol.mean():.0%}）。"]
    for (pw, legs, leg), v in stats_eff.items():
        if legs == ("long", "short"):
            a = np.array(v, dtype=float)
            L.append(f"- {'W1' if pw == 2 else 'W2'} {'做多' if leg == 'long' else '放空'}腿：有效檔數 {np.nanmean(a[:, 0]):.0f}、加權年化波動 {np.nanmean(a[:, 1]):.0%}")
    L += ["", "## 判定", "",
          f"通過條件：兩段 Sharpe ≥ fv5（{b['sh_oos']:.2f} / {b['sh_is']:.2f}）、全期 ≥ {b['full'] + 0.10:.2f}、最大回撤不大於 {b['mdd']:.1%}。", "",
          f"- W1：{'✓' if p1 else '✗'}", f"- W2：{'✓' if p2 else '✗'}", "",
          f"**結論：{'通過（W1）' if p1 else ('通過（W2）' if p2 else '未通過')}**"]
    (ROOT / "docs" / "fv5_invvol.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
