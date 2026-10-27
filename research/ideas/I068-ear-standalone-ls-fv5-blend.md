# I068 月營收公告期報酬（EAR）的獨立多空與 fv5 各半組合：EAR 是否提供 fv5 之外的報酬來源（I063 後續，以跨越檢定判定）

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | A | 橫斷面訊號的獨立可交易建構＋跨越檢定（spanning regression）＋資金層級組合 | free | 約 0（前 500 名還原價、月營收、產業分類、借券、台指期已快取；第 1001–1500 名價格與月營收已在 I063 使用） | 2026-10-27 |

## 假設

在市值前 500 名中，以 I063 的 EAR（月初前一日收盤到換倉前一日收盤的產業調整報酬）取代 SUE、其餘照 fv5 建構的等權多空，扣成本、借券費並以台指期對沖後，日報酬對 fv5 與 I049 的 5 個風格因子迴歸的截距為正（全期 Newey-West t ≥ 2.58、兩段皆 > 0），且 fv5 與 EAR 多空各半資金的組合兩段 Sharpe 都不低於 fv5（1.45 / 1.87）、全期至少 1.79（fv5 1.64 + 0.15）。

## 機制（為什麼會有超額報酬）

I063 顯示 EAR 對之後 60 日報酬的預測力與 SUE 幾乎無關（殘差版 t 5.6），代表價格反應含有營收數字以外的資訊（產品組合、毛利、同業解讀），市場對這部分反應不足（Chan、Jegadeesh、Lakonishok 1996；Chen 等 2014）。0.75 SUE + 0.25 EAR 的合成沒有改善，一個可能是合成分數把 SUE 最極端、漂移最強的股票換成中等 SUE 的股票（I054 已發現 SUE 最極端 10% 的漂移最持續），稀釋了 SUE；若 EAR 是獨立的報酬來源，分開做兩個多空、在資金層級組合，就不必犧牲 SUE 的極端名單。反方：fv5 本身就有正的動能曝險（I049 係數 +0.21），EAR 多空可能只是同一個動能曝險的另一種包裝，跨越檢定的截距會接近 0。

## 出處

- （本專案）docs/revenue_ear_ssf_report.md、docs/revenue_ear.md：前 500 名 EAR 全期 FM 係數 +0.045（t 5.8），第 1001–1500 名 t 4.7，五分組 60 日產業調整報酬 Q0 −1.29% 到 Q4 +1.62%（差 2.91 個百分點）；0.75 SUE + 0.25 EAR 的 fv5 建構 1.37 / 1.90、全期 1.61
- （本專案）docs/fv5_style_hedge_report.md：fv5 日淨報酬有 36% 可由 5 個風格因子解釋，主要是動能（+0.21）與高波動（+0.15）曝險；對沖掉後 Sharpe 1.64 → 1.44
- （同儕審查）Chan、Jegadeesh、Lakonishok（1996）Momentum Strategies，Journal of Finance 51(5)，https://ideas.repec.org/a/bla/jfinan/v51y1996i5p1681-1713.html：依摘要，過去報酬與盈餘驚奇控制彼此後各自預測漂移
- （同儕審查，作者為台灣學者，摘要）Chen、Chen、Hsin、Lee（2014）Does revenue momentum drive or ride earnings or price momentum?，Journal of Banking & Finance 38: 166–185，https://ir.lib.nycu.edu.tw:443/handle/11536/23670：營收、盈餘、價格動能各自帶有未被定價的資訊，沒有一個能取代其他
- （工作論文，經二手摘要）Brandt、Kishore、Santa-Clara、Venkatachalam（2008）Earnings announcements are full of surprises，Duke University 工作論文，Quantpedia 摘要 https://quantpedia.com/strategy-tags/earnings-announcement/：以公告期價格反應（EAR）排序的組合有公告後漂移；全文未讀到，數字不引用
- （工作論文，NBER）Novy-Marx（2015）Fundamentally, momentum is fundamental momentum，https://www.nber.org/papers/w20984 （作者頁 https://mysimon.rochester.edu/novy-marx/research/FMFM.pdf）：依摘要，價格動能的表現可由盈餘動能（含公告期報酬）解釋；提示 EAR 多空與 fv5 的動能曝險可能重疊

