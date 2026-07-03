"""評估指標（規格第 6 節，強制定義）。

- signal_to_probability：規格 6.1 的機率轉換
  bullish → p = confidence；bearish → p = 1 - confidence；neutral → p = 0.5
- brier_score = (p - o)^2
- 校準曲線（Reliability Diagram）：confidence 分 10 桶，
  每桶平均 confidence vs 實際命中率（規格 6.2，核心視覺化產出）
- ECE（Expected Calibration Error）：各桶 |平均p - 命中率| 的加權平均
- 方向準確率：非 neutral 預測中，signal 方向與實際報酬方向一致的比例
"""
from __future__ import annotations

import numpy as np

import matplotlib

matplotlib.use("Agg")  # 無視窗環境亦可產圖
import matplotlib.pyplot as plt


def signal_to_probability(signal: str, confidence: float) -> float:
    """將 (signal, confidence) 轉為「看多機率」p（規格 6.1）。"""
    if signal == "bullish":
        return float(confidence)
    if signal == "bearish":
        return 1.0 - float(confidence)
    if signal == "neutral":
        return 0.5
    raise ValueError(f"未知 signal: {signal!r}")


def brier_score(p: float, outcome: int) -> float:
    """單次預測 Brier score = (p - o)^2，o ∈ {0, 1}（規格 6.1）。"""
    if outcome not in (0, 1):
        raise ValueError(f"outcome 必須是 0 或 1，收到 {outcome}")
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"p 必須在 [0,1]，收到 {p}")
    return (p - outcome) ** 2


def mean_brier(ps: list[float], outcomes: list[int]) -> float:
    return float(np.mean([brier_score(p, o) for p, o in zip(ps, outcomes, strict=True)]))


def directional_accuracy(signals: list[str], outcomes: list[int]) -> tuple[float, int]:
    """方向準確率（規格 6.3）。

    只計非 neutral 的預測：bullish 且 o=1、或 bearish 且 o=0 視為命中。
    回傳 (準確率, 納入計算的預測數)；無非中性預測時準確率回傳 nan。
    """
    hits = 0
    n = 0
    for s, o in zip(signals, outcomes, strict=True):
        if s == "neutral":
            continue
        n += 1
        if (s == "bullish" and o == 1) or (s == "bearish" and o == 0):
            hits += 1
    return (hits / n if n else float("nan")), n


def calibration_bins(ps: list[float], outcomes: list[int], n_bins: int = 10):
    """回傳每桶的 (平均p, 命中率, 樣本數)。空桶不納入。"""
    ps_arr = np.asarray(ps, dtype=float)
    os_arr = np.asarray(outcomes, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (ps_arr >= lo) & (ps_arr < hi) if i < n_bins - 1 else (ps_arr >= lo) & (ps_arr <= hi)
        if mask.sum() == 0:
            continue
        rows.append((float(ps_arr[mask].mean()), float(os_arr[mask].mean()), int(mask.sum())))
    return rows


def ece(ps: list[float], outcomes: list[int], n_bins: int = 10) -> float:
    """Expected Calibration Error（規格 6.3）。"""
    total = len(ps)
    if total == 0:
        return float("nan")
    return float(
        sum(n * abs(avg_p - hit_rate) for avg_p, hit_rate, n in calibration_bins(ps, outcomes, n_bins))
        / total
    )


def reliability_diagram(
    ps: list[float],
    outcomes: list[int],
    save_path: str,
    title: str = "Reliability Diagram",
    n_bins: int = 10,
) -> str:
    """畫校準曲線並存檔（規格 6.2：系統驗收的核心視覺化產出）。"""
    bins = calibration_bins(ps, outcomes, n_bins)

    fig, (ax, ax_hist) = plt.subplots(
        2, 1, figsize=(6, 7), gridspec_kw={"height_ratios": [3, 1]}, sharex=True
    )
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="Perfect calibration")
    if bins:
        xs = [b[0] for b in bins]
        ys = [b[1] for b in bins]
        ns = [b[2] for b in bins]
        ax.plot(xs, ys, "o-", color="#1f77b4", label="Model")
        for x, y, n in zip(xs, ys, ns):
            ax.annotate(str(n), (x, y), textcoords="offset points", xytext=(4, 4), fontsize=8)
    ax.set_ylabel("Observed hit rate")
    ax.set_title(f"{title}\n(n={len(ps)}, ECE={ece(ps, outcomes, n_bins):.4f})")
    ax.legend(loc="upper left")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.3)

    ax_hist.hist(ps, bins=np.linspace(0, 1, n_bins + 1), color="#1f77b4", alpha=0.6)
    ax_hist.set_xlabel("Predicted probability (bullish)")
    ax_hist.set_ylabel("Count")
    ax_hist.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    return save_path
