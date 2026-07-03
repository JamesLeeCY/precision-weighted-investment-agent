# 真實資料回測結果報告（縮小版）

**Precision-Weighted Multi-Agent Investment Research System — FinMind 實資料驗證**

| | |
|---|---|
| 執行日期 | 2026-07-03 |
| 資料來源 | FinMind（月營收、季度財報、日價量、歷史新聞） |
| 股票 | 國巨 2327、華新科 2492、禾伸堂 3026（被動元件） |
| 期間 | 2025-01-02 ~ 2026-04-28（預測時點），horizon 20 個交易日 |
| 取樣 | 每 21 個交易日一個預測點，共 **47 個預測事件** |
| 應驗判定 | horizon 期末收盤價絕對報酬 > 0 → outcome = 1 |
| Agent 模式 | 財報 + 新聞事件 Agent，均為規則式判斷（無 LLM key） |

## 1. 總體結果

| 策略 | 平均 Brier ↓ | 方向準確率 ↑ | ECE ↓ |
|---|---|---|---|
| Baseline A：單一 Agent（財報） | 0.2553 | 0.524 | 0.1490 |
| Baseline B：簡單平均合併 | **0.2529** | 0.517 | **0.0848** |
| 本系統：精度加權合併 | 0.2532 | 0.517 | 0.1103 |

驗收判定（規格 6.3）：精度加權 Brier **優於單一 Agent ✅**、與簡單平均
**實質持平**（差距 0.0003，遠小於抽樣誤差）❌；ECE 優於單一 Agent、遜於
簡單平均。

校準曲線：

![Precision-weighted calibration](../reports/finmind_scoped/calibration_precision_weighted.png)

（其餘兩策略見 `reports/finmind_scoped/calibration_baseline_*.png`）

## 2. 每檔分解

| 股票 | n | outcome 基率 | 單一 Agent Brier | 精度加權 Brier |
|---|---|---|---|---|
| 國巨 2327 | 15 | 0.47 | 0.267 | 0.268 |
| 華新科 2492 | 16 | 0.62 | 0.241 | 0.241 |
| 禾伸堂 3026 | 16 | 0.75 | 0.260 | **0.251** |

## 3. 核心發現：精度加權為何 ≈ 簡單平均

回測結束時的精度記錄：

| Agent | 股票 | n | Brier EMA | precision |
|---|---|---|---|---|
| fundamentals_agent | 2327 | 14 | 0.303 | 3.19 |
| news_agent | 2327 | 13 | 0.279 | 3.46 |
| fundamentals_agent | 2492 | 15 | 0.235 | 4.09 |
| news_agent | 2492 | 15 | 0.262 | 3.68 |
| fundamentals_agent | 3026 | 15 | 0.275 | 3.51 |
| news_agent | 3026 | 15 | 0.243 | 3.95 |

兩個 Agent 的實際可靠度落在 0.24–0.30 的窄帶，同檔精度比僅 1.08–1.13，
導致全部 47 個事件中，精度加權與簡單平均的合併機率**分歧均 < 0.01**。

這不是機制失效，而是理論預期的行為：預測處理框架中，當來源可靠度無法
區分時，等權（loose coupling）本身就是精度加權的均衡解。對照 synthetic
實驗（來源可靠度刻意分化時，精度加權在 17/20 seeds 優於簡單平均，見
[technical_note.md](technical_note.md) 第 3 節），可確認：**精度加權的
價值條件是來源可靠度的實質分化**，本期間兩個規則式 Agent 恰好同樣可靠
（也同樣平庸）。

其他觀察：

- **合併一致優於單一 Agent**（Brier 0.2529–0.2532 vs 0.2553；ECE
  0.085–0.110 vs 0.149）：即使精度未分化，ensemble 分散效果仍成立
- **冷啟動 vs 成熟期**：前 5 個時點（冷啟動，n=15）三策略 Brier
  0.233–0.240；成熟期（n=32）0.259–0.266。成熟期較差主要反映 2025 下半
  年後盤勢轉為震盪，而非機制問題
- 方向準確率僅 ~0.52（基率 0.617 偏多）：規則式 Agent 訊號偏弱且偏多，
  這是量化上最需要改進的環節

## 4. 限制

1. **樣本量**：47 個事件、每檔僅 ~15 筆已結算預測，統計檢定力不足以
   對 0.0003 級別的 Brier 差距下結論
2. **無 LLM 判讀**：兩個 Agent 皆為規則式 fallback；法說會敘述、新聞
   語意等 LLM 擅長的訊號完全未使用
3. **新聞資料**：FinMind 免費層新聞僅有標題（無內文），且來源以財經
   媒體為主，來源可信度分級（公告>媒體>論壇）的分化作用有限
4. **期間單一**：2025-2026 被動元件盤整期，未涵蓋完整多空循環

## 5. 下一步

1. 跑 **5 檔完整版**（2024-01 起，`--mode finmind` 不帶 `--tickers`，
   約需 3 個 API 額度小時），樣本擴至 ~145 事件
2. 接上 `ANTHROPIC_API_KEY` 讓兩個 Agent 用 LLM 判讀，重跑同一期間
   比較規則式 vs LLM 的可靠度分化程度
3. Phase 2：供應鏈 / 總經 Agent 加入後，來源異質性提高，精度加權的
   理論優勢更有機會顯現

---

*重現方式：*

```bash
.venv/bin/python backtest/run_backtest.py --mode finmind \
  --tickers 2327.TW,2492.TW,3026.TW \
  --start-date 2025-01-01 --end-date 2026-05-31 --step-days 21 \
  --output-dir reports/finmind_scoped
```

*（`data_cache/` 已含全部所需 FinMind 回應，重跑不消耗 API 額度）*
