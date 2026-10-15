# HANDOFF — 專案交接狀態

更新日期：2026-10-13

## 一句話
（2026-10-14 總覽：docs/effective_signals.md —— 有效：月營收驚奇 SUE、營收創新高；前瞻 fv1–fv5 記錄中）
多代理人精度加權投資研究系統（台股）。精度加權機制在 synthetic 中成立，但真實資料上各 Agent 沒有絕對方向資訊；之後轉向「找可交易的選股訊號」。到 2026-10-12：
- 唯一兩段（2019–2022 / 2023–2026）都顯著的訊號是**月營收驚奇 SUE**（公告期限後進場，產業內 IC +0.032 / +0.059；與 0050 擇時各半混合 Sharpe 0.88 / 2.64 > 0050 0.75 / 2.40），已凍結為前瞻規格 **fv2**（10-13 起 live）；
- 財報 Agent（fv1 前瞻中）產業內 IC 約 +0.03，穩定但弱；估值、技術面、動能、反轉、領先落後、子產業、技術面進出場、盈餘驚奇皆未通過兩段一致性；
- **腿池第一輪（全市場市值前 300 檔，docs/leg_pool_report.md，2026-10-13）**：原定指標（台指期對沖純 alpha Sharpe）下所有腿與 700 個組合都不為正——等權做多 vs 市值加權（台積電主導）指數的結構差使股票池基準本身 −0.25 / −0.67；扣掉基準後 **SUE 超額 Sharpe 1.24 / 1.73、8/8 年為正**，其餘 10 條價量／籌碼腿都為負，沒有組合兩段都勝過 SUE 單獨 → 腿池目前只有 SUE。**對沖結構差（docs/hedge_construction_report.md）**：產業內市值加權讓基準從 −4.5%／年縮到 −1.2%，但 SUE 的選股能力也被稀釋（市值加權做多 −0.14 / 0.26；市值加權多空含實際借券費 1.56%／年 0.22 / −0.02）→ SUE 的 alpha 在權重小的股票。**等權多空 + 可借量檢查（`docs/borrow_capacity_report.md`）**：放空名單 98% 有借券成交，資金 2 億內額度與深度不是瓶頸、費率才是（小型股 20% 部位 > 5%／年）；限制可借（費率 ≤ 5%）並扣實際借券費後 Sharpe 約 0.5 / 1.15（年化 +5%、波動 6%、回撤 −13%、年換手 21 倍），是第一個台指期對沖口徑下兩段都為正的可交易建構；不限制可借 0.82 / 1.45。**降換手（`docs/ls_turnover_report.md`）**：每 3 個月換倉 0.79 / 1.85（年化 +7.8%、換手 9 倍、交易成本 2.7%／年）、每 3 個月 + 緩衝 0.71 / 1.86（回撤 −8.9%、換手 7.1 倍），兩段都高於每月換倉；**換倉起點穩健性（`docs/ls_offsets_top300.md`）**：無緩衝 3 個起點都通過（0.87/1.85、0.87/1.52、0.69/1.38 vs 每月 0.46/1.16），三份資金錯開平均 0.93 / 1.79；有緩衝 2/3。**已凍結前瞻規格 fv3**（三份資金錯開、每 3 個月、限制可借、台指期對沖；`forward/run_forward_fv3.py`、`forward/fv3/`，2026-10-13 凍結於 git `774c33c`）。**營收動能延伸與持續性動能（`docs/revmom_persist_report.md`）**：營收創新高（÷ 前 24 個月最高）產業內 IC 20 日 +0.035（t 2.6）/ +0.059（t 3.7）、60 日 +0.060 / +0.087，與 SUE 分數相關 +0.40；SUE + 創新高各半合成（fv3 建構）1.22 / 2.13、年化 +9.4%、8/8 年為正，是唯一通過「合成兩段都高於 SUE 單獨」的訊號（報酬差 +2.0%／年，t 1.7）；年增率加速、3 個月年增率 IC 顯著但與 SUE 重疊、合成變差；持續性排名、frog-in-the-pan 不顯著。**新反轉／動能（`docs/reversal_signals_report.md`）**：隔夜／盤中拆解（Ho 等 2023）、殘差反轉（含排除每月 1–10 日）、季節性動能（Fu & Hsieh 2024）7 個訊號產業內 IC 都在 ±0.04 內、無 |t| > 2，扣成本後多空全負 → 不採用。**使用者規則「SUE + 兩日連漲進場（依漲幅 × 成交金額加碼、單檔 ≤ 20%）、連跌兩日且破 20 日線賣半、連跌三日全賣」（docs/sue_breakout_report.md）**：0.50 / 1.06（換手 35 倍），差於月換倉 SUE 0.91 / 1.42；同一進場但不做技術面出場 1.06 / 1.56（兩段都高於月換倉，2023 年後仍低於 0050 1.90）。**拆解（docs/sue_breakout_decompose_report.md，8 個版本）**：分批機制本身 +1.5%／年（t 0.8）、兩日連漲時點與成交金額加權兩段方向相反；只有「漲幅加權」兩段一致（報酬 +5–9%／年，扣 0050 β 後 t ≈ 2，但波動 +15–22%，Sharpe 只 +0.09），屬邊際結果。**是否為動能（docs/sue_tilt_momentum_report.md）**：依兩日報酬排名加碼 +0.0%／年、1 個月 / 3 個月 / 12-1 動能 +0.8% / +1.7% / +0.6%；原版比值的 +4.7%（t 3.8）與 60 日波動度傾斜相同（超額相關 0.75，控制後剩 +2.1%）且集中在 2023 年後 → 主要是偏向高波動股，不是動能，不建議採用。

