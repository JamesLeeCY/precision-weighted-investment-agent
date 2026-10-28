# I080 台指期扣除預期股息後的超額逆價差（期貨 carry）：做多台指期、放空等值大盤現貨的報酬是否平均為正，及其對 fv5 對沖成本與 0050 部位的含意

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 擇時（期貨基差 carry，市場中性；台指期執行） | free | 約 10（台指期 2018-06 ~ 2018-12 約 1 次、0050 借券費約 8 次；加權指數價格與含息報酬、0050 價格、前 1500 名股利與股數已快取） | 2026-10-28 |

## 假設

扣除事前已公告的成分股現金股利點數與資金成本後，台指期近月平均仍低於理論價；因此「做多台指期、放空等值加權指數（含息）」的日報酬全期平均為正，Newey-West t 達本批 Holm 門檻、兩段皆 > 0，且調整後折價最深的三分之一期間報酬最高。

## 機制（為什麼會有超額報酬）

避險壓力與套利限制。外資與自營商持有大量現股，常以放空台指期避險，形成持續的賣方壓力；反向套利（買期貨、放空一籃子現股）在台股成本高：借券費、平盤下放空限制，以及融券在除權息與股東會前強制回補，偏偏除息旺季（6–8 月）是期貨折價最深的時候。若套利不足，期貨相對公平價的折價就是給多方的風險溢酬（carry）。對本專案有兩個用途：(1) fv5 以放空台指期對沖剩餘 β，若台指期長期偏便宜，對沖本身每年有成本，可改用放空 0050；(2) 若折價夠大且穩定，「多台指期、空 0050」是與 fv5 幾乎無關的獨立報酬來源，期貨成本只有約 0.005%。

## 出處

- （同儕審查）Koijen、Moskowitz、Pedersen、Vrugt（2018）Carry，Journal of Financial Economics 127(2): 197–225，工作論文版 https://www.nber.org/papers/w19325：依摘要，以期貨價格相對現貨推得的 carry 能預測多種資產類別（含股價指數期貨）的報酬
- （同儕審查，台灣；期刊卷期未讀到）許溪南、吳依正、黃金生，Estimation of TAIEX's Dividend Payouts and Impacts on the Pricing of TAIEX Index Futures，https://econ.ntpu.edu.tw/p/16-1001-928.php?Lang=en：依摘要，台股改以現金股利為主後，台指期常出現逆價差；未扣股息就視為套利機會會虧損；除息時間有明顯季節性，定價誤差隨時間縮小
- （碩士論文，台灣）政治大學 2020 年論文（胡），除息旺季對台指期轉倉價差與基差收斂的影響，https://thesis.lib.nccu.edu.tw/detail/cefeb5ce450f0c520f1a3dfafcf84282/：依搜尋摘要，以基差收斂建立策略回測；全文未讀到，未引用數字
- （部落格）CMoney 筆記，https://www.cmoney.tw/notes/note-detail.aspx?nid=15001：統計台指期平均逆價差約 0.31%（樣本與是否扣股息未說明），只作為現象描述

## 台股適用性

台指期是全球流動性最高的單一國家指數期貨之一，成本約 0.005%，可交易性沒有問題。關鍵是股息調整：台股現金股利集中在 6–9 月，未調整的逆價差大部分只是股息；本卡用每檔成分股事前公告的除息日與股利金額計算預期股息點數，只看扣除後剩下的部分。限制：(1) FinMind 免費的台指期從 2018-06 起，樣本約 8 年、95 個結算月；(2) 現貨收盤 13:30、期貨日盤 13:45，日報酬有 15 分鐘時差，主判定用日報酬平均（時差只增加雜訊），穩健性用結算日到結算日的月報酬；(3) 實際放空現貨只能用 0050（前 50 大），與加權指數有追蹤差。

## 所需資料

- FinMind TaiwanFuturesDaily TX（2019 起已快取）：近月與次月價格、結算日
- FinMind TaiwanStockPrice TAIEX、TaiwanStockTotalReturnIndex TAIEX（已快取）：現貨與含息報酬
- FinMind TaiwanStockDividend（前 1500 名已快取）：現金股利、CashExDividendTradingDate、AnnouncementDate，用來算事前可知的預期股息點數
- FinMind TaiwanStockShareholding NumberOfSharesIssued 與價格（已快取）：成分股市值與指數除數
- FinMind TaiwanStockPrice 0050（已快取）與 TaiwanStockSecuritiesLending 0050（約 8 次）：可交易版本的放空腿成本

## 檢定計畫（看結果前固定）

