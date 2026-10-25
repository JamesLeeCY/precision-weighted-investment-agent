# I063 月營收公告期間的市場反應（公告期報酬）對 SUE 的增量：價格反應是否帶有營收數字以外的資訊

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | A | 橫斷面 IC（Fama-MacBeth 增量）＋濾網或加權（fv5 合成建構比較） | free | 約 0（前 500 名與第 1001–1500 名的還原價、月營收、產業分類已快取；若第 1001–1500 名價格有缺，至多約 50） | 2026-10-25 |

## 假設

在市值前 500 名中，控制 SUE、營收創新高、上月非公告期報酬與市值後，月營收公告期間（上月最後交易日收盤 → fv5 進場日前一日收盤）的產業調整報酬（EAR），對進場後 60 個交易日報酬有增量預測力（Fama-MacBeth 全期 |t| ≥ 2.58，方向以 2019–2022 決定、事前預期為正），且在 2023–2026/04 與第 1001–1500 名同號確認；以 0.75 × SUE ＋ 0.25 × EAR（同方向）合成的 fv5 建構，兩段 Sharpe 都不低於 fv5（1.45 / 1.87）、全期至少 1.74。

## 機制（為什麼會有超額報酬）

SUE 只衡量營收數字相對自身歷史的意外；公告期間的價格反應還整合了營收以外、SUE 看不到的資訊（產品組合、毛利、同業與法人的解讀）。若市場對這部分同樣反應不足，高反應股之後應續強（Chan、Jegadeesh、Lakonishok 1996：過去報酬與盈餘驚奇在控制彼此後各自預測漂移；Jegadeesh 與 Livnat 2006：營收驚奇有盈餘以外的漂移，分析師調整緩慢）。反方：台股前 500 名有 1 日短期反轉（本專案 IC t 3.4 / 2.4），公告期的急漲可能是過度反應，係數會是負的。兩種機制都可交易（正號用動能、負號用反轉合成），所以方向由前段資料決定、後段與獨立樣本確認。

## 出處

- （同儕審查）Chan、Jegadeesh、Lakonishok（1996）Momentum Strategies，Journal of Finance 51(5): 1681–1713，https://ideas.repec.org/a/bla/jfinan/v51y1996i5p1681-1713.html：依摘要，過去報酬與過去盈餘驚奇在控制彼此後各自預測後續漂移，高價格與盈餘動能股之後少有反轉
- （同儕審查；摘要依 2004 工作論文版本）Jegadeesh、Livnat（2006）Revenue surprises and stock returns，Journal of Accounting and Economics 41: 147–171，https://ideas.repec.org/a/eee/jaecon/v41y2006i1-2p147-171.html：營收驚奇大的股票在控制盈餘驚奇後，公告後仍有顯著異常報酬；分析師對營收資訊的修正緩慢
- （同儕審查）Jegadeesh、Livnat（2006）Post-Earnings-Announcement Drift: The Role of Revenue Surprises，Financial Analysts Journal，https://rpc.cfainstitute.org/research/financial-analysts-journal/2006/post-earnings-announcement-drift-the-role-of-revenue-surprises：營收與盈餘驚奇同向時，盈餘公告後漂移較強（依搜尋摘要）
- （學位論文，台灣）周子安（2016）前百大電子股月營收事件研究，https://www.airitilibrary.com/Publication/Index/U0023-1303201714243478：公告前 5 日已有異常報酬（依本專案 docs/taiwan_alpha_literature.md 的整理）
- （研究計畫摘要，台灣，非實證結果）中國文化大學（2020）Timely Monthly Sales Disclosure, Earnings Volatility, and Market Reactions to Earnings Surprises，https://openalex.org/W7111563851：台灣月營收早於季報揭露，計畫預期可減輕季盈餘公告後的延遲反應
- （本專案）docs/revenue_surprise_report.md：SUE 與公告期間報酬（上月底 → 進場前一日）的產業內 IC 為 +0.14 / +0.19（t 7–9），兩者相關但非同一件事；docs/short_term_reversal_report.md：1 日反轉 IC t 3.4 / 2.4、隔日成交即消失；1 個月反轉兩段方向不一致

## 台股適用性

台灣月營收的公告期間固定（每月 1–10 日，一般公司 10 日前），所以即使 FinMind 沒有歷史逐家公告日（create_time 只有 2026 年才有值），也可用固定視窗涵蓋幾乎所有一般公司的公告；延後申報的金控（15 日前）不列入，與 fv5 金融股的處理一致。視窗內也有營收以外的事件（月初大盤、6–8 月除權息），所以用產業調整並控制上月其餘期間報酬。漲跌停：公告期連續漲停者報酬被 10% 限制截斷，需報告比例。沒有找到台股以公告期報酬為訊號的研究；周子安（2016）只顯示公告前已有反應。

## 所需資料

- FinMind TaiwanStockPrice 還原價（已快取）：公告期報酬、上月其餘期間報酬、60 日後續報酬
- FinMind TaiwanStockMonthRevenue（已快取）：SUE、營收創新高
- config/universe_mcap_membership.csv（前 500 名）、config/universe_mcap_membership_1500.csv（第 1001–1500 名確認樣本）
- fv5 與 fv5s 的建構程式（analysis/ls_turnover.py、ts_rank 合成的寫法）