## 架構
- `config/tickers.yaml`：股票池與全部參數（horizon、閾值、EMA α、冷啟動門檻、基準 0050、交易成本、`outcome_basis`、`agents` 清單、`macro` 窗口）
- `agents/llm_client.py`：provider 可選 anthropic / ollama（地端），JSON schema 結構化輸出、temperature 0、回應快取於 `data_cache/llm/`（納入版控，重跑不需重新推論）
- `agents/`：`base.py` 介面 `analyze(ticker, as_of_date) → AgentOutput`，以及共用的規則評分 `score_components`；`fundamentals_agent`、`news_agent`、`macro_agent` 已實作（規則式；LLM 可用時改用 LLM 判讀，失敗退回規則式；`raw_features.llm_used` 標示是否實際採用 LLM）、`supply_chain_agent`（知識圖譜 `config/supply_chain_graph.json`：2026-10-08 依 2024 年度年報修訂，每條邊標註出處；下游節點是需求代理、非確認客戶——五家年報皆無占營收 10% 以上的外部客戶；v1 另存 `supply_chain_graph_v1.json`）。`news_agent` 可選 `content_fetcher` 於檢索後補新聞內文
- `arbitrator/`：`precision_tracker.py`（Brier EMA、n<5 冷啟動）、`merge.py`（precision×confidence 加權）、`calibration.py`（Agent 層級收縮校準 p' = σ(a·logit p)，a ∈ [0,1]，walk-forward 擬合）
- `data/fetch_article.py`：新聞內文抓取（遵守 robots.txt、同網域 ≥ 1 秒）；快取 `article_cache/` **不納入版控**（著作權）；Google News 轉址連結無法解析
- `data/fetch_supply_chain.py`：圖譜載入與關聯公司的含息還原股價、月營收
- `data/`：FinMind 抓取（快取/節流/額度等待）、含息還原價（`get_total_return_prices`：以 DividendResult + SplitPrice 自行還原，PriceAdj 需付費）、`fetch_macro.py`（法人/外資持股/融資/匯率/美債/大盤外資，只用 as_of 前一日以前的資料）、RSS 新聞、向量庫封裝
- `backtest/`：`run_backtest.py`（walk-forward，共用市場日曆取樣，T+20 到期才更新精度，財報公告遞延防 look-ahead，`--agents` 選擇 Agent，報表含個別 Agent 消融）、`metrics.py`（Brier/ECE）、`portfolio.py`（連續報酬 Rank IC、long/neutral 組合、vs 0050）
- `data_cache/` 刻意納入版控，重跑既有範圍不耗 API 額度（2026-10-09 起例外，見下方 data_cache 版控政策）
- `forward/`：前瞻驗證（凍結規格 fv1、預測／結算紀錄、`auto` 排程指令）；`site/`：研究網站（`build_site.py` 產生單一 HTML，`auto` 有更新時重建）
- `analysis/sector_neutral_portfolio.py`：產業中性做多、產業內多空組合，21 起點穩健性
- `agents/technical_agent.py` + `data/fetch_technical.py`：技術面 Agent（未採用，研究工具）；`data/fetch_subindustry.py`：櫃買中心產業價值鏈子產業（`config/subindustry_pit.csv`）
- `data/revenue_signal.py`：月營收驚奇核心（研究與 fv2 共用，fv2 凍結其程式碼指紋）；`analysis/fund_tech_daily.py`：每日回測引擎（指定訊號欄位與換倉日）
- `forward/run_forward_fv2.py`：前瞻規格 fv2（紀錄在 `forward/fv2/`），由 `forward/run_forward.py auto` 每日一併執行，失敗不影響 fv1
- 腿池流程（2026-10-12 起）：`data/universe_mcap.py`（全市場市值股票池）、`analysis/build_universe_mcap.py`、`analysis/fetch_leg_data.py`、`analysis/leg_probe.py`（單腿探針、純 alpha）、`analysis/leg_enumerate.py`（本機枚舉）

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
- **產業內 IC 加權（`arbitrator/ic_weighting.py`，策略 `ic_weighted`，詳見 `docs/ic_weighting_report.md`）**：權重 = max(0, 最近 24 個已到期時點的平均產業內 IC)，不足 6 期等權；純產業押注不算產業內能力（第一版會誤算，已由測試抓到並修正）。無偏誤股票池：3 Agent IC 加權相對等權 +0.30%/期（t 1.09），簡單平均為 −0.44%；2023 年後財報 Agent 權重占 97–100%，但 2020 年權重一度幾乎全給供應鏈（雜訊）。沒有勝過財報 Agent 單獨（+0.26%，t 1.90）；只放財報 Agent 的合併（`reports/finmind_pit_fundamentals`）+0.28%（t 1.26）。關鍵數字：財報 Agent 每期產業內 IC 平均 0.029、標準差 0.122，24 期估計標準誤 0.025，要 t = 2 需約 73 期（6 年）→ 任何依歷史表現調權的機制（含精度加權）在這種訊號強度下都主要在追雜訊
- **前瞻驗證（`forward/`，詳見 `docs/forward_validation.md`）**：規格 fv1 於 2026-10-09 凍結（git `57c364d`；spec 檔 commit `e940168`）：只用財報 Agent、連續輸出、當年無偏誤成員、每月第一個交易日預測、持有 20 個交易日；事先登錄主要指標（產業內 IC）與評估方式（只算 live；24 期檢查警訊、73 期正式檢定 t > 2）。`predict` 會比對財報 Agent / 評分 / 機率映射 / 公告遞延 / 含息還原的程式碼指紋，改了就拒絕；紀錄只能新增；每次用 `data_cache/forward/<日期>/` 的新資料快照。已回填開發未用過的 2026-06、07、08、09（結算）與 10（待結算）：產業內 IC +0.005（4 期，t 0.07）。2026-07 加權指數 20 日 −15%、股票池平均 −26%（國巨 1,140 → 456.5，連續跌停，非資料錯誤）。紀錄瑕疵：回填第 2–5 批 `git_dirty` 誤記為 True（把未 commit 的 predictions.csv 算進去），已修正檢查，既有紀錄不改
- **回測成績單（`docs/scorecard.md`，`analysis/scorecard.py` 從 reports/ 產生，也顯示在研究網站）**：方向準確率、Brier、年化報酬、Sharpe、最大回撤，對 0050 與等權持有。方向準確率都低於「永遠猜上漲」；Sharpe 都低於 0050（無偏誤股票池：財報 Agent 1.24、產業中性做多 1.25、0050 1.49）
- **樣本外與過度擬合（`docs/overfitting_controls.md`、`docs/oos_report.md`，2026-10-10）**：財報規則自 MVP 未調參 → 無偏誤股票池 2019–2022 為規則樣本外。21 起點中位數：原規則 Sharpe 0.48、相對等權 IR +0.13（樣本內 1.87 / +0.76）；產業中性做多 0.57 / +0.26（樣本內 1.80 / +0.80）；等權 0.59、0050 0.73。Deflated Sharpe ≤ 0.25（不顯著）。前瞻 4 期產業中性做多相對等權 +0.54%（3 正 1 負）
- **技術面 / 動能 / 反轉 / 估值與進出場濾網（`docs/technical_timing_report.md`，2026-10-10）**：技術面 Agent（`agents/technical_agent.py`，指標 `data/fetch_technical.py`：相對 60 日線、20/60 日線排列、量價、突破前 60 日高低點、5 日 K 線實體；`--agents technical_agent`）。產業內 IC 2019–2022 樣本外 / 2023–2026：財報 +0.017 / +0.046；產業內相對估值（`analysis/valuation_signal.py`，改寫自 BRAIN industry-relative valuation，TaiwanStockPER + 自算市值）−0.001 / −0.021；技術面 −0.035 / +0.041；動能 12-1 −0.014 / +0.049；反轉 1 個月 +0.045 / −0.031 → 沒有新訊號兩段都有效（動能與反轉隨行情互換）。大盤濾網（0050 > 200 日線）把財報產業中性回撤 −40% → −24%，但樣本外 Sharpe 0.57 → 0.37；沒有組合的 Sharpe 贏過 0050（0.72 / 2.09）
- **短期反轉 / 過度反應 / 產業領先落後（`docs/short_term_reversal_report.md`，5 日預測期，2026-10-10）**：同一收盤成交的 1 日反轉產業內 IC +0.034（t 3.4）/ +0.027（t 2.4），隔日成交只剩 +0.009 / +0.010；每 5 日換手 1.3（多空 2.7），扣成本後所有版本、兩段都為負。過度反應（低量 vs 高量）兩段方向相反；領先股過去 5 日報酬對追隨股無預測力（−0.009 / +0.011），「領先 − 自身」的效果來自反轉
- **反轉輔助換倉（`docs/reversal_execution_report.md`，2026-10-10）**：財報產業中性組合換倉時，B 延後賣出近 5 日跌深的持股、C 選股分數加 0.1 × 反轉百分位。B 換手 0.58 → 0.52（緩衝下 0.42 → 0.37），樣本外超額 +0.13% → +0.16%（緩衝下不變），Sharpe 幾乎不變；C 無效。最佳仍是「產業中性 + 緩衝」：樣本外超額 +0.25%（t 1.1）、Sharpe 0.63 < 0050 0.72
- **子產業分類（`docs/subindustry_report.md`，`config/subindustry_pit.csv`，2026-10-10）**：來源櫃買中心產業價值鏈資訊平台（`data/fetch_subindustry.py`；主要子產業 = 電子核心產業鏈中、與大產業對應、公司申報筆數最多者），265/271 檔、63 種。子產業 ≥ 5 檔才獨立成組（每日 11.8 組 vs 大產業 7 組）。財報 Agent 組內 IC 樣本外 +0.017 → +0.015（緩衝組合 +0.25% → +0.24%）；估值在子產業 × 市值五分位樣本外 IC +0.014（20/21）但 2023–2026 −0.014、組合仍虧損；領先落後仍無效。主要限制：股票池 100 檔太小
- **基本面選股 + 技術面每日進出場（`docs/fund_tech_daily_report.md`，`analysis/fund_tech_daily.py` 每日回測，2026-10-10；2026-10-12 修正起點 0 漏掉第一次換倉的 bug）**：財報產業中性 + 緩衝，樣本外 / 2023–2026 Sharpe 0.68 / 2.00（每日回撤 −44% / −40%）；個股 60 日線每日進出 0.19 / 1.69（年換手 17）；20 日線 0.49 / 1.12；大盤每日濾網 0.52 / 2.13；財報 + 技術面權重混合 0.63 / 2.08。對照：0050 0.77 / 2.40；0050 + 每日 200 日線濾網 0.80 / 2.41、回撤 −16%（Sharpe 打平、回撤減半；更正前誤記 0.81 vs 0.71）
- **配置研究（`docs/allocation_study_report.md`，`analysis/allocation_study.py`，2026-10-12）**：0050 擇時 7 規則（樣本外 / 2023–2026 Sharpe）：買進持有 0.77 / 2.41；120 日 0.85 / 2.15；200 日 0.80 / 2.42；250 日 0.78 / 2.22；雙均線 0.62 / 1.82；200 日 ±2% 緩衝帶 0.99 / 2.42（每年進出 1 次）；每週判斷 0.72 / 2.47；所有規則報酬都低於買進持有。混合（0050 + 200 日線濾網 a、財報選股 1 − a）：a = 75% 0.89 / 2.53、50% 0.85 / 2.44（年化 +16.4% / +55.6%，回撤 −30% / −25%）、0% 0.68 / 2.00（年化 +19.9% / +59.7%）。個股權重：等權 0.68 / 2.00、財報加權 0.65 / 2.03、波動度倒數 0.71 / 1.94、市值加權 0.69 / 2.57（2023 年後 +73%，行情）
- **前瞻驗證 fv2（2026-10-12 凍結於 git `c06469a`）**：SUE、公告期限後進場（只採 create_time ≤ 期限的營收）、產業中性前 1/3 + 緩衝；回測預期 IC +0.044（sd 0.119）。回填 2026-05～09：4 期已結算，IC 平均 −0.015（無統計意義）
- **強化月營收驚奇（`docs/revenue_surprise_plus_report.md`，2026-10-12）**：盈餘驚奇（歸屬母公司淨利，Q1 5/15、Q2 8/14、Q3 11/14、Q4 3/31 後才用）產業內 IC 20 日 +0.013 / +0.038、60 日 −0.002 / +0.051；與營收驚奇排名相關 +0.29；合成 +0.027 / +0.058（比營收單獨差）。每日回測 Sharpe（樣本外 / 2023–2026）：營收驚奇每 1 個月 0.73 / 2.32（換手 5.7）、每 3 個月 0.70 / 2.38（換手 3.1）；合成每 1 個月 0.70 / 2.08。與 0050 擇時各半：每 1 個月 0.88 / 2.64、每 3 個月 0.86 / 2.67
- **月營收驚奇 SUE（`docs/revenue_surprise_report.md`，`analysis/revenue_surprise.py`，2026-10-12）**：進場 = 當月 10 日或之後第一個交易日的下一個交易日；SUE = (R − R₋₁₂ − μ)/σ（過去 24 個月年差）。產業內 IC 20 日 +0.032（t 2.0）/ +0.059（t 2.9），60 日 +0.044 / +0.091；準時年增率 +0.015 / +0.058；財報 Agent −0.013 / +0.045。公告期間事先反映 IC +0.14 / +0.19。延後 1–10 日仍有效。每日回測：SUE 產業中性 + 緩衝 0.73 / 2.32（年化 +21.3% / +69.3%），財報 Agent 0.61 / 2.17，0050 0.75 / 2.40，50% SUE + 50% 0050 擇時 0.88 / 2.64。**現行財報 Agent 的月營收遞延 40 天，比實際公告晚約一個月使用**
- **產業中性組合（`docs/sector_neutral_report.md`，2026-10-10）**：財報 Agent 連續機率在每個產業內取前 1/3、產業權重等於股票池。未扣成本相對等權 +0.42%／期（t 2.01）、產業內多空 +0.93%／期（t 2.42），兩期與 21 起點全部為正；扣成本後做多 +0.26%（t 1.17）、多空 +0.55%。換手每期 0.60，成本吃掉約四成；加「仍在產業內前 50% 就續抱」的緩衝（事後調整）換手降到 0.44，做多扣成本 +0.35%（t 1.91）。不分產業的前 1/3 在 2024–2026 降到 +0.20%，產業中性兩期較一致。門檻模式機率明顯較差（+0.05%），前後 1/5 在 2019–2023 為負。放空成本未計，多空只作訊號強度指標
- **data_cache 版控政策（2026-10-09 起）**：無偏誤股票池新增約 3,000 個 FinMind 快取檔（約 1.2 GB），不再納入版控（`.gitignore`：`data_cache/*`，但 `data_cache/llm/` 與既有已追蹤檔案仍版控）。重現 `finmind_pit` 需重新下載（約 4–5 小時 FinMind 額度，客戶端會自動等待額度）
- **選股偏誤**：擴大股票池是 2026 年事後挑選的 AI 贏家（等權持有 +1,493% vs 0050 +566%），絕對報酬與跨產業 IC 都會被高估；以產業內 IC 與相對等權持有為主要指標
- 擴大圖譜 `config/supply_chain_graph_expanded.json`：36 檔新股票逐一讀 2024 年報，只有辛耘點名客戶（台積電 21.02%）；多數以代號揭露。154 條邊中 111 條為產業預設、9 條年報文字、9 條推論、1 條年報確認。新增美股代理（NVIDIA、Microsoft、Amazon、Alphabet、Meta、Applied Materials；以 SPY 計算超額報酬）
- **資料修正**：FinMind 有收盤價為 0 的資料列（國巨 2019-11-12、2021-06-30，凱美 2019-03-13，鴻海 2025-07-30），已在資料層視為缺值；重跑 9 份報表，只有 `finmind_supply_chain` 的 5 個事件受影響
- **LLM 判讀有內文的新聞（`reports/finmind_llm_qwen3_content`）**：qwen3:8b、`--llm-num-thread 2`，39 次新呼叫約 3 小時（CPU 約占 16–17%）。內文讓 LLM 新聞判讀也變差（Brier 0.2718 → 0.2877；輸出有變的 20 個事件命中率 66.7% → 44.4%，信心反而更高；校準後係數 0.04）。取得的內文偏向 CMoney 自動文章，主流媒體內文拿不到
- **2026-10-10 起三份 config 的預設 Agent 都只有財報 Agent**；既有報表的指令已補上明確的 `--agents`（4 Agent 指令已驗證可逐筆重現 `finmind_supply_chain_v2`）
- FinMind 客戶端：網路錯誤會退避重試（30s → 600s），最終錯誤訊息不含帶 token 的網址
- 履歷/對外描述注意：Agent 有財報、新聞、總經/籌碼、供應鏈、技術面五個（技術面與供應鏈未採用），目前最強的是月營收驚奇（非 Agent，獨立訊號）；供應鏈圖譜是需求代理而非確認的客戶關係；也不要宣稱打敗大盤或有預測力（Brier 都不如基率）。可宣稱的是：完整的 walk-forward 評估框架、精度加權機制在 synthetic 中驗證有效、對真實資料負結果的誠實分析，以及財報 Agent 在無選股偏誤股票池上有小幅、穩健的產業內排序能力（IC 約 0.02–0.04）。

