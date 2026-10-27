# I071 月底月初效應（turn of the month）以台指期執行：每月最後 1 個交易日到次月第 3 個交易日做多台指期，作為與 fv5 低相關的附加部位

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過 | B | 擇時（日曆效應，台指期執行；樣本內外以時間切分） | free | 約 0（加權報酬指數 2006-06 起、台指期 TX 2007 起逐日資料已快取） | 2026-10-27 |

## 假設

台股加權報酬指數在每月最後 1 個交易日到次月第 3 個交易日（[−1, +3]，共 4 個交易日）的平均日報酬高於其他交易日，差異在從未用於本專案擇時選擇的 2007–2018 年 t ≥ 2.58、2019–2022 與 2023–2026/04 兩段皆為正；只在這 4 日做多 1 倍台指期的策略，扣成本後 Sharpe 高於同平均曝險（約 19%）的固定持有。

## 機制（為什麼會有超額報酬）

文獻提出的解釋包括月底月初的薪資與退休金資金流入、機構月底作帳、以及短期利率與流動性的月週期；McConnell 與 Xu（2008）發現 35 國中 31 國有此現象，但在美國找不到成交量或基金淨流入在月初較高的證據，原因仍未定。台股可能的特殊來源：定期定額買進 ETF 與個股的扣款日（是否集中在月初未查證，需另行確認）。這是事前排定的日曆，不用預測任何變數，與 fv5（市場中性的選股）來源不同，所以適合當附加部位。

## 出處

- （同儕審查）McConnell、Xu（2008）Equity Returns at the Turn of the Month，Financial Analysts Journal 64(2): 49–64，https://ideas.repec.org/a/taf/ufajxx/v64y2008i2p49-64.html：依摘要，35 國中 31 國有月底月初效應，找不到成交量或基金流量較高的證據
- （同儕審查，經典）Lakonishok、Smidt（1988）Are Seasonal Anomalies Real? A Ninety-Year Perspective，Review of Financial Studies 1(4)，https://doi.org/10.1093/rfs/1.4.403：月底月初 [−1, +3] 視窗的定義出處（依常見引用，全文未讀）
- （學位論文，台灣）國立中央大學碩士論文（年份未確認）加權指數與產業指數的月底月初效應（2013–2022），https://ir.lib.ncu.edu.tw/handle/987654321/92722：依搜尋摘要，加權指數月初月底報酬較高但差異不顯著，部分產業指數顯著
- （業者分析，非同儕審查）Seasonax，In Other Global Markets the Turn-of-the-Month Effect Generates Even Bigger Returns than in the US，https://www.seasonax.com/in-other-global-markets-the-turn-of-the-month-effect-generates-even-bigger-returns-than-in-the-us：以 26 日到次月 5 日比較其他日期，台股月初月底報酬較高
- （本專案）docs/timing_futures_report.md：台指期執行擇時成本約每年 0.1%，但過去的訊號型擇時規則沒有勝過同曝險的固定比例

## 台股適用性

台指期單邊成本約 0.005%（加 1 點滑價），每月進出一次，成本約每年 0.2–0.3%，不會被證交稅吃掉。台指期每月第三個星期三結算，[−1, +3] 不跨結算，可固定使用近月；若次月第 3 個交易日剛好在結算日之後，則持有次近月（轉倉日固定在第三個星期三前一日）。學術證據在台股偏弱（中央大學論文 2013–2022 不顯著），業者分析較正面，所以本卡事前預期不高；優點是資料全部已快取、視窗由文獻固定、與 fv5 幾乎無關。風險：本專案的大盤擇時（均線、VIX、景氣燈號、外資部位、Put/Call、股利發放日）全部未通過。

## 所需資料

- FinMind TaiwanStockTotalReturnIndex TAIEX（已快取，2006-06 ~ 2026-05）：日報酬與交易日曆
- FinMind TaiwanFuturesDaily TX（已快取，2007 ~ 2026-05）：近月與次近月結算價、轉倉
- fv5 日淨報酬序列（analysis/fv5_family.py）：相關與組合

## 檢定計畫（看結果前固定）

