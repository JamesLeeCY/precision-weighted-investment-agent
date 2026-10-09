# HANDOFF — 專案交接狀態

更新日期：2026-10-06

## 一句話
多代理人精度加權投資研究系統（台股被動元件，另有 41 檔 AI 供應鏈擴大股票池）。MVP（M1–M5）、5 檔完整真實回測、報酬層級評估、Phase 2 全部 Agent、地端 LLM 判讀實驗（qwen3:8b）、Agent 層級重新校準、新聞內文抓取、供應鏈年報修訂與長期驗證、41 檔擴大股票池、連續輸出模式、271 檔無選股偏誤股票池已完成。整體結論：精度加權機制在 synthetic 中成立；真實資料上唯一可靠的是財報 Agent 的產業內排序能力（小幅，IC 約 0.02–0.04），其餘 Agent 沒有預測力。

## 架構
- `config/tickers.yaml`：股票池與全部參數（horizon、閾值、EMA α、冷啟動門檻、基準 0050、交易成本、`outcome_basis`、`agents` 清單、`macro` 窗口）
- `agents/llm_client.py`：provider 可選 anthropic / ollama（地端），JSON schema 結構化輸出、temperature 0、回應快取於 `data_cache/llm/`（納入版控，重跑不需重新推論）
- `agents/`：`base.py` 介面 `analyze(ticker, as_of_date) → AgentOutput`，以及共用的規則評分 `score_components`；`fundamentals_agent`、`news_agent`、`macro_agent` 已實作（規則式；LLM 可用時改用 LLM 判讀，失敗退回規則式；`raw_features.llm_used` 標示是否實際採用 LLM）、`supply_chain_agent`（知識圖譜 `config/supply_chain_graph.json`：2026-10-08 依 2024 年度年報修訂，每條邊標註出處；下游節點是需求代理、非確認客戶——五家年報皆無占營收 10% 以上的外部客戶；v1 另存 `supply_chain_graph_v1.json`）。`news_agent` 可選 `content_fetcher` 於檢索後補新聞內文
- `arbitrator/`：`precision_tracker.py`（Brier EMA、n<5 冷啟動）、`merge.py`（precision×confidence 加權）、`calibration.py`（Agent 層級收縮校準 p' = σ(a·logit p)，a ∈ [0,1]，walk-forward 擬合）
- `data/fetch_article.py`：新聞內文抓取（遵守 robots.txt、同網域 ≥ 1 秒）；快取 `article_cache/` **不納入版控**（著作權）；Google News 轉址連結無法解析
- `data/fetch_supply_chain.py`：圖譜載入與關聯公司的含息還原股價、月營收
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
- **新聞內文（`reports/finmind_news_content`，詳見 `docs/news_content_and_supply_chain_report.md`）**：覆蓋率 36%（371/1,033；Google News 轉址 61% 無法解析）；取得的內文 43% 來自 CMoney。規則式新聞 Agent 加內文後變差（Brier 0.2531 → 0.2640，命中率 47% → 39%），因為關鍵字被長文中的固定段落（法人買賣超、漲價）帶偏
- **供應鏈 Agent（`reports/finmind_supply_chain`，4 Agent、只有標題，v1 圖譜）**：Brier 0.2656（最差，偏多：69 多 / 4 空），樣本內橫斷面 IC +0.160（t = 1.71）。4 Agent 簡單平均累積報酬 +59%（多持股的多頭效果，非判讀能力）
- **供應鏈訊號驗證（`docs/supply_chain_validation_report.md`）**：**訊號不穩定**。2019–2026 長期回測中，2019–2023 樣本外 IC 為負（v1 −0.070、v2 −0.128）；對所有 21 種取樣起點檢查，原本的 +0.160 是最大值（範圍 −0.147 ~ +0.160）。Agent 內部的連續分數在 2024–2026 對所有起點都為正（+0.11），但 2019–2023 反轉為負（−0.07，0/21 起點為正）→ 行情依賴（AI 伺服器熱潮），非穩定訊號。依年報修訂的 v2 圖譜沒有改變結論
- **擴大股票池（`reports/finmind_expanded`，`config/tickers_expanded.yaml`，詳見 `docs/expanded_universe_report.md`）**：41 檔（被動元件 5、半導體設備 9、功率元件 9、AI 伺服器 6、散熱 3、PCB/CCL 3、電源 2、連接器 2、ASIC 2）× 2019–2026，財報 + 總經/籌碼 + 供應鏈（不含新聞）。結果：三個 Agent 的產業內 IC 都接近 0 或為負；唯一兩期一致的是財報 Agent **連續分數**的產業內 IC（+0.022 / +0.028，單一起點 t 中位數約 0.8，不顯著），轉成看多機率後幾乎消失（門檻化丟資訊）。供應鏈 Agent 跨產業為正、產業內為負 → 族群輪動訊號，非選股。沒有策略顯著贏過等權持有同一股票池；校準後策略平均只持 0.8 檔（機率被收縮到 0.5 附近，很少超過 0.55 門檻）。所有策略 Brier 都比「永遠預測基率 57.6%」（0.2442）差
- **連續輸出模式（`--agent-output continuous`，詳見 `docs/continuous_output_report.md`）**：規則式 Agent 以 p = σ(ln3 · score · 證據強度) 直接輸出機率（`agents/base.py:continuous_judgement`；證據強度 = 資料覆蓋率，新聞為來源可信度 × 事件數），signal / confidence 由 p 換回、符合規格。預設仍為門檻模式（已驗證既有報告逐筆可重現）。41 檔結果：財報 Agent 產業內 IC +0.022 / +0.028（門檻模式 +0.002 / +0.017）；簡單平均合併相對等權持有每期 +1.31%（t 2.21，扣成本），2019–2023 為 +1.58%（未扣成本，21/21 起點為正，選股 +0.97%、產業配置 +0.72%），2024–2026 約 0。5 檔 × 2024–2026 含新聞沒有改善（合併 Brier 0.2530 → 0.2564）。在選股偏誤、多重比較、兩期不一致下仍是未經證實的弱訊號
- **無選股偏誤股票池（`reports/finmind_pit`，`config/tickers_pit.yaml`，詳見 `docs/pit_universe_report.md`）**：`data/universe.py` 從 931 檔電子相關上市櫃股票（含 34 檔 2019 年後下市）中，每年第一個交易日依前 60 日平均成交金額取前 100 檔（`config/universe_pit_membership.csv`，271 檔不重複，與 41 檔每年只重疊 16–23 檔）；回測支援逐年成員（`universe_membership`）。等權持有 +538%，與 0050 +566% 相當 → 選股偏誤已移除。**財報 Agent 產業內 IC 2019–2026 為 +0.029（t 2.16，55/85 期為正）；每日檢驗 2019–2023 +0.019、2024–2026 +0.044，21/21 起點全為正**。單獨持有財報 Agent 看多股票，扣成本後相對等權每期 +0.26%（t 1.90）；起點檢驗（未扣成本）+0.44% / +0.33%，21/21 為正，主要來自產業內選股。合併策略 −0.44%（41 檔上的 +1.31% 沒有重現）；供應鏈 Agent 2024–2026 跨產業 IC 0/21 為正。供應鏈的產業內 IC 在此股票池無意義（圖譜全為產業預設）。所有策略 Brier 仍不如基率預測（0.2489）
- **data_cache 版控政策（2026-10-09 起）**：無偏誤股票池新增約 3,000 個 FinMind 快取檔（約 1.2 GB），不再納入版控（`.gitignore`：`data_cache/*`，但 `data_cache/llm/` 與既有已追蹤檔案仍版控）。重現 `finmind_pit` 需重新下載（約 4–5 小時 FinMind 額度，客戶端會自動等待額度）
- **選股偏誤**：擴大股票池是 2026 年事後挑選的 AI 贏家（等權持有 +1,493% vs 0050 +566%），絕對報酬與跨產業 IC 都會被高估；以產業內 IC 與相對等權持有為主要指標
- 擴大圖譜 `config/supply_chain_graph_expanded.json`：36 檔新股票逐一讀 2024 年報，只有辛耘點名客戶（台積電 21.02%）；多數以代號揭露。154 條邊中 111 條為產業預設、9 條年報文字、9 條推論、1 條年報確認。新增美股代理（NVIDIA、Microsoft、Amazon、Alphabet、Meta、Applied Materials；以 SPY 計算超額報酬）
- **資料修正**：FinMind 有收盤價為 0 的資料列（國巨 2019-11-12、2021-06-30，凱美 2019-03-13，鴻海 2025-07-30），已在資料層視為缺值；重跑 9 份報表，只有 `finmind_supply_chain` 的 5 個事件受影響
- **LLM 判讀有內文的新聞（`reports/finmind_llm_qwen3_content`）**：qwen3:8b、`--llm-num-thread 2`，39 次新呼叫約 3 小時（CPU 約占 16–17%）。內文讓 LLM 新聞判讀也變差（Brier 0.2718 → 0.2877；輸出有變的 20 個事件命中率 66.7% → 44.4%，信心反而更高；校準後係數 0.04）。取得的內文偏向 CMoney 自動文章，主流媒體內文拿不到
- 目前 config 預設為 4 個 Agent；3 Agent 對照組需加 `--agents fundamentals_agent,news_agent,macro_agent`
- FinMind 客戶端：網路錯誤會退避重試（30s → 600s），最終錯誤訊息不含帶 token 的網址
- 履歷/對外描述注意：Agent 有財報、新聞、總經/籌碼、供應鏈四個，供應鏈圖譜是需求代理而非確認的客戶關係；也不要宣稱打敗大盤或有預測力（Brier 都不如基率）。可宣稱的是：完整的 walk-forward 評估框架、精度加權機制在 synthetic 中驗證有效、對真實資料負結果的誠實分析，以及財報 Agent 在無選股偏誤股票池上有小幅、穩健的產業內排序能力（IC 約 0.02–0.04）。