## 腿池流程（第一輪完成 2026-10-13，報告 docs/leg_pool_report.md）

使用者決策（2026-10-12）：依其 WorldQuant 研究流程（選方向 → 盤點原料 → 固定包裝單腿探針 → 腿池 → 本機枚舉 → 實測 → 提交）建台股版；
股票池擴大到全市場市值前 300 / 500 / 1000 檔；**主要指標改為台指期對沖後的純 alpha Sharpe，0050 為輔**。

| 步驟 | 程式 | 狀態 |
|---|---|---|
| 1. 全市場市值股票池 | `analysis/build_universe_mcap.py` → `config/universe_mcap_membership.csv` | 完成（每年前 1000 名；前 300 / 500 / 1000 的 8 年聯集 480 / 776 / 1,387 檔） |
| 2. 腿資料 | `analysis/fetch_leg_data.py 300` | 前 300 完成；500、1000 未抓 |
| 3. 單腿探針 | `analysis/leg_probe.py 300` → `docs/leg_probe_top300.md`、`reports/legs/pnl_top300.csv`（含 `universe` 基準欄） | 完成 |
| 4. 本機枚舉 | `analysis/leg_enumerate.py 300` → `docs/leg_enumerate_top300.md`（純 alpha 與超額兩種） | 完成：通過 0 組 |
| 5. 合成訊號實際建倉驗證、另立前瞻規格 | 未寫 | 沒有通過的組合，暫不需要 |