- 樣本：2018-07 ~ 2026-04 每日，兩段 2018-07 ~ 2022 / 2023 ~ 2026/04；2026-05 以後不用。
- 預期股息點數 D̂(t, T)：上市成分股中，AnnouncementDate ≤ t 且現金除息交易日落在 (t, 近月結算日 T] 的現金股利 × 已發行股數，加總後除以指數除數（除數 = 前一日上市成分股總市值 ÷ 加權指數）；檢查前 1500 名涵蓋的上市市值占比 ≥ 97%，不足則報告。
- 調整後基差 EB_t = [F_t − S_t × (1 + r × τ) + D̂] ÷ S_t，r 事前固定為 1.5%／年，τ 為到結算日的年數；EB < 0 代表期貨比公平價便宜。
- 主判定（計入本批 Holm）：c_t = 台指期近月日報酬（依 analysis/leg_probe.py 的 tx_continuous，以成交量最大的月份、換約不跳價）− 加權指數含息日報酬 + r／252。通過：全期平均 c > 0、Newey-West（落後 5）t 達 Holm 門檻、兩段平均皆 > 0；且 EB 三分組中最便宜組的平均 c 大於最貴組。
- 只報告：(a) 結算日到結算日的月頻版本；(b) r = 0% 與 2.5% 的敏感度；(c) 可交易市場中性版本：多台指期、空 0050（β 比率以前 250 日迴歸，扣 0050 實際借券費與單邊 0.29625%），全期與兩段 Sharpe、與 fv5 日報酬的相關；只在 EB < 0 時持有的條件版本；(d) fv5 的台指期對沖平均口數 × c 的年化成本，以及改放空 0050 對沖的差異；(e) 0050 長期持有 vs 台指期加現金（同曝險）的年化報酬差。
- 通過後的用途（事前約定）：若主判定通過且 (c) 兩段 Sharpe 皆 > 0.5，才以獨立部位另立點子卡；若只有主判定通過，只把結論用於 fv5 對沖工具與 0050 部位的執行選擇，不另立策略。
- 資料窺探：專案只用過台指期的報酬做對沖與擇時，從未計算股息調整後基差。未通過即停止，不改 r、股息估計方式或改用次月合約重測。
- 本批 Holm 校正（5 張卡、α = 5%、雙尾）：依 p 值由小到大的門檻為 t ≥ 2.58、2.50、2.39、2.24、1.96；單卡至少要過最嚴的 2.58 才保證通過，其餘依 Holm 逐步判定。

## 與已測點子的關係

- 外資台指期／台指選擇權淨部位：大盤擇時（台指期執行）（card:已測：未通過，research/ideas/I013-foreign-futures-options-positions-timing.md）：命中 台指期, TAIEX futures
- 股票期貨基差（期貨相對現貨的年化折溢價）：期貨折價深的股票之後報酬較差（隱含放空需求）（card:已測：未通過，research/ideas/I055-ssf-basis-implied-short-demand.md）：命中 基差, futures basis
- 現金股利發放日的再投資買壓（Hartzmark–Solomon 台股版）：大額發放日的加權指數報酬較高，以台指期執行（card:已測：未通過，research/ideas/I060-dividend-payment-reinvestment-pressure.md）：命中 現金股利, 台指期
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 外資台指期／台指選擇權淨部位擇時（failed，docs/fut_inst_timing_report.md）：命中 台指期
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 fv5
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- 臺灣50 季度換股（實際與事前預測名單）（failed，docs/index_rebalance_report.md）：命中 0050
- 臺灣50（0050）季度換股：用市值排名事前預測納入／刪除（card:已測：未通過，research/ideas/I001-tw50-rebalance-predicted.md）：命中 0050
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5
- 中小型股（市值第 501–1000 名）執行面前置檢查：容量、滑價、漲跌停、借券與避險工具（card:已測：L2、S 未過（只做統計檢定），research/ideas/I042-smallcap-execution-precheck.md）：命中 避險
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:已測：未通過，research/ideas/I054-fv5-entry-execution-price.md）：命中 fv5
- fv5 空方腿避開融券回補買壓：新空單若在 10 個交易日內遇到停券窗，延到最後回補日收盤再建倉（訊號與名單不變，只改建倉時點）（card:已測：未通過（只在 2023 年後有效），research/ideas/I059-fv5-short-defer-stop-window.md）：命中 fv5
- fv5 家族的稅後績效與除息日建倉規則：個人投資人股利所得稅與二代健保補充保費下，多方新倉延到除息後是否改善稅後報酬（card:已測：R1 未通過（稅後績效已報告），research/ideas/I061-fv5-after-tax-exdiv-entry.md）：命中 fv5
- 月底月初效應（turn of the month）以台指期執行：每月最後 1 個交易日到次月第 3 個交易日做多台指期，作為與 fv5 低相關的附加部位（card:已測：未通過，research/ideas/I071-turn-of-month-tx-futures.md）：命中 台指期
- fv5 延長持有期：每份資金持有 6 個月、六份錯開（每月換 1/6），以降低換手成本（訊號與名單規則不變）（card:待確認，research/ideas/I078-fv5-six-month-hold-six-tranches.md）：命中 fv5
- fv5 多方腿改用指數避險取代個股空方腿：台指期 ＋ 中型股指數（0051 代理）的滾動 β 避險，作為不需借券的容量延伸（card:待確認，research/ideas/I079-fv5-long-leg-index-hedge-capacity.md）：命中 fv5
- 補充：與 I055（股票期貨基差，failed）不同：I055 用個股期貨的折價當橫斷面選股訊號，本卡是指數期貨本身的報酬（期貨相對現貨），不選股。與 I013、I014、I060、I071（台指期擇時，failed）不同：那些是用外資部位、PCR、日曆預測大盤方向，本卡是多期貨、空現貨的市場中性部位，不押大盤方向。

研究點子，非投資建議。
