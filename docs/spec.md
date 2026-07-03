> 本文件為專案的原始設計規格（v0.1），供實作對照。實作過程中的規格詮釋
> 與偏離（uncertainty 公式、合併機率定義、股票池替換）記錄於
> [technical_note.md](technical_note.md) 與 README「系統設計」一節。

# 技術規格文件：精度加權多智能體投資研究系統
# (Precision-Weighted Multi-Agent Investment Research System)

版本：v0.1 (MVP scope)
文件目的：本文件供 AI coding agent（如 Claude Code）讀取後，依此規格建立專案骨架、實作各模組並撰寫測試。所有介面定義（函式簽名、JSON schema）視為強制規格，非建議。

---

## 1. 專案目標

建立一個多智能體（multi-agent）投資研究系統，鎖定台股 AI 供應鏈個股（被動元件、PMIC/電源半導體、導線架等）。系統由多個「專家 Agent」各自產出帶信心值的判斷，再由一個「精度加權仲裁層」依各 Agent 的**歷史準確度**動態調整其權重，合成最終投資論點。

核心設計理念：借用神經科學「預測處理框架」中的 precision weighting（精度加權信念更新）概念——訊號來源的歷史可靠度（precision，即預測誤差變異數的倒數）決定其在最終信念更新中的權重，可靠度越高的來源，權重越大；系統初期（無歷史記錄）採均等權重（loose coupling），隨著回測資料累積逐漸收斂到以可靠 Agent 為主導（tight coupling）。

MVP 範圍：先實作 2 個專家 Agent（財報 Agent + 新聞事件 Agent）+ 精度加權仲裁層 + 回測評估管線，驗證「精度加權合併」是否優於「簡單平均合併」。之後再擴充供應鏈 Agent、總經 Agent。

---

## 2. 系統架構

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ 財報 Agent   │  │ 供應鏈 Agent │  │ 新聞 Agent   │  │ 總經 Agent   │
│ (MVP: 實作)  │  │ (Phase 2)    │  │ (MVP: 實作)  │  │ (Phase 2)    │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │                │
       └────────────────┴────────┬───────┴────────────────┘
                                  ▼
                   ┌───────────────────────────┐
                   │   精度加權仲裁層             │
                   │ Precision-Weighted         │
                   │ Arbitrator                 │
                   └──────────────┬─────────────┘
                                  ▼
                   ┌───────────────────────────┐
                   │  投資論點輸出                │
                   │ Thesis + Confidence Interval│
                   │ + Evidence Trace           │
                   └──────────────┬─────────────┘
                                  │
                                  ▼ (T+N 天後)
                   ┌───────────────────────────┐
                   │  回測評估管線                │
                   │ Backtest & Calibration     │
                   └──────────────┬─────────────┘
                                  │ 更新各 Agent 精度記錄
                                  └────────────────► (回饋至仲裁層)