- 結果：純 alpha Sharpe（2019–2022 / 2023–2026/04）SUE 0.17 / −0.07，其餘 −0.25 ~ −0.91 / −0.56 ~ −1.21；股票池基準 −0.25 / −0.67（年化 −4.2%）。
  超額（減基準，看完結果後加的診斷）：SUE 1.24 / 1.73（年化 +4.6%，8/8 年正），lowvol60 0.01 / −0.48、short_ratio 0.08 / −0.94，其餘更差；成本（年換手 × 0.29625%）是弱腿虧損的主因之一。
- 腿（事先固定方向）：lowvol20 / lowvol60、resvol60、abvol60、amihud20、season、short_ratio、short_flow、trust_buy、foreign_chg；主腿 sue；借券資料已下載、腿未加入。
- 包裝：產業內 z 分數 → 20 日平均 → 對產業與 log 市值迴歸取殘差；組合：產業內前 1/3 等權；純 alpha = Σw·r − β·台指期近月報酬（β = 持股 250 日 β 加權），扣股票 0.29625% / 期貨 0.005% 單邊成本。
- **2026-05 之後的資料保留不用**（fv2 回填與 live 期間）。
- 市值以「前一交易日收盤 × 普通股股本 ÷ 10」計（股本季報遞延 75 天；FinMind 免費層無市值）；探針中的市值與比率改用外資持股資料的每日已發行股數。
- 對沖結構差（`analysis/hedge_construction.py`，2026-10-13）：市值加權做多、市值加權多空（借券費 = 前 60 日借券成交量加權費率，無成交視為借不到；成員 95% 可借、費率中位數 1.62%／年）都沒有讓 SUE 兩段為正，見 docs/hedge_construction_report.md。
- 連漲進場 / 連跌出場（`analysis/sue_breakout.py`，2026-10-13）：見 docs/sue_breakout_report.md；拆解見 docs/sue_breakout_decompose_report.md（`analysis/sue_breakout_decompose.py`；`backtest()` 的 timing / adv_tilt / gain_tilt 參數）。漲幅加權已檢驗為高波動傾斜（`analysis/sue_tilt_momentum.py`；`backtest()` 另有 `tilt` 參數可傳入自訂倍數）。`prepare()` 另提供每日成交金額 `money`。
- 等權多空與可借量（`analysis/fetch_short_balances.py`、`analysis/borrow_capacity.py`，2026-10-13）：借券賣出額度資料 `TaiwanDailyShortSaleBalances` 免費層可逐檔取得；借券成交量單位為張。
- 降換手與新訊號（`analysis/ls_turnover.py`：`ew_ls_buffer()` 換倉頻率與緩衝；`analysis/reversal_signals.py`：隔夜／盤中拆解 `split_returns()`、殘差反轉、季節性動能），2026-10-13。
- 股權分散、MAX 濾網、營收創新高窗口穩健性已完成（docs/max_rec_robust_report.md）。
- 借券腿已完成（不採用，docs/lending_legs_report.md）。
- 前 500 檔已完成（docs/top500_report.md）。
- 已凍結 fv5（前 500 檔）。
- 下一步選項（待使用者決定）：每週累積集保股權分散資料、前 1000 檔、以中型股 ETF 對沖或主要指標回到相對 0050。
- 長時間下載的經驗：工作階段結束會連帶結束 Claude 啟動的背景程式，需用 `Invoke-CimMethod Win32_Process Create` 啟動獨立行程；重開機曾留下寫一半的快取檔（已改原子寫入、壞檔自動重抓）；使用者要求長時間執行時監控 CPU / RAM（≥ 90% 即停止）並持續記錄進度（`logs/leg_pipeline/status.log`）。
## 待辦（2026-10-15 整理）