## 待辦（依建議順序）
1. **合併只放有產業內技能的 Agent，或依產業內 IC 加權**（最優先）：目前精度以 Brier 衡量，各 Agent 都接近 0.25、分辨不出排序能力；在無偏誤股票池上，總經與供應鏈 Agent 稀釋了財報 Agent（合併 −0.44%/期 vs 財報單獨 +0.26%/期）
2. **前瞻驗證**：凍結目前的規則與參數，從 2026-06 起逐月記錄預測，累積真正的樣本外結果
3. **以財報 Agent 為核心的產業中性組合**：產業內排序、產業內多空（評估腳本已有 `analysis/agent_ic.py`、`analysis/phase_robustness_agents.py`、`analysis/portfolio_phase_robustness.py`）
4. **提升其他 Agent 的資訊量**：新聞內文已試過（規則式與 LLM 都變差），若再試應先提升來源品質（主流媒體內文）；更強的 LLM（雲端 Claude）或 qwen3 思考模式
5. 各 Agent 可個別指定模型（目前所有 Agent 共用同一份 llm 設定）
6. 合併機率的中性稀釋（規格 5.2 修訂的代價）：讓中性 Agent 棄權，或改用對數意見池
7. 合併後再校準：線性池平均已校準機率會信心不足
8. 規格第 9 節待人工決策：新聞可信度分級、MOPS 爬蟲頻率（horizon 已定為 20 日）
9. 報酬評估可延伸：機率加權部位、相對 0050 的 outcome 定義（超額報酬 > 0）
10. 總經/籌碼 Agent 可延伸：半導體庫存週期（免費層無資料）、主力分點、借券等個股籌碼