- 樣本：2007-01 ~ 2026-04；主判定期 2007–2018（本專案從未用於擇時規則的選擇），報告期 2019–2022 / 2023–2026/04；2026-05 以後不用。
- 訊號：TOM 日 = 每月最後 1 個交易日到次月第 3 個交易日（以交易日計，事前由文獻固定，不搜尋其他視窗）。
- T1（統計，主判定）：加權報酬指數日報酬對 TOM 虛擬變數迴歸（Newey-West 落後 5），2007–2018 係數 t ≥ 2.58（本批 Holm 最嚴門檻）；2019–2022、2023–2026/04 係數皆 > 0。
- T2（可交易）：TOM 日前一交易日收盤買進 1 倍名目台指期、第 3 個交易日收盤平倉，其餘日空手；扣 0.005% 單邊成本加 1 點滑價、保證金閒置資金不計利息。通過：2019–2022 與 2023–2026/04 的 Sharpe 都高於同平均曝險的固定持有台指期，且年化報酬差 > 0。
- T3（組合，只報告不判定）：fv5 加上 0.5 倍名目的 TOM 附加部位，與 fv5 的 Sharpe 比較；TOM 策略與 fv5 日報酬相關。
- 只報告：[−3, +3]、[−1, +1] 視窗；月底前 5 日到月初後 5 日的逐日平均報酬；剔除 2008、2020、2022 年大跌月份的版本；台指期夜盤是否改變結果（夜盤 2017-05 起）。
- 資料窺探：本專案未看過任何日曆效應；I063 的 EAR 視窗以月底為起點，但經產業調整，與大盤日曆效應無關。未通過即停止，不搜尋其他視窗或其他月份。

## 與已測點子的關係

- 外資台指期／台指選擇權淨部位擇時（failed，docs/fut_inst_timing_report.md）：命中 台指期, 擇時
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日, calendar
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:已測：未通過，research/ideas/I054-fv5-entry-execution-price.md）：命中 執行, fv5
- 現金股利發放日的再投資買壓（Hartzmark–Solomon 台股版）：大額發放日的加權指數報酬較高，以台指期執行（card:已測：未通過，research/ideas/I060-dividend-payment-reinvestment-pressure.md）：命中 擇時, 台指期
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 員工人數成長（雇用率）（failed，docs/hiring_rate_report.md）：命中 薪資
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 fv5
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- 台指選擇權 Put/Call 比逆向擇時（candidate，docs/pcr_timing_report.md）：命中 擇時
- 均線擇時（0050）（failed，docs/timing_oos_report.md）：命中 擇時
- 外資台指期／台指選擇權淨部位：大盤擇時（台指期執行）（card:已測：未通過，research/ideas/I013-foreign-futures-options-positions-timing.md）：命中 台指期
- 台指選擇權 Put/Call 比（成交量與未平倉）：逆向情緒擇時（card:已測：未通過（接近，建議前瞻記錄），research/ideas/I014-txo-put-call-ratio-timing.md）：命中 擇時
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5
- 中小型股（市值第 501–1000 名）執行面前置檢查：容量、滑價、漲跌停、借券與避險工具（card:已測：L2、S 未過（只做統計檢定），research/ideas/I042-smallcap-execution-precheck.md）：命中 執行
- fv5 空方腿避開融券回補買壓：新空單若在 10 個交易日內遇到停券窗，延到最後回補日收盤再建倉（訊號與名單不變，只改建倉時點）（card:已測：未通過（只在 2023 年後有效），research/ideas/I059-fv5-short-defer-stop-window.md）：命中 fv5
- fv5 家族的稅後績效與除息日建倉規則：個人投資人股利所得稅與二代健保補充保費下，多方新倉延到除息後是否改善稅後報酬（card:已測：R1 未通過（稅後績效已報告），research/ideas/I061-fv5-after-tax-exdiv-entry.md）：命中 fv5
- 補充：與已失敗的大盤擇時（均線、VIX、景氣燈號、外資部位 I013、Put/Call I014、股利發放日 I060）不同：不需要任何預測變數，日期完全事前固定。與已失敗的季節性與季節性動能（橫斷面、同月份報酬）不同：本卡是大盤的月內日曆效應。I060 測的是股利發放日的資金流，本卡是每月固定的月底月初。

研究點子，非投資建議。