### 一、自動執行中（定期查看即可）
1. **前瞻驗證**：Windows 工作排程器每個平日 18:30 執行 `forward/run_forward.py auto --push`，依序 fv1 → fv2 → 發佈 → fv3 → fv4 → 發佈 → fv5 → 發佈（含研究網站 `site/` 重建；線上網站由 Claude 桌面 App 排程工作 `republish-research-site` 每個平日 19:15 依雜湊變動重新發佈，需 App 開著）。查看 `logs/forward_auto.log` 與各 `forward/fv*/REPORT.md`；說明見 docs/forward_validation.md。
   | 規格 | 內容 | 狀態 | 檢定 |
   |---|---|---|---|
   | fv1 | 財報 Agent（電子 100 檔） | 2026-10-01 批約 10/29 結算；第一個 live 約 11/02 | 24 期警訊、73 期檢定 |
   | fv2 | SUE 做多（電子 100 檔） | 第一個 live 2026-10-13 | 12 期警訊、30 期檢定 |
   | fv3 | SUE 等權多空（市值前 300） | 第一個 live 2026-10-13；回填 5 段平均 +0.40%（IC 更正後 +0.046） | 12 段警訊、38 段檢定 |
   | fv4 | SUE + 營收創新高（前 300） | 第一個 live 2026-10-13；回填 +0.24%（IC +0.053） | 12 段警訊、26 段檢定 |
   | fv5 | SUE 等權多空（前 500） | 第一個 live 2026-10-13；回填 −0.47%（IC +0.018） | 12 段警訊、24 段檢定 |
   - 下次預測日約 2026-11-11（10 月營收公告後）；fv3 + fv5 預測日約 3,500 次 FinMind、數小時。
   - fv3 / fv4 / fv5 的產業內 IC 曾有結算取價錯誤（已修正，原紀錄不改，更正值在各 `corrections.csv`）。
