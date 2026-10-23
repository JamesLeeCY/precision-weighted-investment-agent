"""I057 第 501–1000 名的 fv5 家族影子前瞻：回測校準（點子卡 research/ideas/I057-fv5-family-shadow-universe-forward.md，檢定計畫看結果前固定）。

用法（於專案根目錄；第 501–1000 名資料大多已快取）：
    .venv/Scripts/python analysis/fv5_shadow_universe.py
輸出 docs/fv5_shadow_universe.md。本程式只做回測校準，不建立影子前瞻。

設計（依點子卡；補充以「補」標示）：
- 主規格：前 500 名 fv5、fv5e、fv5s、fv5v、fv5x（analysis/fv5_family.run_backtests）。
- 影子規格：第 501–1000 名（名次重編為 1–500 後用同一程式），不限制可借、借券費一律 2%／年、交易成本單邊另加 0.46%（I042 估計）；
  修改規則相同（E、S、V；V 放空端不重查借券）。
- 每段 = 相鄰換倉日之間；d_k = c_k × 規格段報酬 − 基準段報酬；主規格的 c_k 取 forward/family_scale.yaml，影子的 c_k 用影子回測波動比（補，同樣固定）。
- 合併估計：兩池 d_k 平均的最小變異加權（考慮相關係數 r_k）；檢定力 = 1 − Φ(2 − 合併平均 ÷ 合併每段標準差 × √n)，效果 100% 與 50%。
- 前提（逐規格）：(1) 影子 d_k 平均與主規格同號；(2) 合併後 50% 檢定力所需段數比只用主規格少 ≥ 30%；(3) r_k < 0.5。
  fv5e 的影子若有 ESUE 的金融股平均 < 10 檔，只報告不判定。
研究結果，非投資建議。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import fv5_family as ff  # noqa: E402

SHADOW_MEM = ROOT / "data_cache" / "events" / "membership_rank_501_1000_as_1_500.csv"
EXTRA = 0.0046
KEYS = {"fv5": "fv5", "fv5e": "fv5e", "fv5s": "fv5s", "fv5v": "fv5v", "fv5x": "fv5x（E+S+V）"}


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def segs(R, sched):
    D = pd.DataFrame({k: R[v] for k, v in KEYS.items()}).dropna()
    sid = pd.Series(np.searchsorted(np.array(sched), D.index, side="right"), index=D.index)
    S = (1 + D).groupby(sid).prod() - 1
    return D, S


def n50(es):
    return math.ceil((2 / es) ** 2) if es > 0 else None


def main():
    m = pd.read_csv(ROOT / "config" / "universe_mcap_membership.csv", dtype={"stock_id": str})
    m = m[(m["rank"] >= 501) & (m["rank"] <= 1000)].copy()
    m["rank"] = m["rank"] - 500
    m.to_csv(SHADOW_MEM, index=False, encoding="utf-8")
    R1, sched1 = ff.run_backtests()
    n_fin_main = ff.LAST["fin"]
    R2, sched2 = ff.run_backtests(str(SHADOW_MEM), shadow=True, extra_cost=EXTRA)
    e2, fin2, c2 = ff.LAST["e"], ff.LAST["fin"], ff.LAST["c"]
    days2 = c2.adj.index
    fin_cnt = []
    for d in sched2:
        kd = int(days2.searchsorted(d))
        g = e2[(e2["k0"] + 1 <= kd) & (kd - e2["k0"] <= ff.LOOKBACK) & e2["ticker"].isin(fin2)].drop_duplicates("ticker")
        fin_cnt.append(int(sum(bool(c2.member.at[d, t]) for t in g["ticker"])))
    D1, S1 = segs(R1, sched1)
    D2, S2 = segs(R2, sched2)
    vol1 = {k: float(D1[k].std() * math.sqrt(252)) for k in KEYS}
    vol2 = {k: float(D2[k].std() * math.sqrt(252)) for k in KEYS}
    scale1 = yaml.safe_load((ROOT / "forward" / "family_scale.yaml").read_text(encoding="utf-8"))["scale"]
    rows = []
    for k in ("fv5e", "fv5s", "fv5v", "fv5x"):
        d1 = float(scale1[k]) * S1[k] - S1["fv5"]
        c2k = vol2["fv5"] / vol2[k]
        d2 = c2k * S2[k] - S2["fv5"]
        j = pd.concat([d1.rename("a"), d2.rename("b")], axis=1).dropna()
        r = float(j["a"].corr(j["b"]))
        mu = np.array([j["a"].mean(), j["b"].mean()])
        sd = np.array([j["a"].std(ddof=1), j["b"].std(ddof=1)])
        cov = np.array([[sd[0] ** 2, r * sd[0] * sd[1]], [r * sd[0] * sd[1], sd[1] ** 2]])
        inv = np.linalg.pinv(cov)
        one = np.ones(2)
        w = inv @ one / (one @ inv @ one)
        var_c = 1 / (one @ inv @ one)
        out = {"k": k, "c2": c2k, "r": r, "mu1": mu[0], "mu2": mu[1], "sd1": sd[0], "sd2": sd[1], "w": w}
        for f in (1.0, 0.5):
            mc = f * float(w @ mu)
            es_c = mc / math.sqrt(var_c)
            es_1 = f * mu[0] / sd[0]
            out[f] = {"n1": n50(es_1), "nc": n50(es_c), "pw": {n: 1 - phi(2 - es_c * math.sqrt(n)) for n in (24, 48, 72)},
                      "pw1": {n: 1 - phi(2 - es_1 * math.sqrt(n)) for n in (24, 48, 72)}}
        n1, nc = out[1.0]["n1"], out[1.0]["nc"]
        c_sign = np.sign(mu[0]) == np.sign(mu[1]) and mu[0] != 0
        c_gain = n1 is not None and nc is not None and nc <= 0.7 * n1
        c_corr = r < 0.5
        report_only = k == "fv5e" and np.mean(fin_cnt) < 10
        out["ok"] = None if report_only else (c_sign and c_gain and c_corr)
        out["checks"] = (c_sign, c_gain, c_corr)
        rows.append(out)
    stat = lambda D: {k: (float(D[k].mean() * 252), float(D[k].std() * math.sqrt(252))) for k in KEYS}  # noqa: E731
    import leg_probe as lp
    L = ["# I057 第 501–1000 名影子前瞻：回測校準（自動產生）", "",
         "由 [analysis/fv5_shadow_universe.py](../analysis/fv5_shadow_universe.py) 產生；設計見程式開頭（看結果前固定）。"
         "影子規格不限制可借、借券費 2%／年、交易成本單邊另加 0.46%，只當統計證據、不能交易。每段約一個月；d = 縮放係數 × 規格段報酬 − 基準段報酬。研究結果，非投資建議。", "",
         "## 影子回測（第 501–1000 名）", "", "| 規格 | 全期 Sharpe | 2019–2022 / 2023–2026/04 | 年化報酬 | 年化波動 |", "|---|---|---|---|---|"]
    for k, v in KEYS.items():
        x = R2[v].dropna()
        L.append(f"| {k}-sh | {lp.sharpe(x):.2f} | {lp.sharpe(x[x.index < lp.SPLIT]):.2f} / {lp.sharpe(x[x.index >= lp.SPLIT]):.2f} | "
                 f"{x.mean() * 252:+.1%} | {x.std() * math.sqrt(252):.1%} |")
    L += ["", f"影子 fv5e：每個換倉日有 ESUE 的金融股平均 {np.mean(fin_cnt):.1f} 檔（< 10 檔只報告）。", "",
          "## 合併檢定力", "",
          "| 規格 | 影子縮放係數 | 主規格每段 d | 影子每段 d | 相關 r | 合併權重（主／影子） | 50% 檢定力所需段數：只用主規格 → 合併（效果 100%） | 同上（效果 50%） | 合併 24 / 48 / 72 段檢定力（效果 100%） | 前提（同號／少 30%／r < 0.5） |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for o in rows:
        a, b = o[1.0], o[0.5]
        L.append(f"| {o['k']} | {o['c2']:.3f} | {o['mu1']:+.3%} | {o['mu2']:+.3%} | {o['r']:+.2f} | {o['w'][0]:.2f} / {o['w'][1]:.2f} | "
                 f"{a['n1'] or '—'} → {a['nc'] or '—'} | {b['n1'] or '—'} → {b['nc'] or '—'} | "
                 + " / ".join(f"{a['pw'][n]:.0%}" for n in (24, 48, 72)) + " | "
                 + "／".join("✓" if x else "✗" for x in o["checks"]) + ("（只報告）" if o["ok"] is None else "") + " |")
    passed = [o["k"] for o in rows if o["ok"]]
    L += ["", f"**結論：{'前提成立的規格：' + '、'.join(passed) + '，建議另立影子前瞻（每月約 1,500–2,000 次 FinMind，需使用者決定）' if passed else '前提都不成立，不建立影子前瞻，只保留校準表'}**"]
    (ROOT / "docs" / "fv5_shadow_universe.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
