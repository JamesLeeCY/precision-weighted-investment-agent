"""fv5 家族前瞻比較改用「波動調整後的報酬差」：固定縮放係數與檢定力（使用者 2026-10-22 決定，取代 I051 的每段報酬差）。

用法（於專案根目錄；資料皆已快取，重跑 fv5_family 的回測）：
    .venv/Scripts/python analysis/fv5_family_voladj.py
輸出 docs/fv5_family_voladj.md 與 forward/family_scale.yaml（凍結的縮放係數，供 forward/compare_family.py 使用）。

定義（看前瞻結果前固定）：
- 縮放係數 c_k = fv5 回測日報酬年化波動 ÷ 規格 k 回測日報酬年化波動（2019-03 ~ 2026-04，同 analysis/fv5_family.py 的回測），凍結後不再更新。
- 每段波動調整後的報酬差 d_k = c_k × r_k − r_fv5（r 為同一段的組合淨報酬）。等同把規格 k 的槓桿調到與 fv5 相同波動後比較，
  所以 d_k 的平均 > 0 ⇔ 規格 k 的 Sharpe 較高（在兩者相關、波動穩定的近似下）。
- 檢定力：回測每段 d_k 的平均 μ 與標準差 σ，單尾 t > 2 的檢定力 ≈ 1 − Φ(2 − μ/σ × √n)。
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


def main():
    captured, c_sched = ff.run_backtests()
    R = {k: v for k, v in captured.items() if k in ("fv5", "fv5e", "fv5s", "fv5v", "fv5x（E+S+V）")}
    vol = {k: float(v.std() * math.sqrt(252)) for k, v in R.items()}
    scale = {k.split("（")[0]: vol["fv5"] / vol[k] for k in R if k != "fv5"}
    idx = R["fv5"].index
    seg_id = pd.Series(np.searchsorted(np.array(c_sched), idx, side="right"), index=idx)
    seg = {k: (1 + v).groupby(seg_id.reindex(v.index)).prod() - 1 for k, v in R.items()}
    rows = []
    for k in R:
        if k == "fv5":
            continue
        name = k.split("（")[0]
        d = (scale[name] * seg[k] - seg["fv5"]).dropna()
        raw = (seg[k] - seg["fv5"]).dropna()
        mu, sd = float(d.mean()), float(d.std(ddof=1))
        es = mu / sd if sd > 0 else float("nan")
        pw = {n: 1 - 0.5 * (1 + math.erf((2 - es * math.sqrt(n)) / math.sqrt(2))) for n in (24, 48, 72)}
        need = lambda z: (math.ceil(((2 + z) / es) ** 2) if es > 0 else None)  # noqa: E731
        rows.append((name, vol[k], scale[name], float(raw.mean()), mu, sd, pw, need(0.8416), need(0.0)))
    out = {"defined": "2026-10-22", "source": "analysis/fv5_family_voladj.py（回測 2019-03 ~ 2026-04 日報酬年化波動比）",
           "fv5_vol": round(vol["fv5"], 6), "scale": {k: round(v, 6) for k, v in scale.items()},
           "power_50_periods": {r[0]: r[8] for r in rows}}
    (ROOT / "forward" / "family_scale.yaml").write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False), encoding="utf-8")
    L = ["# fv5 家族：波動調整後的報酬差與檢定力（自動產生）", "",
         "由 [analysis/fv5_family_voladj.py](../analysis/fv5_family_voladj.py) 產生。d = c × 規格段報酬 − fv5 段報酬，c = fv5 年化波動 ÷ 規格年化波動（回測固定）；"
         "每段 = 相鄰兩個預測日之間（約一個月）；檢定力為單尾 t > 2 的常態近似。研究結果，非投資建議。", "",
         f"fv5 回測年化波動 {vol['fv5']:.2%}。", "",
         "| 規格 | 年化波動 | 縮放係數 c | 原始每段報酬差 | 波動調整後每段差 | 標準差 | 24 期檢定力 | 48 期 | 72 期 | 80% 所需期數 | 50% 所需期數 |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, v, c, raw, mu, sd, pw, n80, n50 in rows:
        L.append(f"| {name} | {v:.2%} | {c:.3f} | {raw:+.3%} | {mu:+.3%} | {sd:.3%} | {pw[24]:.0%} | {pw[48]:.0%} | {pw[72]:.0%} | "
                 f"{n80 if n80 else '—'} | {n50 if n50 else '—'} |")
    (ROOT / "docs" / "fv5_family_voladj.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
