# I059 fv5 空方腿避開融券回補買壓：新空單若在 10 個交易日內遇到停券窗，延到最後回補日收盤再建倉（訊號與名單不變，只改建倉時點）

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 濾網或加權（fv5 建倉時點規則，與 fv5 建構配對比較） | free | 約 0（停券註記、借券、價格皆已快取）；除權息公告日用 TaiwanStockDividend，與 I058、I060、I061 共用約 690 次 | 2026-10-24 |

## 假設

在 fv5（前 500 名、借券放空）中，換倉日新建的空單若其下一個停券窗第一天 s 落在未來 10 個交易日內且事前可知，改為 s 日收盤才放空（期間以 β × 台指期空單暫代），年化淨報酬比現行 fv5 高至少 0.10 個百分點，兩段皆為正，Sharpe 兩段都不降低。

## 機制（為什麼會有超額報酬）

制度造成的可預期買壓：融券強制回補使股票在最後回補日前幾天相對大盤上漲（I056 附帶發現：前 500 名 +0.72%／5 日），fv5 的空方用借券、不受強制回補，但仍承受這段價格壓力。只延後『新』空單的建倉不增加股票交易次數（已持有的空單不動，因為先回補再放空的來回成本 0.59% 接近買壓幅度），代價只有幾天的台指期暫代追蹤差。

## 出處

- （本專案，已看過）docs/fv5_short_margin_report.md：前 500 名 8,016 次停券事件，回補日前 5 日相對大盤 +0.72%；S1 版本用台指期暫代停券期間的空單，追蹤差每年多付 0.83%（表示空方股票在停券期間確實相對上漲）
- （本專案）docs/fv5_forward_power_execution_report.md（I054）：換倉改隔日開盤、均價或分批都較差，原因是 SUE 最極端股換倉後仍漂移——本卡只延後落在停券窗前的新空單，需檢查是否同樣錯過空方漂移
- （學位論文，台灣）何彥萩（2021）淡江大學碩士論文，https://www.airitilibrary.com/Article/Detail/U0002-2806202123144600：最後回補日前 10 日與當日正異常報酬、其後反轉（依摘要）
- （同儕審查）Short Covering Trades（2018），JFQA，https://doi.org/10.1017/s0022109017001193：回補交易造成正的價格反應、只部分反轉（依摘要）

## 台股適用性

停券窗只存在於台股的融券制度；fv5 每月換倉（三份錯開），股東常會停券集中在 3–4 月、除權息停券在 6–9 月，與 3、4、6–9 月的換倉日（營收公告期限次一交易日，約每月 11–13 日）部分重疊。效果幅度上限可粗估：受影響的新空單比例 × 每筆約 0.7%，預期年化改善只有 0.1–0.3 個百分點，所以門檻設得低，但要求兩段同號與配對差顯著。

## 所需資料

- FinMind TaiwanStockMarginPurchaseShortSale（已快取）：Note 的 X 註記（停券窗）
- FinMind TaiwanStockDividend：AnnouncementDate（判斷除權息類停券窗在換倉日是否已可知）
- 前一年同類停券窗日期（由快取資料推得）：股東常會類的事前預測
- 既有程式：analysis/fv5_short_margin.py（停券窗、β × 台指期暫代的寫法）、analysis/hedge_construction.py、analysis/ls_turnover.py（fv5 建構）

## 檢定計畫（看結果前固定）