```

---

## 3. Agent 規格

### 3.1 共同介面（所有 Agent 必須遵守）

每個 Agent 是一個函式（或 class method），輸入 `ticker` + `as_of_date`，輸出符合以下 JSON schema 的結構：

```json
{
  "agent_id": "string, 例如 fundamentals_agent",
  "ticker": "string, 例如 2327.TW",
  "as_of_date": "YYYY-MM-DD",
  "signal": "bullish | bearish | neutral",
  "confidence": "float, 0.0-1.0，Agent 對自己判斷的主觀信心",
  "horizon_days": "int，判斷的預期應驗時間窗（例如 20 個交易日）",
  "rationale": "string，簡短理由（<=200字，供人工檢視與 evidence trace 使用）",
  "evidence_refs": ["string array，引用的資料來源 ID 或段落索引"],
  "raw_features": "object，該 Agent 用於判斷的關鍵特徵值（供除錯與後續分析用）"
}
```

`confidence` 是 Agent 對自己這次判斷的主觀信心（by LLM self-assessment 或基於特徵完整度的規則），**不等於**精度加權仲裁層使用的「歷史精度」——兩者是不同的量，詳見第 5 節。

### 3.2 財報 Agent (fundamentals_agent) — MVP 必做

- 輸入：ticker、財報公告期間
- 資料處理：解析損益表、資產負債表關鍵科目（營收 YoY/MoM、毛利率、存貨週轉天數、應收帳款天數），計算趨勢特徵（例如近 4 季斜率）
- LLM 任務：將財報敘述性揭露（如法說會 Q&A 逐字稿摘要）與數字特徵一併送入 context，要求模型產出 signal + confidence + rationale
- Prompt 設計要求：明確要求模型區分「營運數字顯示的訊號」與「管理層敘述顯示的訊號」，若兩者矛盾需在 rationale 中說明並降低 confidence

### 3.3 新聞事件 Agent (news_agent) — MVP 必做

- 輸入：ticker、時間窗（預設近 14 天）
- 資料處理：RAG 檢索相關新聞與重大訊息公告，去重、按時間排序
- LLM 任務：抽取事件類型（例如：擴產、客戶認證、法人調升目標價、匯率影響）與情緒方向，產出 signal + confidence
- 特別要求：對來源可信度分級（公司公告 > 財經媒體 > 論壇/社群），並反映在 confidence 計算中

### 3.4 供應鏈 Agent (supply_chain_agent) — Phase 2

- 維護一個簡化知識圖譜（客戶-供應商-替代品關係），初期可用手動整理的 CSV/JSON 起步，之後再考慮自動化擷取
- LLM 任務：給定上游/下游事件（例如某 hyperscaler 資本支出上調），推論對目標個股的傳導效應與時間遞延

### 3.5 總經/籌碼 Agent (macro_agent) — Phase 2

- 輸入：利率、匯率、半導體庫存週期指標、三大法人買賣超
- 可先用純量化規則（非 LLM）產生 signal，之後再視需要加入 LLM 解讀層

---

## 4. 資料來源與 API 選型

| 用途 | 建議來源 | 存取方式 | 備註 |
|---|---|---|---|
| 財報/重大訊息 | 公開資訊觀測站 (MOPS) | 網頁爬取或現成套件（如 `twstock`、`FinMind`） | 注意爬蟲需遵守 MOPS 使用條款，控制請求頻率 |
| 盤後價量、法人買賣超 | 證交所 OpenAPI / FinMind API | REST API | FinMind 提供整理過的歷史資料，優先使用以降低爬蟲維護成本 |
| 新聞 | 財經新聞 RSS（如各媒體財經版 RSS）、Google News RSS | RSS 解析 | 初期不需付費新聞 API，RSS 足夠驗證 MVP |
| 法說會逐字稿 | 公司投資人關係網站、MOPS 重大訊息 | PDF 下載 + 文字擷取 | 需要 PDF 轉文字流程，可用 `pdfplumber` |
| LLM 推論 | Anthropic API | `claude-sonnet-4-6`（一般推論任務）；複雜綜合判斷可用更高階模型 | 所有 Agent 與仲裁層皆呼叫此 API |
| 向量檢索 (RAG) | ChromaDB（本地）或 Qdrant | Python SDK | MVP 用 ChromaDB 即可，免額外部署成本 |
| Embedding | Voyage AI embeddings 或 Anthropic 建議的 embedding 供應商 | REST API | 需另外申請 API key |

**環境變數需求**（`.env` 檔案）：
```
ANTHROPIC_API_KEY=
VOYAGE_API_KEY=
FINMIND_API_TOKEN=
```

---

## 5. 精度加權仲裁層（核心演算法）

### 5.1 精度的定義與追蹤

對每個 Agent `a`、每支個股 `ticker`，維護一個精度記錄：

```json
{
  "agent_id": "fundamentals_agent",
  "ticker": "2327.TW",
  "n_predictions": 12,
  "brier_score_ema": 0.18,
  "precision": 5.56
}
```

- `brier_score_ema`：該 Agent 在該股票上的 Brier score 指數移動平均（見第 6 節定義），值越低代表校準越好
- `precision`：定義為 `1 / (brier_score_ema + epsilon)`，epsilon 取 0.01 避免除零。此值即對應預測處理框架中的「精度」（預測誤差變異數的倒數）
- 冷啟動規則：`n_predictions < 5` 時，該 Agent 精度強制設為所有已知 Agent 精度的平均值（即 loose coupling，尚未有足夠證據前不給予特殊信任）

### 5.2 合併公式

給定 N 個 Agent 對同一 ticker 的判斷，將 signal 轉換為數值 `s ∈ {-1, 0, +1}`（bearish/neutral/bullish），仲裁層計算加權平均：

```
final_score = Σ(precision_i * confidence_i * s_i) / Σ(precision_i * confidence_i)
```

- 最終判斷：`final_score > 0.3` → bullish；`< -0.3` → bearish；否則 neutral
- 不確定性區間：用加權變異數估計信心區間寬度，`precision` 越集中在少數高權重 Agent，區間應越窄（實作時可用 bootstrap 或簡化的加權標準誤公式，MVP 階段可先用簡化版：`uncertainty = 1 - (max_precision_i / Σprecision_i)`，數值越接近 1 代表越依賴單一來源、越不穩定）

### 5.3 精度更新時機

回測管線在 `as_of_date + horizon_days` 後，比對該 Agent 判斷方向與實際股價/財務指標變化方向，計算單次 Brier score，並以指數移動平均（EMA，建議 alpha=0.2）更新 `brier_score_ema`。

---

## 6. 評估指標定義

### 6.1 Brier score（校準度）

對單次預測：將 signal 轉為機率形式 `p`（bullish → confidence 本身視為看多機率，bearish → 1-confidence，neutral → 0.5），實際結果 `o ∈ {0,1}`（例如以 horizon_days 後報酬是否為正定義），

```
brier = (p - o)^2
```

### 6.2 校準曲線（Reliability Diagram）

將所有預測依 confidence 分成 10 個桶（0-0.1, 0.1-0.2, ...），計算每桶的平均 confidence 與實際命中率，畫出校準曲線，理想情況應貼近對角線。此為系統驗收的核心視覺化產出，不只是數字。

### 6.3 系統層級評估（比較基準）

MVP 完成後，需比較三種合併策略在同一測試集（回測期間、同一組個股）上的表現：

1. **Baseline A**：單一 Agent（例如只用財報 Agent）
2. **Baseline B**：簡單平均合併（不做精度加權）
3. **本系統**：精度加權合併

評估指標：
- 平均 Brier score（越低越好）
- 方向準確率（directional accuracy，signal 方向與實際報酬方向一致的比例）
- 校準曲線的偏離程度（ECE, Expected Calibration Error）

驗收標準（MVP 通過門檻）：精度加權合併的 Brier score 需優於 Baseline A 與 Baseline B，且 ECE 不劣於兩者。若未達標，需在報告中誠實記錄並分析原因（例如冷啟動樣本不足），這本身也是可交付的研究產出。

---

## 7. 專案結構

```
investment-agent/
├── .env.example
├── requirements.txt
├── config/
│   └── tickers.yaml          # MVP 測試股票池，建議 5-10 支被動元件/PMIC 個股
├── agents/
│   ├── base.py                # Agent 抽象基底類別，定義共同輸出 schema
│   ├── fundamentals_agent.py
│   ├── news_agent.py
│   ├── supply_chain_agent.py  # Phase 2
│   └── macro_agent.py         # Phase 2
├── arbitrator/
│   ├── precision_tracker.py   # 維護各 Agent 精度記錄（讀寫 storage）
│   └── merge.py                # 實作第 5.2 節合併公式
├── data/
│   ├── fetch_financials.py    # MOPS / FinMind 抓取邏輯
│   ├── fetch_news.py          # RSS 抓取與解析
│   └── vector_store.py         # ChromaDB 封裝
├── backtest/
│   ├── run_backtest.py        # 回測主流程
│   └── metrics.py              # Brier score、校準曲線、ECE 計算
├── storage/
│   └── precision_records.json # 或改用 SQLite，儲存各 Agent 歷史精度
├── notebooks/
│   └── calibration_analysis.ipynb
└── tests/
    ├── test_agents.py
    ├── test_arbitrator.py
    └── test_metrics.py