2. **延後申報金控的月營收補充**：每月 15 日前申報的 10 家金控（具保險子公司）不在前瞻預測內；`analysis/fin_revenue_supplement.py <營收月份>` 會在 FinMind 尚未收錄時改向公開資訊觀測站即時查詢。2026-09 已於 10/15 全部完成（docs/fin_supplement_2026-09.md）；之後每月要用時手動執行或另設排程。
3. **2027 年 1 月（手動）**：fv1 / fv2 的電子股池由 auto 自動建立；**fv3 / fv4 / fv5 的市值股票池須手動執行 `analysis/build_universe_mcap.py`**（約 4,300 次 FinMind），否則三者略過。

### 二、進行中與待使用者決定
4. **除息後偏弱當作 SUE 做多濾網**：已測，未通過（濾網只排除約 3.5% 做多權重，Sharpe 略降；docs/exdiv_followup_report.md）。
5. **除息後偏弱凍結為 fv6**：已檢查可借量，不建議凍結（2 億時只有 63% 可借、限制後 Sharpe 0.77 / 0.27）；1,000 萬時 79% 可借、Sharpe 0.82 / 0.75，若要用小資金前瞻記錄需使用者決定（docs/exdiv_followup_report.md）。
6. **MSCI 季度調整前瞻記錄**：公告到生效納入減刪除 +5.5%（t 2.1）勉強通過、只有 23 次審核；每季 MSCI 公布後記錄名單與到生效日的報酬，2–3 年後判斷（docs/index_rebalance_report.md）。
7. **strategy-scout 後續點子**：A 群 I004–I007 已測完（皆未通過）；I008（季報實際公告日，約 4 小時爬取）暫緩；B 群尚未做卡：董監申報轉讓、現金增資／可轉債發行、當沖比、法說會公告（research/ideas.csv）。
8. **每週累積集保股權分散資料**：FinMind 為付費、集保開放資料只有最新一週，無法回測；可新增每週排程自行累積，1–2 年後才能測（docs/max_rec_robust_report.md）。
9. **擴大到前 1000 檔**：前 500 檔時 SUE 更強（1.45 / 1.87），可檢查是否持續；約 4,000 次以上 FinMind（docs/top500_report.md）。
10. **對沖方式或主要指標**：以中型股 ETF 對沖，或主要指標回到「相對 0050」。
11. **追蹤「0050 長期持有 + SUE 多空」混合**：多空部分已由 fv3 / fv5 記錄，可直接在前瞻報告中合成（回測 50/50：1.01 / 2.13，0050 0.73 / 1.90；docs/blend_longonly_report.md）。

### 三、優先度低
12. **供應鏈 Agent**：台股客戶多以代號揭露、可靠供應關係資料不足，產業領先落後已失敗。
13. **其他 Agent 的資訊量**：新聞內文已試過（都變差）；需更好的來源或更強的 LLM。
14. **Agent 架構**：各 Agent 個別指定模型；合併機率的中性稀釋（中性 Agent 棄權或對數意見池）；合併後再校準；規格第 9 節待人工決策（新聞可信度分級、MOPS 爬蟲頻率）；報酬評估延伸（機率加權部位、相對 0050 的 outcome）；總經／籌碼 Agent 延伸（主力分點、借券）。

### 新工具（2026-10-14 ~ 15）
- **strategy-scout**（`.claude/agents/strategy-scout.md`、`research/`）：從文獻、量化部落格、PTT 找點子，比對 `research/tested_ideas.yaml` 去重、查 `research/data_catalog.yaml`，產出事前固定檢定計畫的點子卡；**每完成一項研究要補登 tested_ideas.yaml**。
- **公開資訊觀測站資料**：股利分派彙總表（董事會決議日，16–18 次請求整批取得，analysis/dividend_surprise.py）、庫藏股與處置（analysis/fetch_events.py）、單月營收即時查詢（analysis/fin_revenue_supplement.py）、指數成分異動（config/index_changes/）。

