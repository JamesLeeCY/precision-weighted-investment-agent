# HANDOFF — 專案交接狀態

更新日期：2026-10-06

## 一句話
多代理人精度加權投資研究系統（台股被動元件）。MVP（M1–M5）、5 檔完整真實回測與報酬層級評估已完成；Phase 2 與 LLM 實驗尚未開始。

## 架構
- `config/tickers.yaml`：股票池與全部參數（horizon、閾值、EMA α、冷啟動門檻、基準 0050、交易成本、`outcome_basis`）
- `agents/`：`base.py` 介面 `analyze(ticker, as_of_date) → AgentOutput`；`fundamentals_agent`、`news_agent` 已實作（規則式，有 `ANTHROPIC_API_KEY` 時走 LLM，失敗退回規則式）；`supply_chain_agent`、`macro_agent` 僅為 `NotImplementedError` 佔位
- `arbitrator/`：`precision_tracker.py`（Brier EMA、n<5 冷啟動）、`merge.py`（precision×confidence 加權）
- `data/`：FinMind 抓取（快取/節流/額度等待）、含息還原價（`get_total_return_prices`：以 DividendResult + SplitPrice 自行還原，PriceAdj 需付費）、RSS 新聞、向量庫封裝
- `backtest/`：`run_backtest.py`（walk-forward，共用市場日曆取樣，T+20 到期才更新精度，財報公告遞延防 look-ahead）、`metrics.py`（Brier/ECE）、`portfolio.py`（連續報酬 Rank IC、long/neutral 組合、vs 0050）
- `data_cache/` 刻意納入版控，重跑既有範圍不耗 API 額度

## 最新結果（reports/finmind_full，135 事件，2024-01~2026-05）
| 策略 | Brier | ECE | Hit rate | 累積報酬 | 橫斷面 IC |
|---|---|---|---|---|---|
| 單一 Agent（財報） | 0.2584 | 0.124 | 47.8% | +22.8% | −0.134 |
| 簡單平均 | 0.2549 | 0.080 | 48.8% | +86.5% | −0.133 |
| 精度加權 | 0.2550 | 0.087 | 48.8% | +86.5% | −0.145 |
| 等權持有 5 檔 | — | — | — | +121.3% | — |
| 0050 | — | — | — | +191.7% | — |

- 基率（20 日含息總報酬為正）54.8%；無資訊 Brier 基準 0.25。Hit rate 低於基率。
- 報酬層級：long/neutral、含息總報酬、扣成本（單邊 0.296%）、27 期。所有策略落後 0050 與等權持有；單一 Agent 每期超額 t=−2.13（顯著為負），合併策略 t=−1.03。橫斷面 IC 為負但不顯著（t≈−1.2）→ 規則式 Agent 無選股能力。
- 多 Agent 合併優於單一 Agent；精度加權與簡單平均訊號完全相同（精度比僅 1.00–1.24）。Synthetic（可靠度分化）下 17/20 seeds 精度加權較佳。
- 2026-10-06 修正：原本各股依自身交易日曆取樣，國巨 2025-08 停牌後日期錯位（組合持有期重疊）。改為共用市場日曆，國巨最後 8 個事件日期改變，Brier 數字因此微調（舊 0.2565/0.2529/0.2530）。
- 2026-10-06 決策：outcome 改用含息總報酬（`outcome_basis: total_return`）。未還原價在國巨 2025-08 分割（546→136.5）使 2025-07-29 那期顯示 −74%（實際 +3.6%）；僅此 1 筆受影響，該事件機率為 0.5 故 Brier 不變、ECE 變動。
- 履歷/對外描述注意：目前只有財報 + 新聞兩個 Agent，不要宣稱含供應鏈訊號；也不要宣稱打敗大盤。

## 待辦（依建議順序）
1. LLM 判讀模式可靠度分化實驗（需 `ANTHROPIC_API_KEY`，重跑同期間比較規則式 vs LLM；報酬層級評估會自動一起產出）
2. Phase 2：總經/籌碼 Agent（純量化規則，較易）、供應鏈 Agent（知識圖譜，如 `config/supply_chain_graph.json`）；接入後重跑回測
3. 合併機制升級：對數意見池 / Agent 層級重新校準（技術筆記第 6 節）
4. 規格第 9 節待人工決策：新聞可信度分級、MOPS 爬蟲頻率（horizon 已定為 20 日）
5. 報酬評估可延伸：機率加權部位（而非 bullish 等權）、相對 0050 的 outcome 定義（超額報酬 > 0）

## 已知限制
每檔僅 27 筆樣本；新聞僅標題；期間與族群單一；LLM 判讀未使用；組合報酬每期之間有 1 個交易日空檔（step 21 > horizon 20）未計入；p 值為常態近似。

## 操作
```bash
.venv/Scripts/python -m pytest tests -q          # 63 tests（Windows；macOS/Linux 用 .venv/bin/python）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --output-dir reports/finmind_full
```
