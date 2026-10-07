# HANDOFF — 專案交接狀態

更新日期：2026-10-06

## 一句話
多代理人精度加權投資研究系統（台股被動元件）。MVP（M1–M5）、5 檔完整真實回測、報酬層級評估、Phase 2 總經/籌碼 Agent、地端 LLM 判讀實驗（qwen3:8b）已完成；供應鏈 Agent 尚未開始。

## 架構
- `config/tickers.yaml`：股票池與全部參數（horizon、閾值、EMA α、冷啟動門檻、基準 0050、交易成本、`outcome_basis`、`agents` 清單、`macro` 窗口）
- `agents/llm_client.py`：provider 可選 anthropic / ollama（地端），JSON schema 結構化輸出、temperature 0、回應快取於 `data_cache/llm/`（納入版控，重跑不需重新推論）
- `agents/`：`base.py` 介面 `analyze(ticker, as_of_date) → AgentOutput`，以及共用的規則評分 `score_components`；`fundamentals_agent`、`news_agent`、`macro_agent` 已實作（規則式；LLM 可用時改用 LLM 判讀，失敗退回規則式；`raw_features.llm_used` 標示是否實際採用 LLM）；`supply_chain_agent` 僅為 `NotImplementedError` 佔位
- `arbitrator/`：`precision_tracker.py`（Brier EMA、n<5 冷啟動）、`merge.py`（precision×confidence 加權）
- `data/`：FinMind 抓取（快取/節流/額度等待）、含息還原價（`get_total_return_prices`：以 DividendResult + SplitPrice 自行還原，PriceAdj 需付費）、`fetch_macro.py`（法人/外資持股/融資/匯率/美債/大盤外資，只用 as_of 前一日以前的資料）、RSS 新聞、向量庫封裝
- `backtest/`：`run_backtest.py`（walk-forward，共用市場日曆取樣，T+20 到期才更新精度，財報公告遞延防 look-ahead，`--agents` 選擇 Agent，報表含個別 Agent 消融）、`metrics.py`（Brier/ECE）、`portfolio.py`（連續報酬 Rank IC、long/neutral 組合、vs 0050）
- `data_cache/` 刻意納入版控，重跑既有範圍不耗 API 額度

## 最新結果（135 事件，2024-01~2026-05）
| 策略 | Brier | ECE | Hit rate | 累積報酬 | 橫斷面 IC |
|---|---|---|---|---|---|
| 單一 Agent（財報） | 0.2593 | 0.117 | 47.8% | +22.8% | −0.149 |
| 簡單平均（2 Agent） | 0.2556 | 0.061 | 48.8% | +86.5% | −0.170 |
| 精度加權（2 Agent） | 0.2557 | 0.067 | 48.8% | +86.5% | −0.174 |
| 簡單平均（3 Agent） | 0.2538 | 0.054 | 49.4% | +182.2% | −0.154 |
| 精度加權（3 Agent） | 0.2540 | 0.059 | 49.4% | +182.2% | −0.147 |
| 等權持有 5 檔 | — | — | — | +121.3% | — |
| 0050 | — | — | — | +191.7% | — |