## 檢定計畫（看結果前固定）

- 樣本：前 500 名，2019-03 ~ 2026-04 的每月營收換倉月（約 86 個月），兩段 2019–2022 / 2023–2026/04；確認樣本為第 1001–1500 名（未用於任何 SUE 變形的選擇）；第 501–1000 名只報告；2026-05 以後不用。
- 訊號：EAR = 個股還原價報酬（m 月第一個交易日的前一交易日收盤 → fv5 進場日前一交易日收盤）減同產業等權平均。只用到進場前一日的資料。
- 控制變數：SUE、營收創新高、PRE（m−1 月公告期之後到 m−1 月最後交易日的產業調整報酬）、log 市值；全部轉成產業內百分位。
- H1（統計）：每月橫斷面迴歸，被解釋變數為進場日收盤起 60 個交易日的產業調整報酬（產業內百分位），Fama-MacBeth，Newey-West 落後 3（持有期重疊）。方向 s 取 2019–2022 前 500 名 EAR 係數的正負號（事前預期為正）。通過條件：2023–2026/04 同號且 t ≥ 1.5；全期 |t| ≥ 2.58（本批 5 張卡 Holm 校正的最嚴門檻，α = 5%）；第 1001–1500 名同號且 t ≥ 2.0。
- H2（可交易，只在 H1 通過時做）：fv5 建構（前 500 名、產業內前／後 1/3 等權多空、借券條件 D、三份錯開、台指期對沖、單邊 0.29625% 成本、借券費）不變，分數改為 0.75 × SUE 產業內百分位 ＋ 0.25 × s·EAR 產業內百分位（權重比照 fv5s，事前固定、不做網格）。通過：兩段 Sharpe 都 ≥ fv5（1.45 / 1.87）、全期 ≥ 1.74、年換手增加 ≤ 20%。
- 只報告（不判定）：EAR 對 SUE 的殘差版本、EAR 五分組的 60 日報酬、EAR 與 1 日反轉訊號的相關、公告期內觸及漲跌停的比例、fv5x 合成版本。
- 資料窺探：SUE 與 EAR 的同期相關已在 revenue_surprise_report 看過；EAR 對進場後報酬的關係從未看過。sue_breakout 看過進場後兩日連漲的效果，本卡不使用進場後的價格。
- 未通過即停止；不改視窗長度、合成權重或持有期重測。若通過，只另立前瞻規格與 fv5 平行記錄，不改已登錄的 fv5 家族。

## 與已測點子的關係

- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5, SUE
- 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）（card:已測：未通過（階段 1 過、階段 2 t 2.8），research/ideas/I043-smallcap-multifactor-composite.md）：命中 合成, sue
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 營收創新高（÷ 前 24 個月最高）（effective，docs/revmom_persist_report.md）：命中 營收創新高
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 fv5
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- 美股大型科技公司財報反應對台股連結股的延遲傳遞（客戶／同業財報 → 台灣供應鏈）（card:已測：未通過，research/ideas/I016-us-earnings-to-taiwan-linked-stocks.md）：命中 earnings announcement return
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- fv5 的未定價風險對沖：在既有名單內調權重，讓多空組合對風格因子（動能、波動、價值、反轉、β）的報酬負荷歸零（card:已測：未通過，research/ideas/I049-fv5-unpriced-style-risk-hedge.md）：命中 fv5 建構
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:已測：未通過，research/ideas/I054-fv5-entry-execution-price.md）：命中 fv5
- 融券強制回補的價格壓力（I050 修訂版）：以官方停券日為事件日，在未看過的第 501–1500 名確認，處理 I056 附帶發現的資料窺探（card:已測：未通過（P2 t 1.3；I059 啟動條件成立），research/ideas/I058-forced-covering-oos-501-1500.md）：命中 第 1001–1500 名
- fv5 空方腿避開融券回補買壓：新空單若在 10 個交易日內遇到停券窗，延到最後回補日收盤再建倉（訊號與名單不變，只改建倉時點）（card:已測：未通過（只在 2023 年後有效），research/ideas/I059-fv5-short-defer-stop-window.md）：命中 fv5
- fv5 家族的稅後績效與除息日建倉規則：個人投資人股利所得稅與二代健保補充保費下，多方新倉延到除息後是否改善稅後報酬（card:已測：R1 未通過（稅後績效已報告），research/ideas/I061-fv5-after-tax-exdiv-entry.md）：命中 fv5
- 補充：與 sue_event_entry（依公告日提早進場，改的是進場時點）不同：本卡進場時點不變，只把公告期報酬當成第二個訊號。與 sue_breakout（進場後兩日連漲才加碼）不同：不使用進場後的價格。與 1 個月反轉（整月報酬、未拆公告期，兩段方向不一致）不同：把上月報酬拆成公告期與其餘期間分別處理。與 I036（法人公告前交易）不同：用價格反應而非法人買賣超。

研究點子，非投資建議。
