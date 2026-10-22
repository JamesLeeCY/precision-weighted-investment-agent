"""fv5 家族前瞻比較：波動調整後的報酬差（使用者 2026-10-22 決定，取代 fv5e、fv5s、fv5v、fv5x 原本登錄的每段報酬差比較）。

用法（於專案根目錄；只讀各規格的 periods.csv，不呼叫 FinMind）：
    .venv/Scripts/python forward/compare_family.py
輸出 forward/FAMILY_REPORT.md。每日由 forward/run_forward.py auto 在 fv5x 之後呼叫 auto()。

規則（事前固定，縮放係數凍結於 forward/family_scale.yaml，來源 analysis/fv5_family_voladj.py）：
- 每段 d_k = c_k × 規格 k 的組合淨報酬 − fv5 的組合淨報酬；c_k = fv5 回測年化波動 ÷ 規格 k 回測年化波動（固定，不用前瞻資料估計）。
- 只用 mode = live 的段；backfill 另列、只作描述。
- n < 24：累積中。
- 24 ≤ n < N50_k（回測估計達 50% 檢定力所需期數，fv5e 105、fv5s 131、fv5v 302、fv5x 76）：只做警訊檢查——
  d_k 平均 < 0 且 Newey-West（落後 1）t < −1 → 停止記錄該規格。
- n ≥ N50_k：正式判定。對已進入正式判定的規格計算 d_k 的單尾 t，Holm 校正、家族顯著水準 10%；
  通過校正、且規格本身每段淨報酬的 t > 2 者才可取代 fv5；多個通過時選 d_k 平均最大者。
研究記錄，非投資建議。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "forward" / "FAMILY_REPORT.md"
SCALE = ROOT / "forward" / "family_scale.yaml"
SPECS = ("fv5e", "fv5s", "fv5v", "fv5x")
PUBLISH_FILES = ["forward/FAMILY_REPORT.md"]
ALPHA = 0.10


def nw_t(x: pd.Series, lag: int = 1) -> float:
    x = x.dropna()
    n = len(x)
    if n < 3:
        return float("nan")
    e = x - x.mean()
    var = (e ** 2).sum() / n
    for k in range(1, lag + 1):
        var += 2 * (1 - k / (lag + 1)) * (e.iloc[k:].to_numpy() * e.iloc[:-k].to_numpy()).sum() / n
    return float(x.mean() / math.sqrt(var / n)) if var > 0 else float("nan")


def p_one_sided(t: float) -> float:
    return 1 - 0.5 * (1 + math.erf(t / math.sqrt(2))) if t == t else float("nan")


def build() -> str:
    cfg = yaml.safe_load(SCALE.read_text(encoding="utf-8"))
    rows, formal = [], {}
    for k in SPECS:
        p = ROOT / "forward" / k / "periods.csv"
        per = pd.read_csv(p) if p.exists() and p.stat().st_size > 0 else pd.DataFrame(columns=["mode", "book_net", "fv5_net"])
        c, n50 = float(cfg["scale"][k]), int(cfg["power_50_periods"][k])
        out = {"spec": k, "c": c, "n50": n50}
        for mode in ("live", "backfill"):
            sub = per[per["mode"] == mode]
            d = c * sub["book_net"].astype(float) - sub["fv5_net"].astype(float)
            out[mode] = (len(d), float(d.mean()) if len(d) else float("nan"), nw_t(d), nw_t(sub["book_net"].astype(float)))
        n, mu, t, t_own = out["live"]
        if n < 24:
            status = "累積中"
        elif n < n50:
            status = "警訊：停止記錄" if (mu < 0 and t < -1) else "警訊檢查通過（未到正式判定期數）"
        else:
            status = "正式判定"
            formal[k] = (t, t_own, mu)
        out["status"] = status
        rows.append(out)
    # Holm
    decision = {}
    if formal:
        ps = sorted(((p_one_sided(v[0]), k) for k, v in formal.items()), key=lambda x: x[0])
        m = len(ps)
        passed = True
        for i, (pv, k) in enumerate(ps):
            ok = passed and pv <= ALPHA / (m - i)
            passed = ok
            decision[k] = ok and formal[k][1] > 2
    winners = [k for k, ok in decision.items() if ok]
    best = max(winners, key=lambda k: formal[k][2]) if winners else None
    fmt = lambda v: "—" if v[0] == 0 else f"{v[1]:+.2%}（t {v[2]:.2f}，{v[0]} 段）"  # noqa: E731
    L = ["# fv5 家族前瞻比較（波動調整後的報酬差，自動產生）", "",
         "由 [forward/compare_family.py](compare_family.py) 產生；規則見程式開頭（2026-10-22 使用者決定，事前固定）。研究記錄，非投資建議。", "",
         "每段 d = c × 規格段淨報酬 − fv5 段淨報酬；c = fv5 回測年化波動 ÷ 規格回測年化波動（固定），等同把規格調到與 fv5 相同波動後比較。"
         "正式判定期數 = 回測估計達 50% 檢定力所需的 live 段數。", "",
         "| 規格 | 縮放係數 c | 正式判定期數 | live：平均 d（t，段數） | backfill：平均 d（只作描述） | 狀態 |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['spec']} | {r['c']:.3f} | {r['n50']} | {fmt(r['live'])} | {fmt(r['backfill'])} | {r['status']} |")
    L += ["", "## 判定", ""]
    if not formal:
        L.append("尚無規格進入正式判定；fv5 維持為主規格。")
    else:
        for k, ok in decision.items():
            L.append(f"- {k}：Holm 校正（家族 10%）{'通過' if ok else '未通過'}，規格本身 t {formal[k][1]:.2f}")
        L.append(f"\n**{'以 ' + best + ' 取代 fv5' if best else 'fv5 維持為主規格'}**")
    return "\n".join(L) + "\n"


def auto() -> bool:
    if not SCALE.exists():
        return False
    text = build()
    old = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    if text != old:
        REPORT.write_text(text, encoding="utf-8")
        return True
    return False


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    auto()
    print(REPORT.read_text(encoding="utf-8"))