## 台股適用性

台灣月營收每月 10 日前公告，EAR 每月都有新值，可以與 fv5 用同一個換倉日、同一套三份錯開的骨架，執行與成本假設都已在 fv5 驗證過。EAR 已在前 500、第 501–1000、第 1001–1500 名兩段都顯著（I063），沒有找到台股以 EAR 做獨立多空的研究。台股限制：(1) EAR 空方腿是公告期下跌的股票，可能較常在借券條件 D 之外或費率較高，需報告可借比例；(2) 公告期觸及漲跌停的比例約 7%（I063），進場日若漲停買不到、跌停借不到應排除；(3) 換手與 fv5 相近（每 3 個月一份），成本結構不變。

## 所需資料

- FinMind TaiwanStockPrice 還原價（已快取）：EAR、持有期報酬、5 個風格因子
- FinMind TaiwanStockSecuritiesLending、TaiwanDailyShortSaleBalances（已快取）：借券條件 D 與借券費
- FinMind TaiwanFuturesDaily TX（已快取）：台指期對沖
- config/universe_mcap_membership.csv、config/universe_mcap_membership_1500.csv
- analysis/revenue_ear.py（EAR 定義）、analysis/ls_turnover.py 與 fv5_family.py（fv5 骨架）、analysis/fv5_style_hedge.py（風格因子）

## 檢定計畫（看結果前固定）

- 樣本：前 500 名，2019-03 ~ 2026-04 的每月換倉日（約 86 個月），兩段 2019–2022 / 2023–2026/04；2026-05 以後不用。確認樣本：第 1001–1500 名（只做統計，不計借券）。第 501–1000 名只報告。
- 訊號：EAR 與 I063 完全相同（方向 s = +，已由 I063 決定），產業內前／後 1/3 等權多空；其餘全部沿用 fv5：借券條件 D、三份錯開每 3 個月換倉、單邊 0.29625% 成本、實際借券費、台指期對沖。進場日漲停的多單、跌停的空單不建倉（與 fv5 處理相同）。
- P1（獨立）：EAR 多空兩段淨 Sharpe 皆 > 0。
- P2（主判定，跨越檢定）：EAR 多空日淨報酬 = a + b·fv5 日淨報酬 + 5 個 I049 風格因子（12-1 動能、60 日波動、帳面市值比、前 20 日報酬、250 日 β）+ e；Newey-West 落後 5。通過：全期 a 的 t ≥ 2.58（本批 5 張卡 Holm 校正最嚴門檻，α = 5%），兩段 a 皆 > 0。
- P3（可交易）：fv5 與 EAR 多空各 50% 資金（每日依資金比例合併淨報酬，不做波動縮放、不做權重網格）。通過：兩段 Sharpe 皆 ≥ fv5（1.45 / 1.87）且全期 ≥ 1.79。
- 確認：第 1001–1500 名，同一建構但不設借券限制、只扣交易成本，EAR 多空月報酬對同樣本 SUE 多空與 5 個風格因子的跨越截距同號且 t ≥ 2.0。
- 判定：P1、P2、P3、確認全部通過才算通過，另立前瞻規格與 fv5 平行記錄；任一未過即停止，不改權重、不改視窗、不改分組重測。
- 只報告（診斷 I063 H2 為何沒改善）：EAR 多空與 fv5 日報酬相關；fv5 多方名單中 EAR 前 1/3 的比例；0.75/0.25 合成相對 fv5 被換掉的股票，其 SUE 分位與之後 60 日報酬；EAR 多空的多方腿與空方腿各自相對產業平均的年化報酬；空方腿可借比例；fv5x 與 EAR 多空各半的版本。
- 資料窺探：EAR 五分組（前 500 名，未扣成本）與 H2 合成結果已看過；EAR 獨立多空的淨報酬、與 fv5 的相關、跨越截距都沒有看過。因為點子是看到 H2 失敗後才設計，主判定用跨越截距（直接回答「是否為 fv5 以外的來源」）並要求第 1001–1500 名確認。

