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
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.base import AgentOutput
from arbitrator.merge import merge
from arbitrator.precision_tracker import PrecisionTracker
from backtest.metrics import (
    directional_accuracy,
    ece,
    mean_brier,
    reliability_diagram,
    signal_to_probability,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASELINE_A_AGENT = "fundamentals_agent"

STRATEGY_LABELS = {
    "baseline_a": "Baseline A：單一 Agent（財報）",
    "baseline_b": "Baseline B：簡單平均合併",
    "precision_weighted": "本系統：精度加權合併",
}

# 校準曲線圖的標題（matplotlib 預設字型無 CJK，圖內用英文）
STRATEGY_LABELS_EN = {
    "baseline_a": "Baseline A: single agent (fundamentals)",
    "baseline_b": "Baseline B: simple average",
    "precision_weighted": "Precision-weighted (this system)",
}


@dataclass
class PredictionEvent:
    """一個 (ticker, as_of_date) 上所有 Agent 的判斷與已實現結果。"""

    ticker: str
    as_of_date: str
    resolution_date: str  # as_of_date + horizon_days（交易日）
    outputs: dict[str, AgentOutput] = field(default_factory=dict)
    outcome: int = 0  # 1 = horizon 期間報酬 > 0


# ---------------------------------------------------------------------------
# Walk-forward 引擎
# ---------------------------------------------------------------------------

def run_walk_forward(
    events: list[PredictionEvent],
    tracker: PrecisionTracker,
    bullish_threshold: float = 0.3,
    bearish_threshold: float = -0.3,
) -> pd.DataFrame:
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
        }
        for a in agent_ids:
            row[f"precision_{a}"] = precisions[a]
        rows.append(row)
        pending.append(ev)

    tracker.save()
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


def write_report(summary: pd.DataFrame, df: pd.DataFrame, output_dir: Path, mode: str) -> Path:
    pw = summary.set_index("strategy")
    brier_pw = pw.loc["precision_weighted", "mean_brier"]
    ece_pw = pw.loc["precision_weighted", "ece"]
    brier_ok = brier_pw < pw.loc["baseline_a", "mean_brier"] and brier_pw < pw.loc["baseline_b", "mean_brier"]
    ece_ok = ece_pw <= pw.loc["baseline_a", "ece"] and ece_pw <= pw.loc["baseline_b", "ece"]

    lines = [
        "# 回測比較報表：三種合併策略（規格 6.3）",
        "",
        f"- 執行模式：`{mode}`",
        f"- 預測事件數：{len(df)}（{df['ticker'].nunique()} 檔股票）",
        f"- 期間：{df['as_of_date'].min()} ~ {df['as_of_date'].max()}",
        "- 應驗判定：horizon 期末絕對報酬 > 0（20 個交易日）",
        "",
        "| 策略 | 平均 Brier ↓ | 方向準確率 ↑ | ECE ↓ | n(方向) |",
        "|---|---|---|---|---|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['label']} | {r['mean_brier']:.4f} | "
            f"{r['directional_accuracy']:.3f} | {r['ece']:.4f} | {r['n_directional']} |"
        )
    lines += [
        "",
        "## 驗收標準（規格 6.3）",
        "",
        f"- 精度加權 Brier 優於兩個 baseline：{'✅ 通過' if brier_ok else '❌ 未通過'}",
        f"- 精度加權 ECE 不劣於兩個 baseline：{'✅ 通過' if ece_ok else '❌ 未通過'}",
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

def generate_finmind_events(config: dict) -> list[PredictionEvent]:
    from agents.fundamentals_agent import FundamentalsAgent
    from agents.llm_client import LLMClient
    from agents.news_agent import NewsAgent
    from data.fetch_financials import FinMindClient, FinMindFundamentalsProvider, get_daily_prices
    from data.fetch_news import FinMindNewsProvider

    bt = config["backtest"]
    horizon = int(bt["horizon_days"])
    step = int(bt["prediction_step_days"])
    tickers = [u["ticker"] for u in config["universe"]]
    names = {u["ticker"]: u["name"] for u in config["universe"]}

    client = FinMindClient()
    llm = LLMClient(model=config["llm"]["model"], enabled=config["llm"]["enabled"])
    fund_agent = FundamentalsAgent(FinMindFundamentalsProvider(client), llm=llm, horizon_days=horizon)
    news_agent = NewsAgent(
        FinMindNewsProvider(client),
        llm=llm,
        window_days=int(config["news"]["window_days"]),
        horizon_days=horizon,
        ticker_names=names,
    )

    events = []
    for ticker in tickers:
        prices = get_daily_prices(client, ticker, bt["start_date"], bt["end_date"])
        if prices.empty:
            print(f"[warn] {ticker} 無價格資料，跳過")
            continue
        closes = prices["close"].astype(float).to_numpy()
        dates = prices["date"].dt.strftime("%Y-%m-%d").tolist()
        # 每 step 個交易日取一個預測點，需保留 horizon 個交易日算報酬
        for idx in range(0, len(dates) - horizon, step):
            as_of = dates[idx]
            ret = closes[idx + horizon] / closes[idx] - 1.0
            outcome = int(ret > 0)  # 使用者決策：20 日絕對報酬 > 0
            outputs = {}
            for agent in (fund_agent, news_agent):
                try:
                    outputs[agent.agent_id] = agent.analyze(ticker, as_of)
                except Exception as exc:  # 單點失敗不中斷整個回測
                    print(f"[warn] {agent.agent_id} {ticker} {as_of} 失敗: {exc}")
            if outputs:
                events.append(
                    PredictionEvent(
                        ticker=ticker,
                        as_of_date=as_of,
                        resolution_date=dates[idx + horizon],
                        outputs=outputs,
                        outcome=outcome,
                    )
                )
        print(f"[info] {ticker}: 累計 {len(events)} 個預測事件")
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
    parser.add_argument(
        "--tickers", default=None,
        help="逗號分隔的 ticker 清單（如 2327.TW,2492.TW），只跑股票池的子集合以節省 API 額度",
    )
    args = parser.parse_args(argv)

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
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

    if args.mode == "synthetic":
        tickers = [u["ticker"] for u in config["universe"]]
        events = generate_synthetic_events(
            tickers, n_dates=args.n_dates, horizon_days=int(config["backtest"]["horizon_days"]), seed=args.seed
        )
    else:
        import dotenv

        dotenv.load_dotenv(PROJECT_ROOT / ".env")
        events = generate_finmind_events(config)

    if not events:
        raise SystemExit("沒有任何預測事件，無法回測")

    tracker = PrecisionTracker(
        output_dir / f"precision_records_{args.mode}.json",
        epsilon=float(arb["epsilon"]),
        ema_alpha=float(arb["ema_alpha"]),
        cold_start_min_n=int(arb["cold_start_min_n"]),
    )
    tracker.records = {}  # 每次回測從零開始累積精度

    df = run_walk_forward(
        events, tracker, float(arb["bullish_threshold"]), float(arb["bearish_threshold"])
    )
    summary = evaluate(df, output_dir)
    report_path = write_report(summary, df, output_dir, args.mode)

    print(summary[["label", "mean_brier", "directional_accuracy", "ece"]].to_string(index=False))
    print(f"\n報表：{report_path}")
    return report_path


if __name__ == "__main__":
    main()
