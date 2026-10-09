"""回測成績單：預測準確度（方向準確率、Brier）與組合風險報酬（年化報酬、Sharpe、最大回撤），對 0050 與等權持有。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/scorecard.py            # 輸出 docs/scorecard.md 與 reports/scorecard.json

資料來源（都已在版控內，不需重跑回測）：
- reports/finmind_full、reports/finmind_pit：summary_metrics.csv（準確度）、return_metrics.csv / period_returns.csv（報酬）
- reports/sector_neutral/periods_*.csv：analysis/sector_neutral_portfolio.py 起點 0 的逐期報酬（與 finmind_pit 同一組預測日）
Sharpe = 年化報酬 / 年化波動（無風險利率以 0 計）；最大回撤以每期（20 個交易日）淨值計，期中波動不計入。
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.portfolio import performance_stats  # noqa: E402

PERIODS_PER_YEAR = 252 / 21

PANELS = [
    {
        "key": "five", "report": "finmind_full",
        "title": "5 檔被動元件 × 2024-01 ~ 2026-05（財報 + 新聞 Agent）",
        "note": "原始 MVP 設定：135 筆 walk-forward 預測（5 檔 × 27 期）。",
        "strategies": [
            ("baseline_a", "單一 Agent（財報）"), ("baseline_b", "簡單平均合併"), ("precision_weighted", "精度加權合併"),
            ("calibrated_precision_weighted", "校準後精度加權"),
        ],
        "extra": [],
    },
    {
        "key": "pit", "report": "finmind_pit",
        "title": "無選股偏誤股票池（每年前 100 檔）× 2019-01 ~ 2026-05（財報 + 總經籌碼 + 供應鏈 Agent，連續輸出）",
        "note": "8,475 筆 walk-forward 預測；股票池含之後下市的公司。",
        "strategies": [
            ("baseline_a", "單一 Agent（財報）"), ("baseline_b", "簡單平均合併"), ("precision_weighted", "精度加權合併"),
            ("calibrated_precision_weighted", "校準後精度加權"), ("ic_weighted", "產業內 IC 加權合併"),
        ],
        "extra": [
            ("periods_default.csv", "sn_net", "產業中性做多（財報，前 1/3）"),
            ("periods_keep50.csv", "sn_net", "產業中性做多 + 緩衝（事後調整）"),
            ("periods_default.csv", "ls_net", "產業內多空（財報，分析用）"),
        ],
    },
]


def panel_rows(panel: dict) -> dict:
    rdir = ROOT / "reports" / panel["report"]
    acc = pd.read_csv(rdir / "summary_metrics.csv").set_index("strategy")
    ret = pd.read_csv(rdir / "return_metrics.csv").set_index("strategy")
    results = pd.read_csv(rdir / "backtest_results.csv")
    periods = pd.read_csv(rdir / "period_returns.csv").set_index("as_of_date")
    bench = periods["benchmark_0050"]

    def ret_fields(s):
        return {"ann_return": s["ann_return"], "sharpe": s["sharpe"], "max_drawdown": s["max_drawdown"],
                "total_return": s["total_return"], "excess_vs_0050": s["total_return"] - s["bench_total_return"],
                "excess_vs_ew": s["total_return"] - ret.loc["equal_weight", "total_return"]}

    rows = []
    for key, label in panel["strategies"]:
        a = acc.loc[key]
        rows.append({"label": label, "kind": "strategy", "directional_accuracy": a["directional_accuracy"],
                     "n_directional": int(a["n_directional"]), "brier": a["mean_brier"],
                     "avg_n_long": ret.loc[key, "avg_n_long"], **ret_fields(ret.loc[key])})
    for fname, col, label in panel["extra"]:
        p = pd.read_csv(ROOT / "reports" / "sector_neutral" / fname)
        p["d"] = pd.to_datetime(p["date"]).dt.strftime("%Y-%m-%d")
        s = performance_stats(p.set_index("d")[col], bench, PERIODS_PER_YEAR)
        n_hold = p["n_sn"].mean() if col.startswith("sn") else p["n_ls"].mean()
        rows.append({"label": label, "kind": "portfolio", "directional_accuracy": None, "n_directional": None,
                     "brier": None, "avg_n_long": n_hold,
                     **ret_fields({**s, "bench_total_return": s["bench_total_return"]})})
    for key, label in (("equal_weight", "等權持有全部股票"), ("benchmark_0050", "0050（大盤基準）")):
        rows.append({"label": label, "kind": "benchmark", "directional_accuracy": None, "n_directional": None,
                     "brier": None, "avg_n_long": ret.loc[key, "avg_n_long"] if key == "equal_weight" else None,
                     **ret_fields(ret.loc[key])})
    base_rate = float(results["outcome"].mean())
    return {"key": panel["key"], "title": panel["title"], "note": panel["note"], "n_predictions": len(results),
            "n_periods": int(ret.loc["baseline_a", "n_periods"]), "start": periods.index.min(), "end": periods.index.max(),
            "base_rate": base_rate, "base_brier": base_rate * (1 - base_rate), "rows": rows}


def pct(v, d=1, sign=False):
    if v is None or pd.isna(v):
        return "—"
    return f"{v * 100:{'+' if sign else ''}.{d}f}%"


def pts(v):
    return "—" if v is None or pd.isna(v) else f"{v * 100:+.0f} pt"


def num(v, d=2):
    return "—" if v is None or pd.isna(v) else f"{v:.{d}f}"


def to_markdown(panels: list[dict]) -> str:
    out = [
        "# 回測成績單（自動產生）",
        "",
        "由 [analysis/scorecard.py](../analysis/scorecard.py) 從 `reports/` 產生；所有報酬皆為含息總報酬、扣交易成本"
        "（換手量 × 單邊 0.29625%），每 21 個交易日換倉、持有 20 個交易日。",
        "",
        "- **方向準確率**：有表態（看多或看空）的預測中，方向與 20 日後實際報酬一致的比例。"
        "對照組是「永遠猜上漲」的命中率（= 期間內上漲的比例）。",
        "- **Brier**：(看多機率 − 實際結果)² 的平均，越低越好；對照組是「永遠預測基率」的 Brier。",
        "- **組合**：看多（或產業中性前段）的股票等權持有，其餘持現金。**Sharpe** = 年化報酬 ÷ 年化波動（無風險利率以 0 計）；"
        "**最大回撤**以每期淨值計。累積差 = 策略累積報酬 − 對照累積報酬（百分點，pt）。",
        "",
    ]
    for p in panels:
        out += [f"## {p['title']}", "", f"{p['note']} 預測日 {p['start']} ~ {p['end']}，{p['n_periods']} 期。", "",
                f"- 對照：「永遠猜上漲」方向準確率 **{pct(p['base_rate'])}**；永遠預測基率的 Brier **{p['base_brier']:.4f}**",
                "",
                "| 策略 | 方向準確率（表態筆數） | Brier | 年化報酬 | Sharpe | 最大回撤 | 累積報酬 | 累積差 vs 0050 | 累積差 vs 等權 | 平均持股 |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        for r in p["rows"]:
            acc = "—" if r["directional_accuracy"] is None else f"{pct(r['directional_accuracy'])}（{r['n_directional']}）"
            name = f"**{r['label']}**" if r["kind"] == "benchmark" else r["label"]
            out.append(f"| {name} | {acc} | {num(r['brier'], 4)} | {pct(r['ann_return'], 1, True)} | {num(r['sharpe'])} | "
                       f"{pct(r['max_drawdown'])} | {pct(r['total_return'], 0, True)} | "
                       f"{'—' if r['kind'] == 'benchmark' and r['label'].startswith('0050') else pts(r['excess_vs_0050'])} | "
                       f"{'—' if r['kind'] == 'benchmark' else pts(r['excess_vs_ew'])} | {num(r['avg_n_long'], 1)} |")
        out.append("")
    out += [
        "## 怎麼讀",
        "",
        "1. **預測準確度沒有勝過簡單對照**：方向準確率大多 45–51%（5 檔的校準後策略只表態 24 筆、29.2%），"
        "低於「永遠猜上漲」（54.8% / 53.4%）；"
        "唯一較高的是無偏誤股票池的校準後精度加權（57.1%），但校準把機率壓到 0.5 附近，85 期只表態 42 筆，"
        "不足以下結論。所有策略的 Brier 都不比永遠預測基率好：Agent 的機率沒有可用的漲跌方向資訊。",
        "2. **5 檔設定全面落後大盤**：期間 0050 是強多頭，所有策略的累積報酬、Sharpe 都明顯低於 0050 與等權持有。",
        "3. **無偏誤股票池上，財報 Agent 有小幅選股能力**：單一財報 Agent 與產業中性組合的累積報酬比等權持有多 "
        "140–200 pt、年化報酬（33.6–35.0%）略高於 0050（30.7%）；但最大回撤（約 −47%）比 0050（−31.6%）深，"
        "Sharpe（1.24–1.27）低於 0050（1.49）、高於等權持有（1.14）——風險調整後並沒有贏過大盤。",
        "   這個優勢來自產業內排序（產業內 IC 約 +0.03，見 [sector_neutral_report.md](sector_neutral_report.md)），"
        "不是判斷漲跌方向。",
        "4. **合併多個 Agent（含精度加權）都比只用財報 Agent 差**，因為其他 Agent 沒有資訊，只會稀釋訊號。",
        "5. 每個數字都是單一取樣起點；21 種起點的穩健性與 t 值見各報告。產業內多空的放空成本未計，只作分析用。",
        "",
    ]
    return "\n".join(out)


def main():
    panels = [panel_rows(p) for p in PANELS]
    (ROOT / "docs" / "scorecard.md").write_text(to_markdown(panels), encoding="utf-8")
    clean = json.loads(pd.Series(panels).to_json(orient="values", force_ascii=False))
    (ROOT / "reports" / "scorecard.json").write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    print((ROOT / "docs" / "scorecard.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