## 與已測點子的關係

- 月營收公告期間的市場反應（公告期報酬）對 SUE 的增量：價格反應是否帶有營收數字以外的資訊（card:已測：H1 通過、H2 未通過（不另立前瞻），research/ideas/I063-revenue-announcement-window-return-ear.md）：命中 公告期報酬, earnings announcement return, announcement return, EAR, 月營收公告
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5, SUE
- fv5 空方腿改以融券為主、借券補足：借券費與強制回補成本的取捨（訊號與名單不變）（card:已測：未通過（保守情境 +0.41%），research/ideas/I056-fv5-short-leg-margin-vs-sbl.md）：命中 借券, 借券費
- fv5 空方腿避開融券回補買壓：新空單若在 10 個交易日內遇到停券窗，延到最後回補日收盤再建倉（訊號與名單不變，只改建倉時點）（card:已測：未通過（只在 2023 年後有效），research/ideas/I059-fv5-short-defer-stop-window.md）：命中 fv5, 借券
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 借券賣出餘額比、借券費率、增量、需求量（partial，docs/lending_legs_report.md）：命中 借券
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 外資台指期／台指選擇權淨部位擇時（failed，docs/fut_inst_timing_report.md）：命中 台指期
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 fv5
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- 借券賣出餘額比相對自身歷史（ts_rank）——與 SUE 合成（effective，docs/ts_rank_report.md）：命中 借券
- 12-1 動能、持續性動能、frog-in-the-pan（failed，docs/revmom_persist_report.md）：命中 momentum
- 外資台指期／台指選擇權淨部位：大盤擇時（台指期執行）（card:已測：未通過，research/ideas/I013-foreign-futures-options-positions-timing.md）：命中 台指期
- 美股大型科技公司財報反應對台股連結股的延遲傳遞（客戶／同業財報 → 台灣供應鏈）（card:已測：未通過，research/ideas/I016-us-earnings-to-taiwan-linked-stocks.md）：命中 earnings announcement return
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- fv5 腿內波動調整權重：以逆變異數權重取代等權（card:已測：未通過（W2 接近），research/ideas/I033-fv5-inverse-volatility-leg-weights.md）：命中 等權
- 中小型股（市值第 501–1000 名）執行面前置檢查：容量、滑價、漲跌停、借券與避險工具（card:已測：L2、S 未過（只做統計檢定），research/ideas/I042-smallcap-execution-precheck.md）：命中 借券
- 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）（card:已測：未通過（階段 1 過、階段 2 t 2.8），research/ideas/I043-smallcap-multifactor-composite.md）：命中 sue
- fv5 的未定價風險對沖：在既有名單內調權重，讓多空組合對風格因子（動能、波動、價值、反轉、β）的報酬負荷歸零（card:已測：未通過，research/ideas/I049-fv5-unpriced-style-risk-hedge.md）：命中 fv5 建構
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:已測：未通過，research/ideas/I054-fv5-entry-execution-price.md）：命中 fv5
- 現金股利發放日的再投資買壓（Hartzmark–Solomon 台股版）：大額發放日的加權指數報酬較高，以台指期執行（card:已測：未通過，research/ideas/I060-dividend-payment-reinvestment-pressure.md）：命中 台指期
- fv5 家族的稅後績效與除息日建倉規則：個人投資人股利所得稅與二代健保補充保費下，多方新倉延到除息後是否改善稅後報酬（card:已測：R1 未通過（稅後績效已報告），research/ideas/I061-fv5-after-tax-exdiv-entry.md）：命中 fv5
- 補充：與 I063 H2 不同：H2 把 EAR 併進同一個分數（換掉部分 SUE 名單），本卡保留 fv5 名單不動，EAR 單獨成一個多空，在資金層級組合，並以跨越截距判定是否為獨立報酬來源。與 I049（對沖風格因子，未通過）不同：本卡不對沖，只把風格因子當跨越檢定的控制。與已失敗的 1 個月反轉、12-1 動能不同：EAR 只取月營收公告期間的報酬。

研究點子，非投資建議。
