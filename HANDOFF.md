# HANDOFF — 專案交接狀態

更新日期：2026-10-06

## 一句話
多代理人精度加權投資研究系統（台股被動元件）。MVP（M1–M5）、5 檔完整真實回測、報酬層級評估、Phase 2 總經/籌碼 Agent、地端 LLM 判讀實驗（qwen3:8b）、Agent 層級重新校準已完成；供應鏈 Agent 尚未開始。

## 架構
- `config/tickers.yaml`：股票池與全部參數（horizon、閾值、EMA α、冷啟動門檻、基準 0050、交易成本、`outcome_basis`、`agents` 清單、`macro` 窗口）
- `agents/llm_client.py`：provider 可選 anthropic / ollama（地端），JSON schema 結構化輸出、temperature 0、回應快取於 `data_cache/llm/`（納入版控，重跑不需重新推論）
- `agents/`：`base.py` 介面 `analyze(ticker, as_of_date) → AgentOutput`，以及共用的規則評分 `score_components`；`fundamentals_agent`、`news_agent`、`macro_agent` 已實作（規則式；LLM 可用時改用 LLM 判讀，失敗退回規則式；`raw_features.llm_used` 標示是否實際採用 LLM）；`supply_chain_agent` 僅為 `NotImplementedError` 佔位
- `arbitrator/`：`precision_tracker.py`（Brier EMA、n<5 冷啟動）、`merge.py`（precision×confidence 加權）、`calibration.py`（Agent 層級收縮校準 p' = σ(a·logit p)，a ∈ [0,1]，walk-forward 擬合）
- `data/`：FinMind 抓取（快取/節流/額度等待）、含息還原價（`get_total_return_prices`：以 DividendResult + SplitPrice 自行還原，PriceAdj 需付費）、`fetch_macro.py`（法人/外資持股/融資/匯率/美債/大盤外資，只用 as_of 前一日以前的資料）、RSS 新聞、向量庫封裝
- `backtest/`：`run_backtest.py`（walk-forward，共用市場日曆取樣，T+20 到期才更新精度，財報公告遞延防 look-ahead，`--agents` 選擇 Agent，報表含個別 Agent 消融）、`metrics.py`（Brier/ECE）、`portfolio.py`（連續報酬 Rank IC、long/neutral 組合、vs 0050）
- `data_cache/` 刻意納入版控，重跑既有範圍不耗 API 額度

## 最新結果（135 事件，2024-01~2026-05，規格 5.2 修訂後）
| 策略 | 規則式 2 Agent | 規則式 3 Agent | LLM qwen3:8b（3 Agent） |
|---|---|---|---|
| 單一 Agent（財報） | 0.2593 / +22.8% | 0.2593 / +22.8% | 0.3354 / +8.3% |
| 簡單平均 | 0.2540 / +53.4% | **0.2530** / −23.2% | 0.2726 / −25.0% |
| 精度加權 | 0.2542 / −11.9% | 0.2532 / −18.6% | 0.2733 / −24.4% |
| 校準後簡單平均 | 0.2538 / −23.5% | 0.2535 / −12.3% | 0.2547 / −22.1% |
| 校準後精度加權 | 0.2539 / −23.5% | 0.2536 / −12.3% | 0.2544 / −20.1% |

（格式：平均 Brier / 組合累積報酬；0050 同期 +191.7%，等權持有 5 檔 +121.3%）