### 近期完成（2026-10-12 ~ 15；總覽見 docs/effective_signals.md）
- **有效訊號**：月營收驚奇 SUE（兩段顯著，前 500 檔更強）、營收創新高（單獨兩段顯著；與 SUE 合成在前 300 檔通過、前 500 檔不穩健）。
- **組合建構**：台指期對沖的等權做多有結構差（docs/leg_pool_report.md）；市值加權稀釋選股（docs/hedge_construction_report.md）；等權多空 + 可借量（docs/borrow_capacity_report.md）；每 3 個月換倉與起點穩健性（docs/ls_turnover_report.md、docs/ls_offsets_top300.md）；前 500 檔（docs/top500_report.md）；做多每 3 個月換手減半（docs/blend_longonly_report.md）。
- **前瞻規格**：fv3、fv4、fv5 凍結與回填（docs/forward_validation.md）。
- **未採用**：腿池 10 條價量／籌碼腿、連漲進場／連跌出場與漲幅加權（高波動傾斜）、隔夜／盤中、殘差反轉、季節性動能、持續性動能、MAX 濾網、借券腿（docs/lending_legs_report.md）、依公告日提早進場（扣成本前 +2%／年、扣成本後略輸，docs/sue_event_entry_report.md）、庫藏股買回（隔日開盤即反映，docs/event_study_report.md）。
- **除權息**：除息前布局、填息無效；除息後偏弱在兩段與驗證樣本皆通過（高殖利率 20 日約 −2.4%），事後追加的放空策略 D 兩樣本 Sharpe 1.0–1.4，建議檢查可借量後凍結為 fv6、並測試作為 SUE 做多濾網（docs/dividend_events_report.md）。
- **年度盈餘驚奇用實際決議日**（I007）：與 SUE 不相關、控制後兩樣本全期顯著，但 2023 後不顯著、無法交易，未通過；I008（季報實際公告日）暫緩（docs/earnings_board_date_report.md）。
- **股利政策公告驚奇**（I006）：未通過；附帶發現實際董事會決議日的年度盈餘變動 CAR[+2,+40] 係數 t 5.4，建議另立點子卡（docs/dividend_surprise_report.md）。
- **強化 SUE**（點子卡 I004、I005）：低法人關注加權、產業層級營收驚奇輪動皆未通過；2023 年後 SUE 在高關注股更有效（docs/sue_attention_industry_report.md）。
- **指數換股**（strategy-scout 點子卡 I001–I003）：臺灣50 預測命中 95% 但 2023 後無效；高股息 ETF 無效；MSCI 公告到生效 +5.5%（t 2.1）勉強通過、樣本少，建議前瞻記錄（docs/index_rebalance_report.md）。
- **處置股做多**：前 500 名處置後 20 日 +5.3%（t 4.4），但為事後發現；在市值第 501–1000 名獨立驗證未通過（+2.8%，2019–2022 t 1.7），不採用（docs/event_study_report.md、docs/disposition_replication.md）。
- **擇時**：均線擇時樣本外無優勢（docs/timing_oos_report.md）；景氣燈號（docs/business_cycle_timing_report.md）、台指 VIX（docs/vix_timing_report.md）皆不顯著；改用台指期執行成本降到約 0.1%／年，仍無規則勝過同曝險固定比例，可用於降低回撤（docs/timing_futures_report.md）。
- **其他**：2026 第四季模型排名與產業營收趨勢（docs/outlook_2026q4.md）；回測中延後申報金控的營收時點有輕微前視（docs/effective_signals.md）。

已完成（2026-10-10 ~ 13）：腿池第一輪、對沖結構差、等權多空與可借量、降換手、前瞻 fv3 / fv4、新反轉／動能與持續性動能（皆未採用）、營收創新高；預設合併只放財報 Agent；以財報 Agent 為核心的產業中性組合評估；回測成績單；樣本外與過度擬合說明；技術面 Agent、動能、反轉、產業內相對估值、進出場濾網（皆未採用，見 docs/technical_timing_report.md）；5 日短期反轉、過度反應、產業領先落後（皆未採用，見 docs/short_term_reversal_report.md）；反轉輔助換倉（換手降約 10%、Sharpe 不變，見 docs/reversal_execution_report.md）；子產業分類（已建立，不改變財報分組，見 docs/subindustry_report.md）；基本面選股 + 技術面每日進出場 / 權重混合（皆未採用，見 docs/fund_tech_daily_report.md）；配置研究：擇時規則、混合比例、個股權重（見 docs/allocation_study_report.md）；月營收驚奇 SUE（兩段皆顯著，見 docs/revenue_surprise_report.md）；前瞻 fv2；強化 SUE（盈餘驚奇、拉長持有皆無改善，見 docs/revenue_surprise_plus_report.md）

## 已知限制
每檔僅 27 筆樣本；新聞僅標題；期間與族群單一；地端 LLM 僅測過 qwen3:8b（純 CPU；2 執行緒時長新聞 prompt 每次約 5–7 分鐘）；phi4 未跑完整實驗（3 核心估計完整 386 次呼叫約 61 小時，主要卡在冗長輸出）；總經分量同一時點各檔相同（對選股無幫助）；總經 Agent 的門檻為經驗值；組合報酬每期之間有 1 個交易日空檔（step 21 > horizon 20）未計入；p 值為常態近似。

