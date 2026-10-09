"""回測主流程（規格 5.3 / 6.3）。

Walk-forward 流程（嚴格按時間順序，避免 look-ahead）：
1. 依時間排序所有 (ticker, as_of_date) 預測事件
2. 在對每個事件產生合併判斷「之前」，先結算所有 horizon 已到期
   （resolution_date <= 當前 as_of_date）的舊預測：以規格 6.1 的
   Brier score 更新各 Agent 的精度記錄（EMA alpha=0.2）
3. 以「當下」的精度快照做精度加權合併 → 本系統策略
4. 同一事件同時計算兩個 baseline（規格 6.3）：
   - Baseline A：單一 Agent（財報 Agent）
   - Baseline B：簡單平均（所有 Agent 精度設為相同值）
5. 全部跑完後產出比較報表（Brier / 方向準確率 / ECE）與校準曲線
6. finmind 模式另做報酬層級評估（backtest/portfolio.py）：連續報酬 Rank IC、
   long/neutral 組合淨值與相對 0050 的超額報酬

機率定義（供系統層級 Brier）：
- Baseline A（單一 Agent）：規格 6.1 之轉換（bullish→conf、bearish→1-conf、neutral→0.5）
- Baseline B / 本系統（合併輸出）：各 Agent 規格 6.1 機率的加權線性意見池
  （權重與規格 5.2 合併公式相同，見 arbitrator/merge.py）

執行模式：
- --mode synthetic：模擬「可靠度不同」的兩個 Agent 與已知結果，
  端到端驗證管線與精度加權機制（不需任何 API key）
- --mode finmind：以 FinMind 真實資料驅動財報 Agent 與新聞 Agent
  （需要 FINMIND_API_TOKEN）
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.base import AgentOutput
from arbitrator.calibration import AgentCalibrator
from arbitrator.ic_weighting import ICWeighter
from arbitrator.merge import merge
from arbitrator.precision_tracker import PrecisionTracker
from backtest.metrics import (
    directional_accuracy,
    ece,
    mean_brier,
    reliability_diagram,
    signal_to_probability,
)
from backtest.portfolio import DEFAULT_COST_PER_SIDE, evaluate_returns

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASELINE_A_AGENT = "fundamentals_agent"

STRATEGY_LABELS = {
    "baseline_a": "Baseline A：單一 Agent（財報）",
    "baseline_b": "Baseline B：簡單平均合併",
    "precision_weighted": "本系統：精度加權合併",
    "calibrated_average": "校準後簡單平均",
    "calibrated_precision_weighted": "校準後精度加權",
    "ic_weighted": "產業內 IC 加權",
}

# 校準曲線圖的標題（matplotlib 預設字型無 CJK，圖內用英文）
STRATEGY_LABELS_EN = {
    "baseline_a": "Baseline A: single agent (fundamentals)",
    "baseline_b": "Baseline B: simple average",
    "precision_weighted": "Precision-weighted (this system)",
    "calibrated_average": "Calibrated simple average",
    "calibrated_precision_weighted": "Calibrated precision-weighted",
    "ic_weighted": "Within-sector IC-weighted",
}


@dataclass
class PredictionEvent:
    """一個 (ticker, as_of_date) 上所有 Agent 的判斷與已實現結果。"""

    ticker: str
    as_of_date: str
    resolution_date: str  # as_of_date + horizon_days（交易日）
    outputs: dict[str, AgentOutput] = field(default_factory=dict)
    # 預測當下各 Agent 的校準後機率（到期時以此計算校準後精度）
    calibrated_p: dict[str, float] = field(default_factory=dict)
    outcome: int = 0  # 1 = horizon 期間報酬 > 0
    # 報酬層級評估用（synthetic 模式為 nan）
    price_return: float = float("nan")  # 未還原收盤價報酬
    forward_return: float = float("nan")  # 含息還原總報酬
    benchmark_return: float = float("nan")  # 同窗口 0050 含息總報酬


# ---------------------------------------------------------------------------
# Walk-forward 引擎
# ---------------------------------------------------------------------------

def calibrated_output(out: AgentOutput, p_cal: float) -> AgentOutput:
    """以校準後機率改寫 confidence（訊號方向不變；neutral 原樣保留）。"""
    if out.signal == "neutral":
        return out
    return dataclasses.replace(out, confidence=p_cal if out.signal == "bullish" else 1.0 - p_cal)


def run_walk_forward(
    events: list[PredictionEvent],
    tracker: PrecisionTracker,
    bullish_threshold: float = 0.1,
    bearish_threshold: float = -0.1,
    calibrator: AgentCalibrator | None = None,
    cal_tracker: PrecisionTracker | None = None,
    ic_weighter: ICWeighter | None = None,
) -> pd.DataFrame:
    """走時序回測。除了原本三個策略，另做 Agent 層級重新校準的兩個策略：
    合併前以 calibrator 修正各 Agent 機率；校準後精度加權使用 cal_tracker，
    其精度由「預測當下的校準後機率」的 Brier 累積（只反映資訊量，不含校準誤差）。
    """
    calibrator = calibrator or AgentCalibrator()
    if cal_tracker is None:
        cal_tracker = PrecisionTracker(
            tracker.storage_path.with_name(tracker.storage_path.stem + "_calibrated.json"),
            epsilon=tracker.epsilon, ema_alpha=tracker.ema_alpha, cold_start_min_n=tracker.cold_start_min_n,
        )
        cal_tracker.records = {}
    # 產業內 IC 加權：以已到期預測的產業內排序能力為權重（arbitrator/ic_weighting.py）
    ic_weighter = ic_weighter or ICWeighter()
    ic_weights_by_date: dict[str, dict[str, float]] = {}
    events = sorted(events, key=lambda e: (e.as_of_date, e.ticker))
    pending: list[PredictionEvent] = []
    rows = []

    for ev in events:
        # 先結算 horizon 已到期的舊預測 → 更新精度（規格 5.3）
        still_pending = []
        for old in pending:
            if old.resolution_date <= ev.as_of_date:
                for out in old.outputs.values():
                    p = signal_to_probability(out.signal, out.confidence)
                    brier = (p - old.outcome) ** 2
                    tracker.record_outcome(out.agent_id, old.ticker, brier, autosave=False)
                    calibrator.record(out.agent_id, p, old.outcome)
                    p_cal = old.calibrated_p[out.agent_id]
                    cal_tracker.record_outcome(out.agent_id, old.ticker, (p_cal - old.outcome) ** 2, autosave=False)
                ic_weighter.record(
                    old.as_of_date, old.ticker,
                    {o.agent_id: signal_to_probability(o.signal, o.confidence) for o in old.outputs.values()},
                    old.forward_return,
                )
            else:
                still_pending.append(old)
        pending = still_pending

        outputs = list(ev.outputs.values())
        agent_ids = [o.agent_id for o in outputs]

        # 本系統：以當下精度快照做加權合併
        precisions = tracker.get_precisions(agent_ids, ev.ticker)
        merged_pw = merge(outputs, precisions, bullish_threshold, bearish_threshold)

        # Baseline B：均等精度（簡單平均）
        equal = {a: 1.0 for a in agent_ids}
        merged_avg = merge(outputs, equal, bullish_threshold, bearish_threshold)

        # Agent 層級重新校準後再合併
        cal_outputs = []
        for o in outputs:
            ev.calibrated_p[o.agent_id] = calibrator.calibrate(
                o.agent_id, signal_to_probability(o.signal, o.confidence)
            )
            cal_outputs.append(calibrated_output(o, ev.calibrated_p[o.agent_id]))
        cal_precisions = cal_tracker.get_precisions(agent_ids, ev.ticker)
        merged_cal_avg = merge(cal_outputs, equal, bullish_threshold, bearish_threshold)
        merged_cal_pw = merge(cal_outputs, cal_precisions, bullish_threshold, bearish_threshold)

        # 產業內 IC 加權（同一時點所有股票共用一組權重）
        if ev.as_of_date not in ic_weights_by_date:
            ic_weights_by_date[ev.as_of_date] = ic_weighter.weights(agent_ids)
        ic_weights = {a: ic_weights_by_date[ev.as_of_date].get(a, 0.0) for a in agent_ids}
        merged_ic = merge(outputs, ic_weights, bullish_threshold, bearish_threshold)

        # Baseline A：單一 Agent
        base = ev.outputs.get(BASELINE_A_AGENT, outputs[0])

        row = {
            "ticker": ev.ticker,
            "as_of_date": ev.as_of_date,
            "outcome": ev.outcome,
            "baseline_a_signal": base.signal,
            "baseline_a_p": signal_to_probability(base.signal, base.confidence),
            "baseline_b_signal": merged_avg.signal,
            "baseline_b_p": merged_avg.probability_bullish,
            "precision_weighted_signal": merged_pw.signal,
            "precision_weighted_p": merged_pw.probability_bullish,
            "pw_uncertainty": merged_pw.uncertainty,
            "calibrated_average_signal": merged_cal_avg.signal,
            "calibrated_average_p": merged_cal_avg.probability_bullish,
            "calibrated_precision_weighted_signal": merged_cal_pw.signal,
            "calibrated_precision_weighted_p": merged_cal_pw.probability_bullish,
            "ic_weighted_signal": merged_ic.signal,
            "ic_weighted_p": merged_ic.probability_bullish,
            "price_return": ev.price_return,
            "forward_return": ev.forward_return,
            "benchmark_return": ev.benchmark_return,
            "excess_return": ev.forward_return - ev.benchmark_return,
        }
        for a in agent_ids:
            row[f"precision_{a}"] = precisions[a]
        for o in outputs:
            # 個別 Agent 的機率，供單一 Agent 消融分析
            row[f"p_{o.agent_id}"] = signal_to_probability(o.signal, o.confidence)
            row[f"llm_{o.agent_id}"] = bool(o.raw_features.get("llm_used", False))
            row[f"pcal_{o.agent_id}"] = ev.calibrated_p[o.agent_id]
            row[f"slope_{o.agent_id}"] = calibrator.slope(o.agent_id)
            row[f"calprecision_{o.agent_id}"] = cal_precisions[o.agent_id]
            row[f"icw_{o.agent_id}"] = ic_weights[o.agent_id]
        rows.append(row)
        pending.append(ev)

    tracker.save()
    cal_tracker.save()
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 評估與報表（規格 6.3）
# ---------------------------------------------------------------------------

def evaluate(df: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    outcomes = df["outcome"].astype(int).tolist()
    results = []
    for strat, label in STRATEGY_LABELS.items():
        ps = df[f"{strat}_p"].astype(float).tolist()
        signals = df[f"{strat}_signal"].tolist()
        acc, n_directional = directional_accuracy(signals, outcomes)
        results.append(
            {
                "strategy": strat,
                "label": label,
                "n": len(df),
                "mean_brier": mean_brier(ps, outcomes),
                "directional_accuracy": acc,
                "n_directional": n_directional,
                "ece": ece(ps, outcomes),
            }
        )
        reliability_diagram(
            ps, outcomes, str(output_dir / f"calibration_{strat}.png"), title=STRATEGY_LABELS_EN[strat]
        )
    return pd.DataFrame(results)


def has_returns(df: pd.DataFrame) -> bool:
    return "forward_return" in df and df["forward_return"].notna().any()


def return_report_lines(df: pd.DataFrame, returns: pd.DataFrame, cost_per_side: float) -> list[str]:
    """報酬層級評估章節（Markdown）。"""
    labels = {**STRATEGY_LABELS, "equal_weight": "對照：等權持有全部股票池", "benchmark_0050": "基準：0050"}
    r = returns.set_index("strategy")
    flips = int(((df["price_return"] > 0) != (df["forward_return"] > 0)).sum())
    pct = lambda x: f"{x * 100:+.1f}%"  # noqa: E731
    fmt_t = lambda t, p: f"{t:.2f} / {p:.2f}" if pd.notna(t) else "—"  # noqa: E731
    lines = [
        "",
        "## 報酬層級評估（long/neutral 組合 vs 0050）",
        "",
        f"- 組合：每期等權持有 bullish 標的，其餘持現金；單邊交易成本 {cost_per_side * 100:.3f}%",
        "- 報酬皆為含息還原總報酬（除權息、配股、分割已還原）",
        f"- 期間 0050 累積報酬：{pct(r['bench_total_return'].iloc[0])}",
        "",
        "| 策略 | 累積報酬 | 年化報酬 | 年化波動 | Sharpe | 最大回撤 | 與 0050 累積報酬差 | 每期超額 t / p | 持股期比例 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for key, row in r.iterrows():
        lines.append(
            f"| {labels.get(key, key)} | {pct(row['total_return'])} | {pct(row['ann_return'])} | "
            f"{row['ann_vol'] * 100:.1f}% | {row['sharpe']:.2f} | {pct(row['max_drawdown'])} | "
            f"{pct(row['excess_total'])} | {fmt_t(row['excess_t'], row['excess_p'])} | "
            f"{row['avg_exposure'] * 100:.0f}% |"
        )
    lines += [
        "",
        "### 連續報酬 Rank IC（看多機率 vs 20 日含息報酬）",
        "",
        "| 策略 | Pooled IC | p | 橫斷面 IC 平均 | t | p | 期數 |",
        "|---|---|---|---|---|---|---|",
    ]
    for key in STRATEGY_LABELS:
        row = r.loc[key]
        lines.append(
            f"| {labels[key]} | {row['ic_pooled']:+.3f} | {row['ic_pooled_p']:.2f} | "
            f"{row['ic_cs_mean']:+.3f} | {row['ic_cs_t']:.2f} | {row['ic_cs_p']:.2f} | {int(row['n_cs_dates'])} |"
        )
    lines += [
        "",
        "![Equity curves](equity_curves.png)",
        "",
        "- Pooled IC 混合了跨期的市場漲跌；橫斷面 IC 只看同一時點 5 檔之間的排序，",
        "  是選股能力的直接衡量（同時點機率全相同的期數不計入）。",
        "- p 值以常態近似計算，期數少時偏樂觀，僅供參考。",
        "- 夏普比率未扣無風險利率；每期為 20 個交易日持有、每 step 日再平衡。",
        f"- 未還原價與含息總報酬方向不一致的事件：{flips} / {len(df)}",
        "  （outcome 依 config `backtest.outcome_basis` 判定，見 config/tickers.yaml）。",
    ]
    return lines


def write_report(
    summary: pd.DataFrame,
    df: pd.DataFrame,
    output_dir: Path,
    mode: str,
    returns: pd.DataFrame | None = None,
    cost_per_side: float = DEFAULT_COST_PER_SIDE,
    outcome_basis: str = "price",
    llm_info: str = "未使用（規則式）",
    agent_output: str = "threshold",
) -> Path:
    pw = summary.set_index("strategy")
    brier_pw = pw.loc["precision_weighted", "mean_brier"]
    ece_pw = pw.loc["precision_weighted", "ece"]
    brier_ok = brier_pw < pw.loc["baseline_a", "mean_brier"] and brier_pw < pw.loc["baseline_b", "mean_brier"]
    ece_ok = ece_pw <= pw.loc["baseline_a", "ece"] and ece_pw <= pw.loc["baseline_b", "ece"]

    lines = [
        "# 回測比較報表：合併策略比較（規格 6.3 + Agent 層級重新校準）",
        "",
        f"- 執行模式：`{mode}`",
        f"- 預測事件數：{len(df)}（{df['ticker'].nunique()} 檔股票）",
        f"- Agent：{', '.join(c[2:] for c in df.columns if c.startswith('p_')) or '—'}",
        f"- 期間：{df['as_of_date'].min()} ~ {df['as_of_date'].max()}",
        f"- LLM 判讀：{llm_info}",
        f"- 規則式輸出：{agent_output}",
        "- 應驗判定：horizon 期末絕對報酬 > 0（20 個交易日，"
        + ("含息總報酬" if outcome_basis == "total_return" else "未還原收盤價")
        + "）",
        "",
        "| 策略 | 平均 Brier ↓ | 方向準確率 ↑ | ECE ↓ | n(方向) |",
        "|---|---|---|---|---|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['label']} | {r['mean_brier']:.4f} | "
            f"{r['directional_accuracy']:.3f} | {r['ece']:.4f} | {r['n_directional']} |"
        )
    agent_cols = [c for c in df.columns if c.startswith("p_")]
    if agent_cols:
        outcomes = df["outcome"].astype(int).tolist()
        lines += [
            "", "### 個別 Agent（消融）", "",
            "| Agent | 平均 Brier ↓ | ECE ↓ | 校準後 Brier ↓ | 校準後 ECE ↓ | 期末收縮係數 a | p ≠ 0.5 比例 | LLM 判讀比例 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for c in agent_cols:
            agent = c[2:]
            ps = df[c].astype(float).tolist()
            llm_col = f"llm_{agent}"
            llm_rate = f"{df[llm_col].astype(bool).mean() * 100:.0f}%" if llm_col in df else "—"
            cal = df[f"pcal_{agent}"].astype(float).tolist() if f"pcal_{agent}" in df else None
            cal_cells = f"{mean_brier(cal, outcomes):.4f} | {ece(cal, outcomes):.4f}" if cal else "— | —"
            slope = f"{df[f'slope_{agent}'].iloc[-1]:.2f}" if f"slope_{agent}" in df else "—"
            lines.append(
                f"| {agent} | {mean_brier(ps, outcomes):.4f} | {ece(ps, outcomes):.4f} | {cal_cells} | {slope} | "
                f"{(df[c] != 0.5).mean() * 100:.0f}% | {llm_rate} |"
            )
    lines += [
        "",
        "## 驗收標準（規格 6.3）",
        "",
        f"- 精度加權 Brier 優於兩個 baseline：{'✅ 通過' if brier_ok else '❌ 未通過'}",
        f"- 精度加權 ECE 不劣於兩個 baseline：{'✅ 通過' if ece_ok else '❌ 未通過'}",
        f"- 校準後精度加權 Brier 優於校準後簡單平均："
        f"{'✅ 通過' if pw.loc['calibrated_precision_weighted', 'mean_brier'] < pw.loc['calibrated_average', 'mean_brier'] else '❌ 未通過'}",
        "",
        "## 校準曲線",
        "",
        "![Baseline A](calibration_baseline_a.png)",
        "![Baseline B](calibration_baseline_b.png)",
        "![Precision Weighted](calibration_precision_weighted.png)",
        "",
        "## 備註",
        "",
        "- Baseline A 的機率採規格 6.1 轉換；合併策略的機率為各 Agent 6.1 機率的",
        "  加權線性意見池（權重同規格 5.2 合併公式）。",
        "- 精度加權在回測初期（冷啟動，n<5）等同簡單平均，差異隨精度記錄累積浮現。",
    ]
    if returns is not None:
        lines += return_report_lines(df, returns, cost_per_side)
    report_path = output_dir / "comparison_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    df.to_csv(output_dir / "backtest_results.csv", index=False)
    summary.to_csv(output_dir / "summary_metrics.csv", index=False)
    return report_path


# ---------------------------------------------------------------------------
# Synthetic 模式：可靠度不同的模擬 Agent，驗證精度加權機制
# ---------------------------------------------------------------------------

def generate_synthetic_events(
    tickers: list[str],
    n_dates: int = 60,
    horizon_days: int = 20,
    seed: int = 42,
) -> list[PredictionEvent]:
    """模擬情境：資訊互補 + 可靠度不同（貼近實際的多 Agent 設定）。

    - 每個 Agent 只有 60% 的時點「有資訊」（財報 Agent 在財報期、
      新聞 Agent 在有事件時），無資訊時輸出 neutral（低 confidence）
    - fundamentals_agent：有資訊時校準良好（實際命中率 = confidence）
    - news_agent：有資訊時過度自信（實際命中率 = confidence - 0.15）

    精度加權應隨記錄累積把權重移向可靠來源，Brier / ECE 優於簡單平均。
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n_dates * 5, freq="B")[::5][:n_dates]

    def synthetic_output(
        agent_id: str, ticker: str, as_of: str, outcome: int, overconfidence: float, p_informed: float = 0.6
    ):
        if rng.random() < p_informed:
            conf = float(rng.uniform(0.55, 0.85))
            hit_prob = max(conf - overconfidence, 0.5)
            correct = rng.random() < hit_prob
            signal = ("bullish" if outcome == 1 else "bearish") if correct else (
                "bearish" if outcome == 1 else "bullish"
            )
        else:
            signal, conf = "neutral", 0.3
        return AgentOutput(
            agent_id=agent_id,
            ticker=ticker,
            as_of_date=as_of,
            signal=signal,
            confidence=conf,
            horizon_days=horizon_days,
            rationale=f"synthetic agent (overconfidence={overconfidence})",
            evidence_refs=["synthetic"],
            raw_features={},
        )

    events = []
    for ticker in tickers:
        for d in dates:
            as_of = d.strftime("%Y-%m-%d")
            resolution = (d + pd.tseries.offsets.BDay(horizon_days)).strftime("%Y-%m-%d")
            outcome = int(rng.random() < 0.5)
            outputs = {
                "fundamentals_agent": synthetic_output("fundamentals_agent", ticker, as_of, outcome, 0.0),
                "news_agent": synthetic_output("news_agent", ticker, as_of, outcome, 0.15),
            }
            events.append(
                PredictionEvent(
                    ticker=ticker,
                    as_of_date=as_of,
                    resolution_date=resolution,
                    outputs=outputs,
                    outcome=outcome,
                )
            )
    return events


