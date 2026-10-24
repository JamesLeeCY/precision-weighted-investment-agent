# I060 現金股利發放日的再投資買壓（Hartzmark–Solomon 台股版）：大額發放日的加權指數報酬較高，以台指期執行

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 擇時（大盤，台指期執行；事前排定的資金流日期） | free | 約 700（TaiwanStockDividend：2019–2026 前 500 名成員 776 檔中缺約 690 檔，每檔一次可取全歷史；主要 ETF 約 15 檔）；加權報酬指數 2007 年起已快取；台指期近月已快取 | 2026-10-24 |

## 假設

以全市場當日現金股利發放金額 ÷ 前一日總市值排名，發放金額最大的 20% 交易日（含 ETF 配息），加權報酬指數在發放日與次一日（t、t + 1）的 2 日報酬，高於沒有發放的交易日；控制年 × 月固定效果後，發放金額係數在 2007–2018、2019–2022、2023–2026/04 三段皆 > 0、合併 t > 2。

## 機制（為什麼會有超額報酬）

可預期、與基本面無關的資金流：股利在除息日後約 3–4 週的固定日期入帳，日期在除息前就公告；部分投資人（存股族、領息再投入、基金）把現金再買回股票，形成買壓。在需求曲線向下傾斜時，總體價格會短暫上升。Hartzmark 與 Solomon 估計市場層級的價格乘數約 1.9（AER 版本摘要）。台股現金股利占市值比例高、且發放日集中在 7–10 月（台積電改為季配），每日發放金額的差異很大，適合用日頻變化識別，並以年 × 月固定效果排除『7 月效應』等季節性。

## 出處

- （同儕審查）Hartzmark 與 Solomon（2025）Market-Wide Predictable Price Pressure，American Economic Review，DOI 10.1257/aer.20231725；工作論文版 Predictable Price Pressure，NBER w30688，https://www.nber.org/papers/w30688：股利發放（數週前公告）的買壓預測較高的市值加權市場報酬，發放最多的五分位日報酬約為最低五分位的 4 倍；國際樣本也成立；再投資比例高、流動性低時效果較強（依摘要，未讀全文，未確認是否含台灣）
- （工作論文摘要）Chicago Booth Review 的介紹，https://www.chicagobooth.edu/review/dividend-payouts-lead-stock-price-bumps：作為摘要的輔助說明（媒體等級）
- （本專案）docs/timing_oos_report.md、docs/vix_timing_report.md、docs/fut_inst_timing_report.md：均線、VIX、外資期貨部位等大盤擇時皆未通過；本卡的訊號是事前排定的資金流日期，不是價格或情緒指標

## 台股適用性

制度與資料都適用：FinMind TaiwanStockDividend 有 CashDividendPaymentDate、每股現金股利與參與分派股數（已確認 2330 有 2005 年起的紀錄），可直接算每日發放金額；ETF（0050、0056、00878、00919 等）的配息也有發放日。台灣差異：外資持股約四成，外資收到股利可能匯出而非再投入，乘數可能比美國小；存股族與高股息 ETF 投資人眾多，再投入比例可能較高。沒有台灣的直接實證（AER 論文摘要只說國際成立），屬 B。可交易性好：台指期來回約 0.01%，每年約 50 個高發放日。

## 所需資料

- FinMind TaiwanStockDividend：CashDividendPaymentDate、CashEarningsDistribution + CashStatutorySurplus、ParticipateDistributionOfTotalShares（每日發放金額）、CashExDividendTradingDate（控制同日除息）、AnnouncementDate（確認發放日事前可知）
- FinMind TaiwanStockTotalReturnIndex（TAIEX，2007-01 起已快取）：日報酬
- FinMind TaiwanFuturesDaily（已快取）：台指期可交易版本
- config/universe_mcap_membership.csv 的市值：每日總市值分母（2019 年前用 TaiwanStockPrice × 股數近似，或以加權指數市值代替）
- 既有程式：analysis/timing_oos.py（樣本內外）、analysis/timing_futures.py（台指期執行）

## 檢定計畫（看結果前固定）