## 已知限制
每檔僅 27 筆樣本；新聞僅標題；期間與族群單一；地端 LLM 僅測過 qwen3:8b（純 CPU；2 執行緒時長新聞 prompt 每次約 5–7 分鐘）；phi4 未跑完整實驗（3 核心估計完整 386 次呼叫約 61 小時，主要卡在冗長輸出）；總經分量同一時點各檔相同（對選股無幫助）；總經 Agent 的門檻為經驗值；組合報酬每期之間有 1 個交易日空檔（step 21 > horizon 20）未計入；p 值為常態近似。

## 操作
```bash
.venv/Scripts/python -m pytest tests -q          # 136 tests（Windows；macOS/Linux 用 .venv/bin/python）
# 3 Agent（config 預設）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent,macro_agent --output-dir reports/finmind_macro
# LLM 判讀（需 Ollama + qwen3:8b；回應已快取，重跑秒完）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent,macro_agent --llm-provider ollama --llm-model qwen3:8b --llm-think false --output-dir reports/finmind_llm_qwen3
# 4 Agent（含供應鏈，v1 圖譜）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --supply-chain-graph config/supply_chain_graph_v1.json --output-dir reports/finmind_supply_chain
# 3 Agent + 新聞內文（需連網；內文快取只存在本機）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent,macro_agent --news-content --output-dir reports/finmind_news_content
# 3 Agent LLM + 新聞內文（回應已快取；內文快取只存在本機，需先以 --news-content 抓取）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent,macro_agent --news-content-offline --llm-provider ollama --llm-model qwen3:8b --llm-think false --llm-num-thread 2 --output-dir reports/finmind_llm_qwen3_content
# 供應鏈驗證：樣本內 v2（4 Agent）與 2019–2026 長期（只有供應鏈 Agent；v1 加 --supply-chain-graph config/supply_chain_graph_v1.json）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --output-dir reports/finmind_supply_chain_v2
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2019-01-01 --end-date 2026-05-31 --step-days 21 --agents supply_chain_agent --output-dir reports/finmind_supply_chain_long_v2
.venv/Scripts/python analysis/phase_robustness.py config/supply_chain_graph.json phase_v2.csv
# 擴大股票池（41 檔 × 2019–2026，不含新聞）與分析
.venv/Scripts/python backtest/run_backtest.py --mode finmind --config config/tickers_expanded.yaml --output-dir reports/finmind_expanded
.venv/Scripts/python analysis/agent_ic.py reports/finmind_expanded/backtest_results.csv config/tickers_expanded.yaml
.venv/Scripts/python analysis/phase_robustness_agents.py config/tickers_expanded.yaml daily_expanded.csv
# 連續輸出模式（41 檔、5 檔）與組合穩健性
.venv/Scripts/python backtest/run_backtest.py --mode finmind --config config/tickers_expanded.yaml --agent-output continuous --output-dir reports/finmind_expanded_continuous
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent,macro_agent --agent-output continuous --output-dir reports/finmind_macro_continuous
.venv/Scripts/python analysis/portfolio_phase_robustness.py daily_expanded.csv config/tickers_expanded.yaml
# 無選股偏誤股票池（成員表已存；FinMind 快取不在版控，首次需重新下載）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --config config/tickers_pit.yaml --output-dir reports/finmind_pit
.venv/Scripts/python analysis/agent_ic.py reports/finmind_pit/backtest_results.csv config/tickers_pit.yaml
# 2 Agent 對照組
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent --output-dir reports/finmind_full
```
