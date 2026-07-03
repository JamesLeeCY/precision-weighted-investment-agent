# 精度加權多智能體投資研究系統

**Precision-Weighted Multi-Agent Investment Research System**

![Python](https://img.shields.io/badge/python-3.11+-blue)
![Tests](https://img.shields.io/badge/tests-53%20passed-brightgreen)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

借用神經科學**預測處理框架（predictive processing）**中的 precision
weighting 概念建構的多智能體投資研究系統：多個專家 Agent（財報、新聞事件）
各自產出帶信心值的判斷，仲裁層依各 Agent 的**歷史準確度**（Brier score
EMA 的倒數，即「精度」）動態加權合成投資論點——可靠度越高的來源權重越大，
系統從均等權重（loose coupling）隨證據累積收斂到以可靠來源為主導
（tight coupling）。鎖定台股 AI 供應鏈之被動元件族群。

```
 財報 Agent          新聞事件 Agent        供應鏈/總經 Agent
 (規則式/LLM)        (規則式/LLM)          (Phase 2)
      │                   │                   │
      └───────────┬───────┴───────────────────┘
                  ▼
     精度加權仲裁層  final_score = Σ(precisionᵢ·confidenceᵢ·sᵢ) / Σ(precisionᵢ·confidenceᵢ)
                  ▼
     投資論點 + 不確定性區間 + evidence trace
                  ▼ (T+20 交易日後)
     回測評估 → Brier score → 更新各 Agent 精度（EMA）→ 回饋仲裁層
```

## 核心結果

**真實資料回測**（FinMind，3 檔被動元件 × 2025-01~2026-05，47 個預測事件，
詳見[完整報告](docs/finmind_scoped_report.md)）：

| 策略 | 平均 Brier ↓ | ECE ↓ |
|---|---|---|
| Baseline A：單一 Agent（財報） | 0.2553 | 0.1490 |
| Baseline B：簡單平均合併 | **0.2529** | **0.0848** |
| 本系統：精度加權合併 | 0.2532 | 0.1103 |

**Synthetic 機制驗證**（20 seeds，來源可靠度刻意分化，詳見
[技術筆記](docs/technical_note.md)）：精度加權在 **17/20 seeds** 的
Brier 優於簡單平均。

兩組實驗合起來的結論：(1) 多 Agent 合併穩定優於單一 Agent；(2) 精度加權
相對簡單平均的增益，**只在來源可靠度實質分化時顯現**——真實回測中兩個
規則式 Agent 恰好同樣可靠（精度比僅 1.1），精度加權因此收斂到等權，這
本身是理論的正確行為而非機制失效。誠實的負結果與條件分析是本專案的
主要研究產出之一。

![Calibration](reports/finmind_scoped/calibration_precision_weighted.png)

## 快速開始

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip

# 單元測試（不需任何 API key）
.venv/bin/python -m pytest tests -q

# Synthetic 回測：模擬可靠度不同的 Agent，驗證精度加權機制
.venv/bin/python backtest/run_backtest.py --mode synthetic

# 真實資料回測（需 FinMind token：cp .env.example .env 並填入）
.venv/bin/python backtest/run_backtest.py --mode finmind \
    --tickers 2327.TW,2492.TW --start-date 2025-01-01 --step-days 21
```

輸出至 `reports/<mode>/`：比較報表（`comparison_report.md`）、校準曲線
（`calibration_*.png`）、逐筆預測（`backtest_results.csv`）。

### 執行模式與 API key

| 模式 | 需要的 key | 說明 |
|---|---|---|
| 測試 / synthetic | 無 | 完整驗證 schema、合併公式、冷啟動、指標 |
| finmind 回測 | `FINMIND_API_TOKEN`（免費註冊） | 兩個 Agent 以真實財報/新聞驅動（規則式判斷）。免費額度 600 req/hr，客戶端內建逐日快取與額度自動等待；`data_cache/` 已隨 repo 提供，重跑既有範圍不消耗額度 |
| + LLM 判讀 | 另加 `ANTHROPIC_API_KEY` | Agent 自動改用 Claude 產出 signal/confidence/rationale，失敗時退回規則式 |

## 系統設計

- **Agent 共同介面**（[agents/base.py](agents/base.py)）：`analyze(ticker, as_of_date) → AgentOutput`，
  輸出含 signal（bullish/bearish/neutral）、confidence（單次判斷的主觀信心）、
  rationale、evidence_refs、raw_features
- **precision ≠ confidence**：confidence 是 Agent 對單次判斷的信心；
  precision 是仲裁層追蹤的歷史可靠度 `1/(brier_ema + ε)`。合併權重 =
  兩者相乘（「這次訊號多強 × 這個來源多可信」）
- **冷啟動**（[arbitrator/precision_tracker.py](arbitrator/precision_tracker.py)）：
  n < 5 的 Agent 精度取成熟記錄均值，無任何歷史時全體等權
- **走時序回測**（[backtest/run_backtest.py](backtest/run_backtest.py)）：
  精度只在 horizon 到期後更新；財報設公告遞延（月營收 40 天、季報 75 天），
  杜絕 look-ahead
- **評估**（[backtest/metrics.py](backtest/metrics.py)）：Brier score、
  Reliability Diagram、ECE、方向準確率；驗收 = 精度加權 vs 單一 Agent vs
  簡單平均的三方比較

## 專案結構

```
config/tickers.yaml     股票池與全部參數（horizon、閾值、EMA α、冷啟動門檻）
agents/                 Agent 基底 + 財報/新聞 Agent（LLM 可插拔）+ Phase 2 佔位
arbitrator/             精度追蹤（Brier EMA）+ 合併公式
data/                   FinMind 抓取（快取/節流/額度等待）、RSS 新聞、向量庫封裝
backtest/               walk-forward 回測 + 評估指標
tests/                  53 個單元測試
reports/                synthetic / finmind_preliminary / finmind_scoped 結果
docs/                   規格、技術筆記、回測報告
notebooks/              校準分析 notebook
```

## 文件

- [技術規格](docs/spec.md) — 系統的原始設計規格（v0.1）
- [技術筆記](docs/technical_note.md) — 預測處理框架的理論對應、synthetic
  實驗、誠實分析（M5 交付物）
- [真實資料回測報告](docs/finmind_scoped_report.md) — FinMind 縮小版結果
  與逐項解讀

## Roadmap

- [x] MVP：財報 + 新聞 Agent、精度加權仲裁、回測管線（M1–M5）
- [ ] 5 檔完整版真實回測（2024-01 起）
- [ ] LLM 判讀模式的可靠度分化實驗
- [ ] Phase 2：供應鏈 Agent（知識圖譜）、總經/籌碼 Agent
- [ ] 對數意見池 / Agent 層級重新校準（見技術筆記第 6 節）

## 免責聲明

本專案為研究與教育目的之技術實作，所有輸出（signal、confidence、投資論點）
均為演算法產物，**不構成任何投資建議**。歷史回測結果不代表未來績效。

## License

[MIT](LICENSE)