- 啟動條件（事前固定）：只有在 I058 的『無條件複製』成立時才執行——第 501–1000 名全部停券事件 CAR[s − 4, s]（市場調整）> 0 且 t > 2。理由：前 500 名的 +0.72% 已看過，必須先在未看過的樣本確認買壓存在；I058 的強度梯度是否通過不影響本卡（本規則只依賴平均買壓）。
- 事前可知的定義：換倉日 d 時，除權息類停券窗需 AnnouncementDate ≤ d；股東常會類用『前一年同類窗 s 加 52 週』預測 ŝ，若 d < ŝ ≤ d + 10 個交易日則延到 ŝ + 3 日收盤（涵蓋 ±3 日誤差）；其餘不延後。回測不得使用 d 之後才公布的資訊。
- 規則 R：只作用在 d 日新建或加碼的空單；延後期間該部位以 β × 台指期空單暫代（期貨 0.005%）；已持有的空單、多方腿、權重、名單都不變。
- 比較：fv5（S0）vs fv5 + R，2019–2022 / 2023–2026/04，扣成本與借券費（借券費依實際持有天數）；同時報告 fv5x（fv5e + fv5s + fv5v）+ R（只報告）。
- 指標：年化淨報酬差、兩段 Sharpe、最大回撤、受影響的新空單比例與平均延後天數；每次換倉的配對報酬差 Newey-West t（落後 2）。另報告被延後部位在延後期間的『股票 − β × 台指期』報酬（即省下的買壓），以及延後後 20 日的空方漂移是否受影響。
- 通過標準：年化淨報酬差 ≥ +0.10 個百分點、兩段皆 > 0、兩段 Sharpe 都不低於 S0、配對差 t > 2；計入本批 Holm 校正。
- 資料窺探與決策：前 500 名的效果已部分看過，回測通過只作為『是否把 R 加入前瞻執行規則』的依據，由使用者決定；不改寫已登錄的 fv5 家族紀錄，也不另立第六個平行前瞻（I053 顯示平行比較檢定力很低）。若加入，以 2027 年股東常會季（3–4 月）起的 live 紀錄報告實際省下的買壓。
- 未通過即停止；不改 K = 10 日或 ŝ ± 3 日重測。

## 與已測點子的關係

- fv5 空方腿改以融券為主、借券補足：借券費與強制回補成本的取捨（訊號與名單不變）（card:已測：未通過（保守情境 +0.41%），research/ideas/I056-fv5-short-leg-margin-vs-sbl.md）：命中 融券, 借券, 空方腿, 強制回補, 停券, 最後回補日
- 融券強制回補的價格壓力（I050 修訂版）：以官方停券日為事件日，在未看過的第 501–1500 名確認，處理 I056 附帶發現的資料窺探（card:待確認，research/ideas/I058-forced-covering-oos-501-1500.md）：命中 融券強制回補, 最後回補日, 停券, forced short covering, short covering, price pressure
- 股東會與除權息前的融券強制回補：高融券股在最後回補日前的價格壓力、其後反轉，以及對 fv5 空方腿的影響（card:待確認，research/ideas/I050-margin-short-forced-covering.md）：命中 融券強制回補, 最後回補日, forced short covering
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 execution, fv5
- 借券賣出餘額比、借券費率、增量、需求量（partial，docs/lending_legs_report.md）：命中 借券
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 外資台指期／台指選擇權淨部位擇時（failed，docs/fut_inst_timing_report.md）：命中 台指期
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 fv5
- 借券賣出餘額比相對自身歷史（ts_rank）——與 SUE 合成（effective，docs/ts_rank_report.md）：命中 借券
- 券資比、融券增量（failed，docs/leg_pool_report.md）：命中 融券
- 臺灣50（0050）季度換股：用市值排名事前預測納入／刪除（card:已測：未通過，research/ideas/I001-tw50-rebalance-predicted.md）：命中 price pressure
- MSCI 季度調整：台股標準指數納入／刪除的公告到生效效果（card:已測：勉強通過（候選），research/ideas/I002-msci-taiwan-rebalance.md）：命中 price pressure
- 高股息 ETF 換股（0056／00878／00919 等）公告後的價格壓力與生效後反轉（card:已測：未通過，research/ideas/I003-high-dividend-etf-rebalance.md）：命中 price pressure
- 外資台指期／台指選擇權淨部位：大盤擇時（台指期執行）（card:已測：未通過，research/ideas/I013-foreign-futures-options-positions-timing.md）：命中 台指期
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5
- 中小型股（市值第 501–1000 名）執行面前置檢查：容量、滑價、漲跌停、借券與避險工具（card:已測：L2、S 未過（只做統計檢定），research/ideas/I042-smallcap-execution-precheck.md）：命中 借券
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:已測：未通過，research/ideas/I054-fv5-entry-execution-price.md）：命中 fv5
- 補充：承接 I050 原卡的『fv5 空方腿附帶檢定』並改為獨立卡。與 I056（融券取代借券，未通過）不同：本卡不換放空工具、不增加來回交易，只延後新空單。與 I054（換倉執行價格，未通過）不同：I054 是全部持股都改成交時點，本卡只影響落在停券窗前的少數新空單；要另外報告是否錯過 SUE 空方漂移。

研究點子，非投資建議。
