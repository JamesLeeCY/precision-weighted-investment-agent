# 策略點子研究（strategy-scout）

從財金文獻、量化部落格與台灣論壇找策略靈感，產出「點子卡＋事前固定的檢定計畫」，由使用者決定要測哪些。
分工比照 WorldQuant 的研究迴圈：判斷由 Claude Code 子代理做，工具負責抓資料與比對。

```
選題 → 搜尋來源 → 萃取假設 → 查已測（去重） → 查資料可得性 → 設計檢定 → 排序 → 點子卡 → 使用者確認 → 回測（analysis/）→ 前瞻（forward/）
```

| 檔案 | 用途 |
|---|---|
| [`.claude/agents/strategy-scout.md`](../.claude/agents/strategy-scout.md) | 子代理定義（流程、台股限制、評分規則、點子卡格式） |
| [`scout.py`](scout.py) | 工具：`lit`（OpenAlex＋arXiv）、`blogs`（量化部落格 RSS）、`ptt`（PTT 搜尋）、`dedup`（比對已測點子）、`data`（資料盤點與 FinMind 試抓）、`card`（寫點子卡） |
| [`tested_ideas.yaml`](tested_ideas.yaml) | 已測過的點子與結論（去重用；**每完成一項研究就要補上**） |
| [`data_catalog.yaml`](data_catalog.yaml) | 可用資料盤點（免費／付費／需整理、是否已使用） |
| `ideas/`、`ideas.csv` | 點子卡與索引（狀態：待確認 → 已選 → 已測／放棄） |

## 使用方式

在 Claude Code 對話中說，例如：

- 「用 strategy-scout 找跟法人持股有關的策略點子」
- 「strategy-scout：看看最近量化部落格有什麼可以在台股測的」
- 「找 PTT 上關於除權息的交易慣例，評估能不能測」

子代理會回報依優先度排序的點子卡清單；選好要測的卡後，再請 Claude Code 依卡上的檢定計畫寫回測。
研究點子，非投資建議。