## 操作
```bash
.venv/Scripts/python -m pytest tests -q          # 221 tests（Windows；macOS/Linux 用 .venv/bin/python）
# 3 Agent（config 預設）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent,macro_agent --output-dir reports/finmind_macro
# LLM 判讀（需 Ollama + qwen3:8b；回應已快取，重跑秒完）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent,macro_agent --llm-provider ollama --llm-model qwen3:8b --llm-think false --output-dir reports/finmind_llm_qwen3
# 4 Agent（含供應鏈，v1 圖譜）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent,macro_agent,supply_chain_agent --supply-chain-graph config/supply_chain_graph_v1.json --output-dir reports/finmind_supply_chain
# 3 Agent + 新聞內文（需連網；內文快取只存在本機）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent,macro_agent --news-content --output-dir reports/finmind_news_content
# 3 Agent LLM + 新聞內文（回應已快取；內文快取只存在本機，需先以 --news-content 抓取）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent,macro_agent --news-content-offline --llm-provider ollama --llm-model qwen3:8b --llm-think false --llm-num-thread 2 --output-dir reports/finmind_llm_qwen3_content
# 供應鏈驗證：樣本內 v2（4 Agent）與 2019–2026 長期（只有供應鏈 Agent；v1 加 --supply-chain-graph config/supply_chain_graph_v1.json）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent,macro_agent,supply_chain_agent --output-dir reports/finmind_supply_chain_v2
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2019-01-01 --end-date 2026-05-31 --step-days 21 --agents supply_chain_agent --output-dir reports/finmind_supply_chain_long_v2
.venv/Scripts/python analysis/phase_robustness.py config/supply_chain_graph.json phase_v2.csv
# 擴大股票池（41 檔 × 2019–2026，不含新聞）與分析
.venv/Scripts/python backtest/run_backtest.py --mode finmind --config config/tickers_expanded.yaml --agents fundamentals_agent,macro_agent,supply_chain_agent --output-dir reports/finmind_expanded
.venv/Scripts/python analysis/agent_ic.py reports/finmind_expanded/backtest_results.csv config/tickers_expanded.yaml
.venv/Scripts/python analysis/phase_robustness_agents.py config/tickers_expanded.yaml daily_expanded.csv
# 連續輸出模式（41 檔、5 檔）與組合穩健性
.venv/Scripts/python backtest/run_backtest.py --mode finmind --config config/tickers_expanded.yaml --agents fundamentals_agent,macro_agent,supply_chain_agent --agent-output continuous --output-dir reports/finmind_expanded_continuous
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent,macro_agent --agent-output continuous --output-dir reports/finmind_macro_continuous
.venv/Scripts/python analysis/portfolio_phase_robustness.py daily_expanded.csv config/tickers_expanded.yaml
# 無選股偏誤股票池（成員表已存；FinMind 快取不在版控，首次需重新下載）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --config config/tickers_pit.yaml --agents fundamentals_agent,macro_agent,supply_chain_agent --output-dir reports/finmind_pit
.venv/Scripts/python analysis/agent_ic.py reports/finmind_pit/backtest_results.csv config/tickers_pit.yaml
# 只放財報 Agent 的合併（IC 加權已含在每次回測的 ic_weighted 策略中）
.venv/Scripts/python backtest/run_backtest.py --mode finmind --config config/tickers_pit.yaml --agents fundamentals_agent --output-dir reports/finmind_pit_fundamentals
# 前瞻驗證（每月第一個交易日）
.venv/Scripts/python forward/run_forward.py predict --as-of YYYY-MM-DD
.venv/Scripts/python forward/run_forward.py resolve
.venv/Scripts/python forward/run_forward.py report
# 產業中性組合（先產生每日輸出 daily_pit.csv，再算組合）
.venv/Scripts/python analysis/phase_robustness_agents.py config/tickers_pit.yaml daily_pit.csv
.venv/Scripts/python analysis/sector_neutral_portfolio.py daily_pit.csv config/tickers_pit.yaml --keep 0.5
# 前瞻驗證自動執行（工作排程器使用）與研究網站重建
.venv/Scripts/python forward/run_forward.py auto --push
.venv/Scripts/python site/build_site.py
# 回測成績單（docs/scorecard.md、reports/scorecard.json；網站重建時會讀取）
.venv/Scripts/python analysis/scorecard.py
# 技術面 / 動能 / 反轉 / 估值與濾網（估值資料 271 次 FinMind 呼叫；評估約 20 分鐘）
.venv/Scripts/python analysis/valuation_signal.py fetch config/tickers_pit.yaml
.venv/Scripts/python analysis/valuation_signal.py build daily_pit.csv config/tickers_pit.yaml daily_pit_val.csv
.venv/Scripts/python analysis/technical_timing.py daily_pit_val.csv config/tickers_pit.yaml
# 5 日短期反轉 / 過度反應 / 領先落後（輸入為上一步產生的 daily_pit_val_tech.csv；約 15 分鐘）
.venv/Scripts/python analysis/short_term_reversal.py daily_pit_val_tech.csv config/tickers_pit.yaml
# 子產業分類（約 280 次網頁請求）與評估
.venv/Scripts/python analysis/build_subindustry.py config/tickers_pit.yaml
.venv/Scripts/python analysis/subindustry_eval.py daily_pit_val_tech.csv config/tickers_pit.yaml
# 基本面選股 + 技術面每日進出場（每日回測，約 15 分鐘）
.venv/Scripts/python analysis/fund_tech_daily.py daily_pit_val_tech.csv config/tickers_pit.yaml
# 腿池流程（全市場市值前 N 檔；FinMind 額度不足時會自動等待，可中斷重跑）
.venv/Scripts/python analysis/build_universe_mcap.py
.venv/Scripts/python analysis/fetch_leg_data.py 300
.venv/Scripts/python analysis/leg_probe.py 300
.venv/Scripts/python analysis/leg_enumerate.py 300
# 前瞻驗證 fv2（月營收驚奇；auto 會一併執行）
.venv/Scripts/python forward/run_forward_fv2.py schedule
.venv/Scripts/python forward/run_forward_fv2.py resolve
.venv/Scripts/python forward/run_forward_fv2.py report
# 月營收驚奇 SUE（約 3 分鐘）與強化版（約 5 分鐘）
.venv/Scripts/python analysis/revenue_surprise_plus.py daily_pit_val_tech.csv config/tickers_pit.yaml
.venv/Scripts/python analysis/revenue_surprise.py daily_pit_val_tech.csv config/tickers_pit.yaml
# 配置研究：擇時規則 / 混合比例 / 個股權重（約 20 分鐘）
.venv/Scripts/python analysis/allocation_study.py daily_pit_val_tech.csv config/tickers_pit.yaml
# 反轉輔助換倉（約 10 分鐘）
.venv/Scripts/python analysis/reversal_execution.py daily_pit_val_tech.csv config/tickers_pit.yaml
# 樣本內 / 樣本外（docs/oos_report.md）
.venv/Scripts/python analysis/oos_report.py daily_pit.csv config/tickers_pit.yaml
# 2 Agent 對照組
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent --output-dir reports/finmind_full
```