# ---------------------------------------------------------------------------
# FinMind 模式：真實資料驅動兩個 MVP Agent
# ---------------------------------------------------------------------------

def build_llm(config: dict):
    """依 config 的 llm 區塊建立 LLMClient（provider: anthropic / ollama）。"""
    from agents.llm_client import DEFAULT_OLLAMA_URL, LLMClient

    cfg = config.get("llm", {})
    cache_dir = cfg.get("cache_dir")
    return LLMClient(
        model=cfg.get("model", "claude-sonnet-4-6"),
        enabled=cfg.get("enabled", "auto"),
        provider=cfg.get("provider", "anthropic"),
        base_url=cfg.get("base_url", DEFAULT_OLLAMA_URL),
        cache_dir=PROJECT_ROOT / cache_dir if cache_dir else None,
        options=cfg.get("options"),
        think=cfg.get("think"),
    )


def generate_finmind_events(config: dict, llm=None) -> list[PredictionEvent]:
    from agents.fundamentals_agent import FundamentalsAgent
    from agents.macro_agent import MacroAgent
    from agents.news_agent import NewsAgent
    from agents.supply_chain_agent import SupplyChainAgent
    from data.fetch_macro import FinMindMacroProvider
    from data.fetch_supply_chain import FinMindSupplyChainProvider, load_graph
    from data.fetch_financials import FinMindClient, FinMindFundamentalsProvider, get_total_return_prices
    from data.fetch_news import FinMindNewsProvider

    bt = config["backtest"]
    horizon = int(bt["horizon_days"])
    step = int(bt["prediction_step_days"])
    outcome_basis = bt.get("outcome_basis", "price")
    if outcome_basis not in ("price", "total_return"):
        raise ValueError(f"backtest.outcome_basis 必須是 price 或 total_return，收到 {outcome_basis!r}")
    tickers = [u["ticker"] for u in config["universe"]]
    names = {u["ticker"]: u["name"] for u in config["universe"]}

    client = FinMindClient()
    llm = llm or build_llm(config)
    fetcher = None
    if config["news"].get("fetch_content"):
        from data.fetch_article import ArticleFetcher

        fetcher = ArticleFetcher(offline=bool(config["news"].get("content_offline", False)))
    mode = config.get("agent_output", "threshold")
    builders = {
        "fundamentals_agent": lambda: FundamentalsAgent(
            FinMindFundamentalsProvider(
                client, history_start=config.get("fundamentals", {}).get("history_start", "2020-01-01")
            ),
            llm=llm,
            horizon_days=horizon,
            output_mode=mode,
        ),
        "news_agent": lambda: NewsAgent(
            FinMindNewsProvider(client),
            llm=llm,
            window_days=int(config["news"]["window_days"]),
            horizon_days=horizon,
            ticker_names=names,
            content_fetcher=fetcher.fetch if fetcher else None,
            output_mode=mode,
        ),
        "macro_agent": lambda: MacroAgent(
            FinMindMacroProvider(client, history_start=config.get("macro", {}).get("history_start", "2023-01-01")),
            llm=llm,
            horizon_days=horizon,
            window_days=int(config.get("macro", {}).get("window_days", 20)),
            rate_window_days=int(config.get("macro", {}).get("rate_window_days", 60)),
            output_mode=mode,
        ),
        "supply_chain_agent": lambda: SupplyChainAgent(
            FinMindSupplyChainProvider(
                client, history_start=config.get("supply_chain", {}).get("history_start", "2023-01-01")
            ),
            graph=load_graph(PROJECT_ROOT / config.get("supply_chain", {}).get("graph", "config/supply_chain_graph.json")),
            llm=llm,
            horizon_days=horizon,
            window_days=int(config.get("supply_chain", {}).get("window_days", 20)),
            output_mode=mode,
        ),
    }
    agent_ids = config.get("agents", ["fundamentals_agent", "news_agent"])
    unknown = set(agent_ids) - set(builders)
    if unknown:
        raise ValueError(f"未知的 agent：{sorted(unknown)}，可用：{sorted(builders)}")
    agents = [builders[a]() for a in agent_ids]
    print(f"[info] 啟用 Agent：{', '.join(agent_ids)}（規則式輸出：{mode}）")

    # 各標的（含 0050 基準）的未還原價與含息還原價，以日期為索引
    bench_ticker = config.get("benchmark", {}).get("ticker", "0050.TW")
    series: dict[str, tuple[pd.Series, pd.Series]] = {}
    for t in [*tickers, bench_ticker]:
        prices = get_total_return_prices(client, t, bt["start_date"], bt["end_date"])
        if prices.empty:
            print(f"[warn] {t} 無價格資料，跳過")
            continue
        idx = pd.DatetimeIndex(prices["date"])
        series[t] = (
            pd.Series(prices["close"].astype(float).to_numpy(), index=idx),
            pd.Series(prices["adj_close"].astype(float).to_numpy(), index=idx),
        )
    bench = series.pop(bench_ticker, None)
    if bench is None:
        print(f"[warn] 基準 {bench_ticker} 無資料，超額報酬將為 nan")

    # 共用市場日曆：所有標的交易日的聯集。各標的依自身日曆取樣會在停牌
    # （如國巨 2025-08 停牌 7 日）後錯位，使組合持有期重疊、報酬重複計算。
    calendar = sorted(set().union(*(c.index for c, _ in series.values())))

    def window_return(s: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
        # 期末停牌時以停牌前最後收盤價計值
        return float(s.asof(end) / s.asof(start) - 1.0)

    # 隨時間變動的股票池（point-in-time）：每年只為當年成員產生事件
    membership = None
    if config.get("universe_membership"):
        from data.universe import load_membership

        membership = load_membership(PROJECT_ROOT / config["universe_membership"])

    events = []
    for ticker in tickers:
        if ticker not in series:
            continue
        close, adj = series[ticker]
        # 每 step 個交易日取一個預測點，需保留 horizon 個交易日算報酬
        for i in range(0, len(calendar) - horizon, step):
            start_ts, end_ts = calendar[i], calendar[i + horizon]
            if start_ts not in close.index:  # 當日停牌，無法進場
                continue
            if membership is not None and ticker not in membership.get(start_ts.year, set()):
                continue
            as_of = start_ts.strftime("%Y-%m-%d")
            end = end_ts.strftime("%Y-%m-%d")
            price_ret = window_return(close, start_ts, end_ts)
            total_ret = window_return(adj, start_ts, end_ts)
            bench_ret = window_return(bench[1], start_ts, end_ts) if bench else float("nan")
            # 使用者決策：20 日絕對報酬 > 0；outcome_basis 決定用未還原價或含息總報酬
            outcome = int((total_ret if outcome_basis == "total_return" else price_ret) > 0)
            outputs = {}
            for agent in agents:
                try:
                    outputs[agent.agent_id] = agent.analyze(ticker, as_of)
                except Exception as exc:  # 單點失敗不中斷整個回測
                    print(f"[warn] {agent.agent_id} {ticker} {as_of} 失敗: {exc}")
            if outputs:
                events.append(
                    PredictionEvent(
                        ticker=ticker,
                        as_of_date=as_of,
                        resolution_date=end,
                        outputs=outputs,
                        outcome=outcome,
                        price_return=price_ret,
                        forward_return=total_ret,
                        benchmark_return=bench_ret,
                    )
                )
        print(f"[info] {ticker}: 累計 {len(events)} 個預測事件")
    if fetcher is not None:
        print(f"[info] 新聞內文：{fetcher.stats}，快取狀態 {fetcher.coverage()}")
    return events


# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description="回測：比較三種合併策略（規格 6.3）")
    parser.add_argument("--mode", choices=["synthetic", "finmind"], default="synthetic")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config" / "tickers.yaml"))
    parser.add_argument(
        "--output-dir", default=None,
        help="輸出目錄，預設 reports/<mode>（synthetic → reports/synthetic）",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-dates", type=int, default=60, help="synthetic 模式的預測時點數")
    parser.add_argument("--start-date", default=None, help="覆寫 config 的回測起日（控制 API 額度用）")
    parser.add_argument("--end-date", default=None, help="覆寫 config 的回測迄日")
    parser.add_argument("--step-days", type=int, default=None, help="覆寫預測取樣間隔（交易日）")
    parser.add_argument("--llm-provider", choices=["anthropic", "ollama", "none"], default=None,
                        help="覆寫 config 的 llm.provider；none = 全部規則式")
    parser.add_argument("--llm-model", default=None, help="覆寫 config 的 llm.model（如 qwen3:8b、phi4）")
    parser.add_argument("--llm-num-thread", type=int, default=None,
                        help="ollama 推論使用的 CPU 執行緒數（與其他工作共用電腦時用來限制占用）")
    parser.add_argument("--llm-think", choices=["true", "false"], default=None,
                        help="推理模型（qwen3 等）是否開啟思考模式")
    parser.add_argument("--news-content", action="store_true",
                        help="為入選新聞抓取內文摘要（快取於本機 article_cache/，不納入版控）")
    parser.add_argument("--news-content-offline", action="store_true",
                        help="只用已快取的新聞內文，不連網")
    parser.add_argument("--agent-output", choices=["threshold", "continuous"], default=None,
                        help="規則式 Agent 的輸出：threshold（門檻化訊號，預設）或 continuous（由分數直接映射機率）")
    parser.add_argument("--supply-chain-graph", default=None,
                        help="覆寫供應鏈知識圖譜路徑（如 config/supply_chain_graph_v1.json）")
    parser.add_argument(
        "--agents", default=None,
        help="逗號分隔的 Agent 清單（如 fundamentals_agent,news_agent,macro_agent），覆寫 config 的 agents",
    )
    parser.add_argument(
        "--tickers", default=None,
        help="逗號分隔的 ticker 清單（如 2327.TW,2492.TW），只跑股票池的子集合以節省 API 額度",
    )
    args = parser.parse_args(argv)

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    llm_cfg = config.setdefault("llm", {})
    if args.llm_provider == "none":
        llm_cfg["enabled"] = False
    elif args.llm_provider:
        llm_cfg["provider"] = args.llm_provider
        llm_cfg["enabled"] = True
    if args.llm_model:
        llm_cfg["model"] = args.llm_model
    if args.llm_think:
        llm_cfg["think"] = args.llm_think == "true"
    if args.llm_num_thread:
        llm_cfg["options"] = {**(llm_cfg.get("options") or {}), "num_thread": args.llm_num_thread}
    if args.news_content or args.news_content_offline:
        config["news"]["fetch_content"] = True
        config["news"]["content_offline"] = args.news_content_offline
    if args.agent_output:
        config["agent_output"] = args.agent_output
    if args.supply_chain_graph:
        config.setdefault("supply_chain", {})["graph"] = args.supply_chain_graph
    if args.agents:
        config["agents"] = [a.strip() for a in args.agents.split(",")]
    if args.tickers:
        wanted = {t.strip() for t in args.tickers.split(",")}
        config["universe"] = [u for u in config["universe"] if u["ticker"] in wanted]
        if not config["universe"]:
            raise SystemExit(f"--tickers {args.tickers} 與 config 股票池無交集")
    if args.start_date:
        config["backtest"]["start_date"] = args.start_date
    if args.end_date:
        config["backtest"]["end_date"] = args.end_date
    if args.step_days:
        config["backtest"]["prediction_step_days"] = args.step_days
    arb = config["arbitrator"]
    output_dir = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "reports" / args.mode
    output_dir.mkdir(parents=True, exist_ok=True)

    llm_info = "未使用（規則式）"
    if args.mode == "synthetic":
        tickers = [u["ticker"] for u in config["universe"]]
        events = generate_synthetic_events(
            tickers, n_dates=args.n_dates, horizon_days=int(config["backtest"]["horizon_days"]), seed=args.seed
        )
    else:
        import dotenv

        dotenv.load_dotenv(PROJECT_ROOT / ".env")
        llm = build_llm(config)
        events = generate_finmind_events(config, llm=llm)
        if llm.available:
            st = llm.stats
            llm_info = (
                f"{llm.provider} / `{llm.model}`（新呼叫 {st['calls']}、快取命中 {st['cache_hits']}、"
                f"失敗退回規則式 {st['failures']}）"
            )
            print(f"[info] LLM：{llm_info}")

    if not events:
        raise SystemExit("沒有任何預測事件，無法回測")

    tracker = PrecisionTracker(
        output_dir / f"precision_records_{args.mode}.json",
        epsilon=float(arb["epsilon"]),
        ema_alpha=float(arb["ema_alpha"]),
        cold_start_min_n=int(arb["cold_start_min_n"]),
    )
    tracker.records = {}  # 每次回測從零開始累積精度

    calibrator = AgentCalibrator(
        min_n=int(arb.get("calibration_min_n", 10)),
        prior_strength=float(arb.get("calibration_prior_strength", 2.0)),
    )
    cal_tracker = PrecisionTracker(
        output_dir / f"precision_records_{args.mode}_calibrated.json",
        epsilon=float(arb["epsilon"]),
        ema_alpha=float(arb["ema_alpha"]),
        cold_start_min_n=int(arb["cold_start_min_n"]),
    )
    cal_tracker.records = {}

    ic_weighter = ICWeighter(
        sectors={u["ticker"]: u.get("segment", "?") for u in config["universe"]},
        window=int(arb.get("ic_window_dates", 24)),
        min_dates=int(arb.get("ic_min_dates", 6)),
    )

    df = run_walk_forward(
        events, tracker, float(arb["bullish_threshold"]), float(arb["bearish_threshold"]),
        calibrator=calibrator, cal_tracker=cal_tracker, ic_weighter=ic_weighter,
    )
    summary = evaluate(df, output_dir)

    returns = None
    cost = float(config["backtest"].get("cost_per_side", DEFAULT_COST_PER_SIDE))
    if has_returns(df):
        returns, periods = evaluate_returns(
            df,
            STRATEGY_LABELS_EN,
            step_days=int(config["backtest"]["prediction_step_days"]),
            cost_per_side=cost,
            plot_path=str(output_dir / "equity_curves.png"),
        )
        returns.to_csv(output_dir / "return_metrics.csv", index=False)
        periods.to_csv(output_dir / "period_returns.csv", index=False)

    report_path = write_report(
        summary, df, output_dir, args.mode, returns=returns, cost_per_side=cost,
        outcome_basis=config["backtest"].get("outcome_basis", "price"),
        llm_info=llm_info,
        agent_output=config.get("agent_output", "threshold"),
    )

    print(summary[["label", "mean_brier", "directional_accuracy", "ece"]].to_string(index=False))
    if returns is not None:
        cols = ["strategy", "total_return", "ann_return", "sharpe", "max_drawdown", "excess_total", "ic_cs_mean"]
        print(returns[[c for c in cols if c in returns]].to_string(index=False))
    print(f"\n報表：{report_path}")
    return report_path


if __name__ == "__main__":
    main()
