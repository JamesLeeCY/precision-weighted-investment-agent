"""I053 fv5 家族前瞻輔助判定：機制指標與非劣性檢定的檢定力校準（點子卡 research/ideas/I053-fv5-family-mechanism-endpoints-power.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/fv5_mechanism_power.py
輸出 docs/fv5_mechanism_power.md。本程式只用回測校準檢定力，不計算任何 live 機制指標。

設計（依點子卡；補充以「補」標示）：
- 回測：analysis/fv5_family.run_backtests（fv5、fv5e、fv5s、fv5v、fv5x 日淨報酬，2019-03 ~ 2026-04）。
- D0 等價性：fv5x − fv5 的每段（相鄰換倉日之間）報酬差 t（Newey-West 落後 1）與日頻報酬差 t（Newey-West 落後 20）比較；|t_日 ÷ t_段 − 1| < 10% 為等價。
- M_s：每個換倉日，前 500 名 60 日報酬的產業內百分位 ~ SUE 百分位 + S1 百分位（橫斷面百分位 − 0.5）的 S1 係數；月度序列。
- M_v：日頻淨報酬變異數比 ρ = Var(規格) ÷ Var(fv5)（fv5v、fv5x），檢定 ln ρ < 0；以區塊長度 20 日的成對區塊 bootstrap（5,000 次）估計 n 個月時 ln ρ 的標準誤。
- M_e（只報告）：金融股內，已知 ESUE 的股票之 ESUE 與 SUE 對 60 日報酬的 Spearman IC 差。
- N_k：波動調整後每段報酬差 d_k = c_k × 規格段報酬 − fv5 段報酬（c_k 取 forward/family_scale.yaml），非劣性 = 90% 單尾信賴下界 > −0.05%／段。
- 檢定力（常態近似；補：Holm 家族單尾 10%、兩個機制指標，以最寬鬆的第二步 10% 與最嚴的第一步 5% 之間取第一步 5%，即單尾臨界值 1.645）：
  M_s：1 − Φ(1.645 − f × μ/σ × √n)；M_v：Φ(f × |ln ρ| ÷ se_n − 1.645)；N_k：Φ((f × μ_d + 0.0005) ÷ (σ_d/√n) − 1.2816)；
  f = 1（回測效果）與 0.5（保守），n = 6、12、24、36 個月（每段約一個月）。
- 通過（本卡）：D0 等價，且至少一個機制指標在 24 個月、f = 0.5 時檢定力 ≥ 50% → 建議使用者登錄輔助規則。
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
import leg_probe as lp  # noqa: E402
from sue_attention import nw_t  # noqa: E402

NS = (6, 12, 24, 36)
Z = 1.645


def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def block_se(a: np.ndarray, b: np.ndarray, n_days: int, reps: int = 5000, block: int = 20, seed: int = 0) -> float:
    """成對區塊 bootstrap：長度 n_days 的樣本中 ln(Var(a)/Var(b)) 的標準誤。"""
    rng = np.random.default_rng(seed)
    T = len(a)
    nb = int(math.ceil(n_days / block))
    out = np.empty(reps)
    for r in range(reps):
        st = rng.integers(0, T - block, nb)
        idx = (st[:, None] + np.arange(block)[None, :]).ravel()[:n_days]
        out[r] = math.log(a[idx].var() / b[idx].var())
    return float(out.std(ddof=1))


def main():
    R, sched = ff.run_backtests()
    ctx = ff.LAST
    c, sue, s1, e, fin = ctx["c"], ctx["sue"], ctx["s1"], ctx["e"], ctx["fin"]
    days = c.adj.index
    keys = {"fv5": "fv5", "fv5e": "fv5e", "fv5s": "fv5s", "fv5v": "fv5v", "fv5x": "fv5x（E+S+V）"}
    D = pd.DataFrame({k: R[v] for k, v in keys.items()}).dropna()
    seg_id = pd.Series(np.searchsorted(np.array(sched), D.index, side="right"), index=D.index)
    S = (1 + D).groupby(seg_id).prod() - 1
    # D0
    t_seg = nw_t(S["fv5x"] - S["fv5"], 1)
    t_day = nw_t(D["fv5x"] - D["fv5"], 20)
    d0 = abs(t_day / t_seg - 1) < 0.10 if t_seg == t_seg and t_seg != 0 else False
    # M_s
    fwd60 = c.adj.shift(-60) / c.adj - 1
    limit = int(days.searchsorted(lp.HOLDOUT))
    ms = {}
    for d in sched:
        if int(days.searchsorted(d)) + 60 >= limit:
            continue
        df = pd.DataFrame({"y": fwd60.loc[d], "sue": sue[d], "s1": s1[d]}).dropna()
        df = df[c.member.loc[d].reindex(df.index).fillna(False).to_numpy(bool)]
        if len(df) < 50:
            continue
        df["y"] = df["y"].groupby(c.sector.reindex(df.index)).rank(pct=True) - 0.5
        X = np.column_stack([np.ones(len(df)), df["sue"].rank(pct=True) - 0.5, df["s1"].rank(pct=True) - 0.5])
        b, *_ = np.linalg.lstsq(X, df["y"].to_numpy(), rcond=None)
        ms[d] = b[2]
    ms = pd.Series(ms)
    ms_mu, ms_sd, ms_t = float(ms.mean()), float(ms.std(ddof=1)), nw_t(ms, 2)
    # M_e（只報告）
    me = {}
    for d in sched:
        kd = int(days.searchsorted(d))
        if kd + 60 >= limit:
            continue
        g = e[(e["k0"] + 1 <= kd) & (kd - e["k0"] <= ff.LOOKBACK) & e["ticker"].isin(fin)].sort_values("k0").drop_duplicates("ticker", keep="last")
        g = g[[bool(c.member.at[d, t]) for t in g["ticker"]]]
        if len(g) < 8:
            continue
        f = fwd60.loc[d].reindex(g["ticker"]).to_numpy()
        sv = sue[d].reindex(g["ticker"]).to_numpy()
        a = pd.Series(g["esue"].to_numpy()).rank().corr(pd.Series(f).rank())
        b2 = pd.Series(sv).rank().corr(pd.Series(f).rank())
        if a == a and b2 == b2:
            me[d] = a - b2
    me = pd.Series(me)
    # M_v 與 N_k
    scale = yaml.safe_load((ROOT / "forward" / "family_scale.yaml").read_text(encoding="utf-8"))["scale"]
    mv = {}
    for k in ("fv5v", "fv5x"):
        lr = math.log(D[k].var() / D["fv5"].var())
        se = {n: block_se(D[k].to_numpy(), D["fv5"].to_numpy(), n * 21) for n in NS}
        mv[k] = (lr, se)
    nk = {}
    for k in ("fv5e", "fv5s", "fv5v", "fv5x"):
        d = float(scale[k]) * S[k] - S["fv5"]
        nk[k] = (float(d.mean()), float(d.std(ddof=1)))
    pw = lambda x: f"{x:.0%}"  # noqa: E731
    L = ["# I053 fv5 家族前瞻輔助判定：檢定力校準（自動產生）", "",
         "由 [analysis/fv5_mechanism_power.py](../analysis/fv5_mechanism_power.py) 產生；設計見程式開頭（看結果前固定）。只用回測（2019-03 ~ 2026-04）校準，未計算任何 live 指標。"
         "檢定力 = 在 n 個月的 live 資料下單尾檢定成立的機率（常態近似）；f = 1 用回測效果、f = 0.5 假設 live 效果只有回測的一半。研究結果，非投資建議。", "",
         "## D0：提高頻率是否提高檢定力（fv5x − fv5）", "",
         f"- 每段（約一個月）報酬差 t（Newey-West 落後 1）：{t_seg:.2f}；日頻報酬差 t（Newey-West 落後 20）：{t_day:.2f}；"
         f"相對差 {t_day / t_seg - 1:+.0%} → {'等價（提高頻率無助於平均差的檢定）' if d0 else '不等價，需查原因'}", "",
         "## 機制指標", "",
         f"- M_s（S1 在控制 SUE 後對 60 日報酬百分位的係數，月度）：平均 {ms_mu:+.4f}、標準差 {ms_sd:.4f}、回測 t {ms_t:.2f}（{len(ms)} 個月）",
         f"- M_v（日報酬變異數比）：fv5v ρ = {math.exp(mv['fv5v'][0]):.2f}、fv5x ρ = {math.exp(mv['fv5x'][0]):.2f}",
         f"- 只報告 M_e（金融股 ESUE − SUE 的 60 日 IC 差）：平均 {me.mean():+.3f}（t {nw_t(me, 2):.2f}，{len(me)} 個月）", "",
         "| 指標 | 效果 | " + " | ".join(f"{n} 個月" for n in NS) + " |", "|---|---|" + "---|" * len(NS)]
    best24 = {}
    for f in (1.0, 0.5):
        es = ms_mu / ms_sd
        row = [1 - phi(Z - f * es * math.sqrt(n)) for n in NS]
        L.append(f"| M_s（fv5s、fv5x） | f = {f:g} | " + " | ".join(pw(x) for x in row) + " |")
        if f == 0.5:
            best24["M_s"] = row[NS.index(24)]
        for k in ("fv5v", "fv5x"):
            lr, se = mv[k]
            row = [phi(f * abs(lr) / se[n] - Z) if lr < 0 else 0.0 for n in NS]
            L.append(f"| M_v（{k}） | f = {f:g} | " + " | ".join(pw(x) for x in row) + " |")
            if f == 0.5:
                best24[f"M_v {k}"] = row[NS.index(24)]
    L += ["", "## 非劣性 N_k（波動調整後每段報酬差的 90% 下界 > −0.05%／段）", "",
          "| 規格 | 回測每段 d 平均 | 標準差 | 效果 | " + " | ".join(f"{n} 個月" for n in NS) + " |", "|---|---|---|---|" + "---|" * len(NS)]
    for k, (mu, sd) in nk.items():
        for f in (1.0, 0.5):
            row = [phi((f * mu + 0.0005) / (sd / math.sqrt(n)) - 1.2816) for n in NS]
            L.append(f"| {k} | {mu:+.3%} | {sd:.3%} | f = {f:g} | " + " | ".join(pw(x) for x in row) + " |")
    ok = d0 and any(v >= 0.5 for v in best24.values())
    L += ["", "## 判定", "",
          f"- D0 等價性：{'✓' if d0 else '✗'}",
          "- 24 個月、f = 0.5 時機制指標檢定力：" + "、".join(f"{k} {pw(v)}" for k, v in best24.items()) + f" → {'至少一項 ≥ 50% ✓' if any(v >= 0.5 for v in best24.values()) else '皆 < 50% ✗'}", "",
          f"**結論：{'建議登錄輔助判定規則（需使用者在看到任何 live 機制指標前決定）' if ok else '不建議登錄輔助規則；只保留 D0 結論'}**"]
    (ROOT / "docs" / "fv5_mechanism_power.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
