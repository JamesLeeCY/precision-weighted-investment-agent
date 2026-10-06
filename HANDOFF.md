# HANDOFF — 專案交接狀態

更新日期：2026-10-06

## 一句話
多代理人精度加權投資研究系統（台股被動元件）。MVP（M1–M5）與 5 檔完整真實回測已完成；Phase 2 與 LLM 實驗尚未開始。

## 架構
- `config/tickers.yaml`：股票池與全部參數（horizon、閾值、EMA α、冷啟動門檻）
- `agents/`：`base.py` 介面 `analyze(ticker, as_of_date) → AgentOutput`；`fundamentals_agent`、`news_agent` 已實作（規則式，有 `ANTHROPIC_API_KEY` 時走 LLM，失敗退回規則式）；`supply_chain_agent`、`macro_agent` 僅為 `NotImplementedError` 佔位
- `arbitrator/`：`precision_tracker.py`（Brier EMA、n<5 冷啟動）、`merge.py`（precision×confidence 加權）
- `data/`：FinMind 抓取（快取/節流/額度等待）、RSS 新聞、向量庫封裝
- `backtest/`：`run_backtest.py`（walk-forward，T+20 到期才更新精度，財報公告遞延防 look-ahead）、`metrics.py`
- `data_cache/` 刻意納入版控，重跑既有範圍不耗 API 額度

## 最新結果（reports/finmind_full，135 事件，2024-01~2026-05）
| 策略 | Brier | ECE | Hit rate | Rank IC |
|---|---|---|---|---|
| 單一 Agent（財報） | 0.2565 | 0.116 | 50.0% | −0.007 |
| 簡單平均 | 0.2529 | 0.087 | 51.8% | 0.018 |
| 精度加權 | 0.2530 | 0.093 | 51.8% | 0.015 |

- 基率（20 日報酬為正）55.6%；無資訊 Brier 基準 0.25。Hit rate 低於基率，IC 與 0 無顯著差異（p≈0.87）。IC 以二元結果近似計算。
- 多 Agent 合併優於單一 Agent；精度加權相對簡單平均無增益（兩個規則式 Agent 精度比僅約 1.1）。Synthetic（可靠度分化）下 17/20 seeds 精度加權較佳。
- **尚未有**：報酬層級績效、超額報酬 vs 0050（回測只記錄二元結果，無價格/組合模擬）。
- 履歷/對外描述注意：目前只有財報 + 新聞兩個 Agent，不要宣稱含供應鏈訊號。

## 待辦（依建議順序）
1. LLM 判讀模式可靠度分化實驗（需 `ANTHROPIC_API_KEY`，重跑同期間比較規則式 vs LLM）
2. 報酬層級評估：補 0050 與個股價格，做 long/neutral 組合報酬與超額報酬、連續報酬 IC
3. Phase 2：總經/籌碼 Agent（純量化規則，較易）、供應鏈 Agent（知識圖譜，如 `config/supply_chain_graph.json`）；接入後重跑回測
4. 合併機制升級：對數意見池 / Agent 層級重新校準（技術筆記第 6 節）
5. 規格第 9 節待人工決策：horizon 與結果判定基準、新聞可信度分級、MOPS 爬蟲頻率

## 已知限制
每檔僅 27 筆樣本；新聞僅標題；期間與族群單一；LLM 判讀未使用。

## 操作
```bash
.venv/bin/python -m pytest tests -q          # 53 tests
.venv/bin/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --output-dir reports/finmind_full
```