- 前置（不看報酬）：(1) 發放金額涵蓋率：2019–2025 每年本卡算出的現金股利總額 ÷ 證交所＋櫃買公布的全市場現金股利總額（或以前 500 名市值占比近似）需 ≥ 85%；2007–2018 只用當時存在且在檔案中的股票，報告涵蓋率，不足 70% 的年份剔除。(2) 發放日事前可知：抽 200 筆，AnnouncementDate 早於發放日 ≥ 5 個交易日的比例需 ≥ 95%。
- 訊號：D_t = 發放日為 t 的現金股利總額（股票＋ETF）÷ t − 1 日總市值（單位：基點）；每年把所有交易日依 D_t 排名，Q5 = 前 20% 交易日，Q0 = D_t = 0 的交易日。
- 報酬：加權報酬指數 R = r_t + r_{t+1}（t − 1 日收盤到 t + 1 日收盤）；次要（只報告）：只看 r_t、只看 r_{t+1}、以及 t + 2 ~ t + 5 的反轉。
- 迴歸：R = b × D_t + 同日除息金額 ÷ 市值 + 星期虛擬變數 + 期貨結算日虛擬變數 + 年 × 月固定效果，Newey-West（落後 5）。
- 樣本與資料窺探：三段 2007–2018（本專案的均線擇時曾用過這段指數報酬，但從未與股利發放日一起看過）、2019–2022、2023–2026/04；2026-05 以後不用。不加入其他控制變數或改視窗重測。
- 通過標準：b 在三段皆 > 0、合併 t > 2；Q5 − Q0 的平均 R 在 2019–2022 與 2023–2026/04 皆 > 0。計入本批 Holm 校正。
- 可交易版本（訊號通過才判定）：Q5 日（發放日事前已知）於 t − 1 日收盤買進 1 口等值台指期、t + 1 日收盤平倉，其他時間空手；成本單邊 0.005% 加 1 檔滑價；年化淨報酬三段皆 > 0。另報告作為 fv5 台指期對沖的覆蓋：Q5 日把對沖比例降 20%（只報告，不判定）。
- 附帶（只報告）：個股層級——前 500 名發放股票在發放日 [p, p + 4] 的產業調整 CAR，依外資持股比例（低 = 散戶多）與殖利率分組，檢查是否為自身股票再投入；以及與『除息後偏弱』（除息後 1–20 日）的重疊。

## 與已測點子的關係

- 高股息 ETF 換股（0056／00878／00919 等）公告後的價格壓力與生效後反轉（card:已測：未通過，research/ideas/I003-high-dividend-etf-rebalance.md）：命中 高股息 ETF, 價格壓力, price pressure
- 外資台指期／台指選擇權淨部位擇時（failed，docs/fut_inst_timing_report.md）：命中 台指期, 擇時
- 臺灣50（0050）季度換股：用市值排名事前預測納入／刪除（card:已測：未通過，research/ideas/I001-tw50-rebalance-predicted.md）：命中 市值排名, price pressure
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:已測：未通過，research/ideas/I054-fv5-entry-execution-price.md）：命中 執行, 價格壓力
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- 台指選擇權 Put/Call 比逆向擇時（candidate，docs/pcr_timing_report.md）：命中 擇時
- 高股息 ETF 換股（0056／00878／00919）（failed，docs/index_rebalance_report.md）：命中 高股息 etf
- 均線擇時（0050）（failed，docs/timing_oos_report.md）：命中 擇時
- MSCI 季度調整：台股標準指數納入／刪除的公告到生效效果（card:已測：勉強通過（候選），research/ideas/I002-msci-taiwan-rebalance.md）：命中 price pressure
- 外資台指期／台指選擇權淨部位：大盤擇時（台指期執行）（card:已測：未通過，research/ideas/I013-foreign-futures-options-positions-timing.md）：命中 台指期
- 台指選擇權 Put/Call 比（成交量與未平倉）：逆向情緒擇時（card:已測：未通過（接近，建議前瞻記錄），research/ideas/I014-txo-put-call-ratio-timing.md）：命中 擇時
- PTT 股版討論量暴增（相對自身歷史）：散戶注意力代理，Google 搜尋熱度為穩健性（card:已測：未通過，research/ideas/I041-ptt-discussion-surge-attention.md）：命中 股版
- 中小型股（市值第 501–1000 名）執行面前置檢查：容量、滑價、漲跌停、借券與避險工具（card:已測：L2、S 未過（只做統計檢定），research/ideas/I042-smallcap-execution-precheck.md）：命中 執行
- 融券強制回補的價格壓力（I050 修訂版）：以官方停券日為事件日，在未看過的第 501–1500 名確認，處理 I056 附帶發現的資料窺探（card:待確認，research/ideas/I058-forced-covering-oos-501-1500.md）：命中 price pressure
- fv5 空方腿避開融券回補買壓：新空單若在 10 個交易日內遇到停券窗，延到最後回補日收盤再建倉（訊號與名單不變，只改建倉時點）（card:待確認，research/ideas/I059-fv5-short-defer-stop-window.md）：命中 price pressure
- 補充：大盤擇時是已失敗的大類（均線、VIX、外資期貨部位；Put/Call 比接近），但本卡的訊號是事前公告的發放日期造成的資金流，機制與價格／情緒擇時不同，且有 AER 等級證據；與『除息後偏弱』（partial）不同：除息日是權利歸屬，發放日是現金入帳，兩者約相隔 3–4 週。執行用台指期，成本約為股票的 1/60。

研究點子，非投資建議。
