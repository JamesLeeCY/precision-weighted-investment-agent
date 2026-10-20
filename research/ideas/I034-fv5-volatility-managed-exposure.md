# I034 fv5 因子層級的波動率管理：依多空組合自身近期波動調整總曝險

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | C | 擇時（多空因子曝險，樣本內外） | free | 0（只用 fv5 回測的每日報酬序列） | 2026-10-20 |

## 假設

依 fv5 多空組合前 21 個交易日的實現變異數（或下檔變異數）反向調整下一個月的總曝險（上限 1.5 倍、下限 0.5 倍，縮放常數只用過去資料估計），扣成本後兩段 Sharpe 都比未調整的 fv5 高 0.1 以上，且最大回撤不變大。

## 機制（為什麼會有超額報酬）

Moreira 與 Muir（2017）認為因子的波動可預測、但報酬不隨波動等比例上升，所以高波動時降曝險可提高 Sharpe。反面證據很強：Cederburg 等（2020）在 103 個策略的即時樣本外比較中，波動管理版本通常沒有勝過原版，只在動能、獲利能力與 BAB 等少數因子有幫助；Wang 與 Yan（2021）認為只用下檔波動較好。本專案已在 0050 上測過 VIX／實際波動的曝險管理（無效），但 fv5 是市場中性的多空因子，波動來源（產業擁擠、空方軋空）與大盤不同。

## 出處

- Cederburg, O'Doherty, Wang & Yan（2020）On the Performance of Volatility-Managed Portfolios，Journal of Financial Economics 138:95–117，https://www.lehigh.edu/~xuy219/research/COWY.pdf：103 個股票策略中，可即時執行的波動管理版本通常沒有勝過原版，樣本外 Sharpe 與確定等值報酬多半較低（摘要與二手摘要）【同儕審查】
- Alpha Architect 對上文的摘要，https://alphaarchitect.com/the-performance-of-volatility-managed-portfolios/：波動管理對動能、獲利能力、BAB 有幫助，其他六個常用因子沒有【部落格】
- Wang & Yan（2021）下檔波動管理，Journal of Banking and Finance，https://www.lehigh.edu/~xuy219/research/Downside.pdf：用下檔波動縮放的即時表現優於總波動（二手摘要，未讀全文）【同儕審查】
- Moreira & Muir（2017）Volatility-Managed Portfolios，Journal of Finance：高波動時降曝險可提高多數因子的 Sharpe（經上述文獻轉述，本次未讀原文）【同儕審查，未讀摘要】
- 本專案 docs/vix_timing_report.md：0050 的 VIX／實際波動曝險管理扣成本前就接近 0【本專案實證】

## 台股適用性

可用台指期與現股同時縮放，但 fv5 的縮放要動到多空兩腿，成本是現股成本（每調 10% 曝險約付 0.03% 的單邊成本 × 兩腿），不是期貨成本；若 I031 通過，可改用股票期貨縮放。沒有找到台股多空因子的波動管理研究。fv5 回測只有約 88 個月，縮放常數的估計誤差大，這也是 Cederburg 等指出的失敗原因。

## 所需資料

- fv5 建構的每日淨報酬（由已快取資料重建，analysis/ls_turnover.py 一類）

## 檢定計畫（看結果前固定）

- 樣本：fv5 前 500 名每日淨報酬，2019-01 ~ 2026-04；兩段 2019–2022 / 2023–2026/04；2026-05 以後不使用。前 12 個月只用來初始化，正式比較從 2020-01 起（兩段改為 2020–2022 / 2023–2026/04，fv5 基準同期重算）。
- 版本（只有這兩個）：M1 總波動：曝險_t = c_t ÷ 前 21 日實現變異數；M2 下檔波動：只用負報酬日計算變異數。c_t 用到 t−1 為止的擴張視窗估計，使未截斷前的平均曝險等於 1；曝險每月在換倉日調整一次，截在 0.5–1.5 倍。
- 成本：曝險變動 × 兩腿 × 單邊 0.29625%；放大時多借的股數套用可借條件 D，借不到的部分不放大；借券費依實際曝險計。
- 通過標準：M1 或 M2 兩段 Sharpe 都比同期 fv5 高 ≥ 0.10，且最大回撤不大於 fv5；同時 Cederburg 式的直接比較（同平均曝險下的報酬差）全期 t > 1.5。事前指定 M2 為主版本（依 Wang 與 Yan）。
- 只報告：fv5 月報酬對前月實現波動的預測迴歸（報酬是否隨波動上升）；高、低波動月的平均報酬；只用 2026-05 起前瞻資料的觀察（不判定）。

## 與已測點子的關係

- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 外資台指期／台指選擇權淨部位擇時（failed，docs/fut_inst_timing_report.md）：命中 擇時
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- 台指選擇權 Put/Call 比逆向擇時（candidate，docs/pcr_timing_report.md）：命中 擇時
- 均線擇時（0050）（failed，docs/timing_oos_report.md）：命中 擇時
- 台指 VIX 擇時與波動率管理（failed，docs/vix_timing_report.md）：命中 波動率管理
- 台指選擇權 Put/Call 比（成交量與未平倉）：逆向情緒擇時（card:已測：未通過（接近，建議前瞻記錄），research/ideas/I014-txo-put-call-ratio-timing.md）：命中 擇時
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5
- 補充：與已測點子的差別：vix_timing 對象是 0050（大盤），本卡對象是市場中性的 fv5 多空組合。列 C 的理由：文獻的即時樣本外證據偏負面、樣本只有約 7 年、且縮放要付現股成本；只有在 I031（股票期貨執行）通過、縮放成本變低時才值得先做。

研究點子，非投資建議。