- 2 Agent = `reports/finmind_full`（財報 + 新聞），3 Agent = `reports/finmind_macro`（加總經/籌碼），詳見 `docs/phase2_macro_report.md`。
- 基率（20 日含息總報酬為正）54.8%。**所有策略與個別 Agent 的 Brier 都高於 0.25**（永遠猜 50% 的無資訊基準），規則式 Agent 沒有預測力；Hit rate 也低於基率。
- 加入第 3 個 Agent：Brier 與 ECE 都改善（ECE 0.061 → 0.054）。個別 Agent 的 Brier：財報 0.2593、新聞 0.2531、總經 0.2547。
- 3 Agent 精度比仍只有 1.01–1.24，精度加權與簡單平均的訊號完全相同。Synthetic（可靠度分化）下 17/20 seeds 精度加權較佳。
- 3 Agent 組合 +182%（vs 0050 超額 t=0.16）的改善主要來自 2 期（禾伸堂 2026-03 單期 +82%），IC 沒有改善，**不可當成總經 Agent 有效的證據**。
- 2 Agent 報酬層級：落後 0050 與等權持有；單一 Agent 每期超額 t=−2.13（顯著為負）。
- 2026-10-06 的三項修正：
  - 共用市場日曆取樣（國巨 2025-08 停牌造成日期錯位）
  - outcome 改用含息總報酬（`outcome_basis: total_return`）
  - 有方向訊號的信心下限 0.5（`agents/base.py:_build_output`，原始值存 `raw_features.confidence_raw`）。被修正的訊號（財報 9、總經 15）方向命中率僅 33%，舊換算是歪打正著，修正後 Brier 略升
- **LLM 判讀實驗（qwen3:8b，`reports/finmind_llm_qwen3`，詳見 `docs/llm_experiment_report.md`）**：386 次呼叫 0 失敗。LLM 全面劣於規則式（3 Agent 簡單平均 Brier 0.2805 vs 0.2538；財報 0.335、總經 0.405）。主因是嚴重過度自信（信心 ≥ 0.8 的命中率 45–53%），且總經 Agent 135 次**全部看空**（不論數字正負都解讀成利空）。精度比拉大到 1.35–2.63（前提成立），但精度加權仍略輸簡單平均（0.2812 vs 0.2805），因為沒有好的來源可以加重。組合報酬 −11% 到 −16%，顯著輸 0050。新聞 Agent 是唯一勉強有用的（命中率 56%）
- 履歷/對外描述注意：Agent 只有財報、新聞、總經/籌碼三個，不要宣稱含供應鏈訊號；也不要宣稱打敗大盤、有預測力或有選股能力。

## 待辦（依建議順序）
1. **Agent 層級重新校準**（最優先）：walk-forward 只用已到期預測，對每個 Agent 擬合「原始機率 → 實際命中率」（Platt / isotonic / 收縮到 0.5）後再合併。直接修正 LLM 實驗暴露的過度自信，可沿用已快取的 LLM 回應，不需重新推論
2. LLM 延伸：開啟 qwen3 思考模式（`--llm-think true`）重跑總經 Agent，檢驗方向偏誤；或改用雲端 Claude（`--llm-provider anthropic`）
3. Phase 2：供應鏈 Agent（知識圖譜，如 `config/supply_chain_graph.json`）
4. 合併機制升級：對數意見池（技術筆記第 6 節）
5. 規格第 9 節待人工決策：新聞可信度分級、MOPS 爬蟲頻率（horizon 已定為 20 日）
6. 報酬評估可延伸：機率加權部位（而非 bullish 等權）、相對 0050 的 outcome 定義（超額報酬 > 0）
7. 總經/籌碼 Agent 可延伸：半導體庫存週期（免費層無資料）、主力分點、借券等個股籌碼

## 已知限制
每檔僅 27 筆樣本；新聞僅標題；期間與族群單一；地端 LLM 僅測過 qwen3:8b（純 CPU 每次呼叫約 1 分鐘，phi4 約 8 分鐘，未跑完整實驗）；總經分量同一時點各檔相同（對選股無幫助）；總經 Agent 的門檻為經驗值；組合報酬每期之間有 1 個交易日空檔（step 21 > horizon 20）未計入；p 值為常態近似。

## 操作
```bash
.venv/Scripts/python -m pytest tests -q          # 91 tests（Windows；macOS/Linux 用 .venv/bin/python）
# 3 Agent（config 預設）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --output-dir reports/finmind_macro
# LLM 判讀（需 Ollama + qwen3:8b；回應已快取，重跑秒完）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --llm-provider ollama --llm-model qwen3:8b --llm-think false --output-dir reports/finmind_llm_qwen3
# 2 Agent 對照組
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent --output-dir reports/finmind_full
```