- 報表：規則式 2 Agent = `reports/finmind_full`，3 Agent = `reports/finmind_macro`，LLM = `reports/finmind_llm_qwen3`，synthetic = `reports/synthetic`（`--n-dates 100`）。
- **核心結論**：所有設定的 Brier 都高於 0.25（永遠猜 50% 的無資訊基準）。Agent（規則式或 LLM）都沒有預測力，系統表態時方向準確率約 43–50%。瓶頸在 Agent 的資訊量，不在合併機制。
- **組合報酬對訊號公式極度敏感**：修訂前規則式 3 Agent 合併是 +182%（93% 時間持股），修訂後 −12% 到 −23%（30–56% 時間持股）。之前的報酬來自多頭中多數時間持股，不是判讀能力。所有策略都顯著輸 0050。
- **精度加權機制本身成立**：synthetic 20 seeds 中，精度加權 < 簡單平均 17/20，校準後版本 18/20。真實資料中各 Agent 資訊量相近，精度加權等於或略輸簡單平均。
- **LLM 判讀（`docs/llm_experiment_report.md`）**：386 次呼叫 0 失敗；嚴重過度自信（信心 ≥ 0.8 的命中率 45–53%），總經 Agent 135 次全部看空。
- **Agent 層級重新校準（`docs/calibration_report.md`）**：LLM 合併 Brier 0.2726 → 0.2544。校準後 LLM 的精度比從 1.35–2.63 縮回 1.04–1.28，原本的「分化」是過度自信程度不同，不是資訊量不同。
- **2026-10-07 規格 5.2 修訂**（`arbitrator/merge.py`，校準報告第 8 節）：final_score = Σ(precision·κ·s)/Σprecision = 2p − 1，κ = |2p − 1| 為確信度，門檻 ±0.1（合併機率 0.55/0.45）。p = 0.5 的 Agent 不再投票，訊號與機率一致。**代價**：合併機率是純精度加權平均，中性輸出會稀釋，synthetic 中合併變得信心不足（合併 < 單一 Agent 只有 2/20）。
- 2026-10-06 的修正：共用市場日曆取樣；outcome 改用含息總報酬；有方向訊號的信心下限 0.5（`agents/base.py:_build_output`）。
- 履歷/對外描述注意：Agent 只有財報、新聞、總經/籌碼三個，不要宣稱含供應鏈訊號；也不要宣稱打敗大盤、有預測力或有選股能力。可宣稱的是：完整的 walk-forward 評估框架、精度加權機制在 synthetic 中驗證有效、對真實資料負結果的誠實分析。

## 待辦（依建議順序）
1. **提升 Agent 本身的資訊量**（目前真正的瓶頸）：新聞內文（目前只有標題）、更強的 LLM（雲端 Claude：`--llm-provider anthropic`）或 qwen3 思考模式（`--llm-think true`）、供應鏈 Agent（知識圖譜，如 `config/supply_chain_graph.json`）
2. 合併機率的中性稀釋（規格 5.2 修訂的代價）：讓中性 Agent 棄權不進入平均，或改用對數意見池（中性的 logit 為 0，天然不影響結果）
3. 合併後再校準：線性池平均已校準機率會信心不足
4. 規格第 9 節待人工決策：新聞可信度分級、MOPS 爬蟲頻率（horizon 已定為 20 日）
5. 報酬評估可延伸：機率加權部位（而非 bullish 等權）、相對 0050 的 outcome 定義（超額報酬 > 0）
6. 總經/籌碼 Agent 可延伸：半導體庫存週期（免費層無資料）、主力分點、借券等個股籌碼

## 已知限制
每檔僅 27 筆樣本；新聞僅標題；期間與族群單一；地端 LLM 僅測過 qwen3:8b（純 CPU 每次呼叫約 1 分鐘，phi4 約 8 分鐘，未跑完整實驗）；總經分量同一時點各檔相同（對選股無幫助）；總經 Agent 的門檻為經驗值；組合報酬每期之間有 1 個交易日空檔（step 21 > horizon 20）未計入；p 值為常態近似。

## 操作
```bash
.venv/Scripts/python -m pytest tests -q          # 104 tests（Windows；macOS/Linux 用 .venv/bin/python）
# 3 Agent（config 預設）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --output-dir reports/finmind_macro
# LLM 判讀（需 Ollama + qwen3:8b；回應已快取，重跑秒完）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --llm-provider ollama --llm-model qwen3:8b --llm-think false --output-dir reports/finmind_llm_qwen3
# 2 Agent 對照組
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent --output-dir reports/finmind_full
```