```

---

## 8. 開發里程碑

| 階段 | 內容 | 驗收標準 |
|---|---|---|
| M1 | 建立專案骨架、資料抓取模組（財報+新聞）、Agent 基底類別 | 能對單一 ticker 跑出符合 schema 的 Agent 輸出 |
| M2 | 實作財報 Agent、新聞 Agent | 兩個 Agent 對測試股票池皆能產出合理 signal/confidence，人工抽查 rationale 品質 |
| M3 | 實作精度加權仲裁層（冷啟動用均等權重） | 合併輸出格式正確，unit test 覆蓋合併公式 |
| M4 | 建立回測管線與評估指標 | 能產出第 6.3 節三種策略的比較報表與校準曲線圖 |
| M5 | 分析結果、撰寫技術筆記（含預測處理框架對應說明） | 完成一份 1-2 頁技術筆記，說明 precision weighting 的理論對應與實驗結果 |
| M6 (Phase 2) | 擴充供應鏈 Agent、總經 Agent | 四個 Agent 皆納入精度加權合併，重跑回測比較 |

---

## 9. 已知限制與待決事項（需人工決策，Agent 不應自行假設）

1. 測試股票池的具體名單需人工指定（建議從使用者已熟悉的被動元件/PMIC 個股中選 5-10 支）
2. 回測的 `horizon_days` 與「結果是否為正」的判定基準（用股價報酬？用財報後的財測修正方向？）需人工確認，會直接影響 Brier score 的意義
3. 新聞來源的可信度分級規則目前為簡化假設，需視實際資料品質調整
4. MOPS 爬蟲需確認請求頻率限制與使用條款，避免被封鎖
