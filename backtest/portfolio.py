"""報酬層級評估：連續報酬 Rank IC 與 long/neutral 組合模擬。

Brier / ECE 只衡量機率品質；這裡回答「照訊號操作能不能賺錢、有沒有打贏 0050」。

輸入為 run_walk_forward 的結果表，需含欄位：
- as_of_date / ticker
- forward_return：as_of_date 收盤到 horizon 期末收盤的含息總報酬
- benchmark_return：同一窗口 0050 的含息總報酬
- {strategy}_signal / {strategy}_p

組合規則（long/neutral，不放空）：
- 每個預測時點為一個持有期；訊號為 bullish 的股票等權持有，其餘不持有
- 沒有任何 bullish 時整期持有現金（報酬 0）
- 交易成本以權重變動量（turnover）計，單邊成本預設 0.29%
  （手續費 0.1425% × 2 + 證交稅 0.3%，平均到買賣兩邊）
- 持有期內權重漂移不計（每期期初重新等權）

統計檢定以常態近似計算雙尾 p 值（未依賴 scipy）；
樣本數小（每期 5 檔、約 27 期）時僅供參考。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

TRADING_DAYS_PER_YEAR = 252
DEFAULT_COST_PER_SIDE = (0.001425 * 2 + 0.003) / 2


def _normal_two_sided_p(z: float) -> float:
    if not math.isfinite(z):
        return float("nan")
    return math.erfc(abs(z) / math.sqrt(2.0))


def _t_stat(values: np.ndarray) -> float:
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return float("nan")
    sd = values.std(ddof=1)
    if sd == 0:
        return float("nan")
    return float(values.mean() / (sd / math.sqrt(len(values))))


# ---------------------------------------------------------------------------
# Rank IC（連續報酬）
# ---------------------------------------------------------------------------

def spearman(x: pd.Series, y: pd.Series) -> float:
    """Spearman 相關（平均名次處理同分）。任一邊無變異時回傳 nan。"""
    rx = x.rank(method="average")
    ry = y.rank(method="average")
    if rx.std() == 0 or ry.std() == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def rank_ic(df: pd.DataFrame, score_col: str, ret_col: str = "forward_return") -> dict:
    """看多機率 vs 實現報酬的 Rank IC。

    - pooled：全部事件混在一起算一次 Spearman（含跨期的市場漲跌）
    - cross-sectional：每個時點對 5 檔股票算一次 Spearman，再對時點取平均
      （選股能力的標準衡量；同時點機率全相同的期數會被略過）
    """
    data = df[[score_col, ret_col, "as_of_date"]].dropna()
    n = len(data)
    pooled = spearman(data[score_col], data[ret_col]) if n >= 3 else float("nan")
    # Spearman 的 t 近似：t = r·sqrt((n-2)/(1-r²))
    if n >= 3 and math.isfinite(pooled) and abs(pooled) < 1:
        pooled_t = pooled * math.sqrt((n - 2) / (1 - pooled**2))
    else:
        pooled_t = float("nan")

    per_date = []
    for _, g in data.groupby("as_of_date"):
        if len(g) >= 3:
            ic = spearman(g[score_col], g[ret_col])
            if math.isfinite(ic):
                per_date.append(ic)
    cs = np.asarray(per_date, dtype=float)
    cs_t = _t_stat(cs)
    return {
        "ic_pooled": pooled,
        "ic_pooled_p": _normal_two_sided_p(pooled_t),
        "n_pooled": n,
        "ic_cs_mean": float(cs.mean()) if len(cs) else float("nan"),
        "ic_cs_t": cs_t,
        "ic_cs_p": _normal_two_sided_p(cs_t),
        "n_cs_dates": len(cs),
    }


# ---------------------------------------------------------------------------
# Long/neutral 組合
# ---------------------------------------------------------------------------

def long_neutral_returns(
    df: pd.DataFrame,
    signal_col: str,
    ret_col: str = "forward_return",
    cost_per_side: float = DEFAULT_COST_PER_SIDE,
) -> pd.DataFrame:
    """每期等權持有 bullish 標的，回傳每期 [as_of_date, gross, turnover, net, n_long]。

    signal_col=None 時視為全部持有（等權股票池基準）。
    """
    rows = []
    prev_w: dict[str, float] = {}
    data = df.dropna(subset=[ret_col])
    for date, g in data.groupby("as_of_date", sort=True):
        held = g if signal_col is None else g[g[signal_col] == "bullish"]
        w = {t: 1.0 / len(held) for t in held["ticker"]} if len(held) else {}
        gross = float(held[ret_col].mean()) if len(held) else 0.0
        tickers = set(w) | set(prev_w)
        turnover = sum(abs(w.get(t, 0.0) - prev_w.get(t, 0.0)) for t in tickers)
        rows.append(
            {
                "as_of_date": date,
                "gross": gross,
                "turnover": turnover,
                "net": gross - turnover * cost_per_side,
                "n_long": len(held),
            }
        )
        prev_w = w
    return pd.DataFrame(rows)


def benchmark_returns(df: pd.DataFrame, col: str = "benchmark_return") -> pd.Series:
    """每期 0050 報酬（同一時點各列相同，取第一筆）。"""
    return df.dropna(subset=[col]).groupby("as_of_date", sort=True)[col].first()


def max_drawdown(period_returns: np.ndarray) -> float:
    equity = np.cumprod(1.0 + period_returns)
    peak = np.maximum.accumulate(np.concatenate([[1.0], equity]))[1:]
    return float((equity / peak - 1.0).min()) if len(equity) else float("nan")


def performance_stats(
    returns: pd.Series, benchmark: pd.Series, periods_per_year: float
) -> dict:
    """單一報酬序列對 0050 的績效摘要（報酬皆為每期簡單報酬）。"""
    aligned = pd.concat([returns.rename("r"), benchmark.rename("b")], axis=1).dropna()
    r = aligned["r"].to_numpy()
    b = aligned["b"].to_numpy()
    n = len(r)
    if n == 0:
        return {}
    total = float(np.prod(1.0 + r) - 1.0)
    years = n / periods_per_year
    ann_ret = float((1.0 + total) ** (1.0 / years) - 1.0) if total > -1 else -1.0
    ann_vol = float(r.std(ddof=1) * math.sqrt(periods_per_year)) if n > 1 else float("nan")
    excess = r - b
    te = float(excess.std(ddof=1) * math.sqrt(periods_per_year)) if n > 1 else float("nan")
    bench_total = float(np.prod(1.0 + b) - 1.0)
    excess_t = _t_stat(excess)
    return {
        "n_periods": n,
        "total_return": total,
        "ann_return": ann_ret,
        "ann_vol": ann_vol,
        "sharpe": ann_ret / ann_vol if ann_vol and math.isfinite(ann_vol) else float("nan"),
        "max_drawdown": max_drawdown(r),
        "bench_total_return": bench_total,
        "excess_total": total - bench_total,
        "excess_mean_per_period": float(excess.mean()),
        "tracking_error": te,
        "information_ratio": float(excess.mean() * periods_per_year / te) if te else float("nan"),
        "excess_t": excess_t,
        "excess_p": _normal_two_sided_p(excess_t),
        "excess_hit_rate": float((excess > 0).mean()),
    }


def equity_curve_plot(curves: dict[str, pd.Series], save_path: str, title: str) -> str:
    """各策略累積淨值曲線（每期簡單報酬 → 連乘）。"""
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for label, r in curves.items():
        equity = (1.0 + r).cumprod()
        x = pd.to_datetime(equity.index)
        ax.plot(x, equity.values, label=label, lw=1.6)
    ax.axhline(1.0, color="k", lw=0.8, ls="--")
    ax.set_ylabel("Growth of 1")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    return save_path


def evaluate_returns(
    df: pd.DataFrame,
    strategies: dict[str, str],
    step_days: int,
    cost_per_side: float = DEFAULT_COST_PER_SIDE,
    plot_path: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """回傳 (策略績效摘要表, 每期報酬表)。

    strategies：{strategy_key: 英文標籤}，用 {key}_signal 建組合、{key}_p 算 IC。
    另加兩個基準：等權持有全部股票池（equal_weight）與 0050。
    """
    periods_per_year = TRADING_DAYS_PER_YEAR / step_days
    bench = benchmark_returns(df)
    period_table = pd.DataFrame(index=bench.index)
    period_table["benchmark_0050"] = bench
    rows = []
    curves: dict[str, pd.Series] = {}

    def add(key: str, label: str, port: pd.DataFrame, ic: dict | None):
        gross = port.set_index("as_of_date")["gross"]
        net = port.set_index("as_of_date")["net"]
        period_table[f"{key}_net"] = net
        period_table[f"{key}_n_long"] = port.set_index("as_of_date")["n_long"]
        stats_net = performance_stats(net, bench, periods_per_year)
        stats_gross = performance_stats(gross, bench, periods_per_year)
        rows.append(
            {
                "strategy": key,
                **stats_net,
                "ann_return_gross": stats_gross.get("ann_return", float("nan")),
                "avg_turnover": float(port["turnover"].mean()),
                "avg_exposure": float((port["n_long"] > 0).mean()),
                "avg_n_long": float(port["n_long"].mean()),
                **(ic or {}),
            }
        )
        curves[label] = net

    for key, label in strategies.items():
        port = long_neutral_returns(df, f"{key}_signal", cost_per_side=cost_per_side)
        add(key, label, port, rank_ic(df, f"{key}_p"))

    ew = long_neutral_returns(df, None, cost_per_side=cost_per_side)
    add("equal_weight", "Equal-weight universe", ew, None)
    rows.append({"strategy": "benchmark_0050", **performance_stats(bench, bench, periods_per_year),
                 "avg_exposure": 1.0})
    curves["0050 (benchmark)"] = bench

    if plot_path:
        equity_curve_plot(curves, plot_path, "Long/neutral portfolios vs 0050 (net of costs)")
    return pd.DataFrame(rows), period_table.reset_index()
