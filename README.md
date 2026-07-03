# 精度加權多智能體投資研究系統（MVP）

Precision-Weighted Multi-Agent Investment Research System — 依
`../precision_weighted_investment_agent_spec.md` v0.1 實作。

多個專家 Agent（財報、新聞事件）各自產出帶信心值的判斷，由精度加權仲裁層依各
Agent 的**歷史準確度**（Brier score EMA 的倒數，對應預測處理框架中的
precision）動態加權合成最終投資論點，並以回測管線驗證「精度加權合併」是否優於
「簡單平均合併」。

## 快速開始

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 執行測試（不需任何 API key）
.venv/bin/python -m pytest tests/ -q

# synthetic 模式回測：模擬可靠度不同的 Agent，端到端驗證精度加權機制
.venv/bin/python backtest/run_backtest.py --mode synthetic

# 真實資料回測（需先 cp .env.example .env 並填入 FINMIND_API_TOKEN）
.venv/bin/python backtest/run_backtest.py --mode finmind
```

回測輸出在 `reports/`：`comparison_report.md`（三策略比較 + 驗收判定）、
`calibration_*.png`（校準曲線）、`backtest_results.csv`（逐筆預測）。

## 執行模式

| 模式 | 需要的 key | 說明 |
|---|---|---|
| 測試 / synthetic 回測 | 無 | 完整驗證 schema、合併公式、冷啟動、指標計算 |
| finmind 回測 | `FINMIND_API_TOKEN` | 財報 Agent 與新聞 Agent 以 FinMind 真實資料驅動（規則式判斷） |
| LLM 推論 | 另加 `ANTHROPIC_API_KEY` | Agent 自動改用 Claude 產出 signal/confidence/rationale，失敗時退回規則式 |

LLM 是可插拔設計（`agents/llm_client.py`）：沒有 key 時所有 Agent 使用
確定性的規則式判斷，行為可測試、可重現。

## 專案結構（對應規格第 7 節）

```
config/tickers.yaml        # 股票池（被動元件 5 支）與所有參數
agents/base.py             # AgentOutput schema（規格 3.1 強制介面）
agents/fundamentals_agent.py  # 財報 Agent（規格 3.2）
agents/news_agent.py       # 新聞事件 Agent（規格 3.3）
agents/{supply_chain,macro}_agent.py  # Phase 2 佔位
arbitrator/precision_tracker.py  # 精度記錄：Brier EMA、冷啟動（規格 5.1/5.3）
arbitrator/merge.py        # 合併公式（規格 5.2）
data/fetch_financials.py   # FinMind 財報/價量抓取（含快取與節流）
data/fetch_news.py         # Google News RSS + FinMind 歷史新聞、來源可信度分級
data/vector_store.py       # ChromaDB 封裝（含免依賴 fallback）
backtest/run_backtest.py   # walk-forward 回測、三策略比較（規格 6.3）
backtest/metrics.py        # Brier / 校準曲線 / ECE / 方向準確率（規格 6.1-6.3）
storage/precision_records.json  # 精度記錄持久化
docs/technical_note.md     # M5 技術筆記（理論對應 + 實驗結果）
notebooks/calibration_analysis.ipynb
```

## 關鍵決策記錄

- **股票池**（規格 9.1，使用者指定）：國巨 2327、華新科 2492、禾伸堂 3026、
  凱美 2375、大毅 2478（原名單之奇力新 2456 已於 2021 年底併入國巨下市，故替換）
- **應驗判定**（規格 9.2，使用者指定）：horizon = 20 個交易日，期末收盤價
  絕對報酬 > 0 視為 outcome = 1
- **合併機率**：規格未定義合併輸出的機率形式，本實作採「精度加權線性意見池」
  （與規格 5.2 相同權重，對各 Agent 規格 6.1 機率加權平均），詳見技術筆記
- **uncertainty 公式**：規格 5.2 文字敘述與公式方向相反，以公式為準
  （precision 越集中 → 區間越窄），詳見 `arbitrator/merge.py` docstring

## 實驗結果摘要

見 `docs/technical_note.md`。單行版：synthetic 情境（20 seeds）下精度加權在
17/20 個 seed 的 Brier 優於簡單平均（機制有效），但整體 ensemble 能否勝過
單一校準良好的 Agent 取決於來源間的資訊互補程度——這是誠實記錄的已知限制。
