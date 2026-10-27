# I076 fv5 用平滑的月營收驚奇排序以降低換手：最近 3 個月 SUE 產業內百分位的平均取代單月 SUE（其餘建構不變）

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | A | 濾網或加權（fv5 排序分數修改，與 fv5 建構配對比較） | free | 約 0（前 500 名月營收、還原價、產業分類、借券、台指期已快取） | 2026-10-27 |

## 假設

把 fv5 的排序分數由當月 SUE 改為最近 3 個月 SUE 產業內百分位的平均（SUE3），年換手至少下降 20%，且年化淨報酬相對 fv5 提高至少 0.10 個百分點、兩段皆提高、兩段 Sharpe 都不低於 fv5，配對日報酬差 t ≥ 2.58。

## 機制（為什麼會有超額報酬）

fv5 的報酬來自 SUE 的 60 日以上漂移，成本來自每 3 個月整份資金重新排序時名單大幅更換。單月 SUE 有雜訊（一次性出貨、工作日、基期），排名逐月跳動；平均 3 個月的百分位提高分數的自我相關，讓仍屬高／低驚奇的股票續留，降低換手。若過去 2 個月的驚奇仍有漂移（文獻與本專案都顯示 SUE 的預測力延續 60 日以上），平滑幾乎不損失訊號，淨效果為正。這是成本面的改善，不是新的報酬來源。

## 出處

- （同儕審查）Novy-Marx、Velikov（2016）A Taxonomy of Anomalies and Their Trading Costs，Review of Financial Studies 29(1)，https://doi.org/10.1093/rfs/hhv063：依摘要，單邊月換手低於 50% 的異常多數扣成本後仍顯著，降低成本的方法中以買進與續抱門檻不同（緩衝）最有效
- （本專案）docs/ls_turnover_report.md：fv3 時期每 3 個月換倉把年換手從 21 倍降到 9 倍、Sharpe 0.49 / 1.16 升到 0.79 / 1.85；緩衝（前 1/2 續抱）再降到 7.1 倍，但 Sharpe 與無緩衝相當
- （本專案）docs/revmom_persist_report.md：3 個月年增率單獨的 20 日 IC +0.037 / +0.051，與 SUE 相近，但與 SUE 各半合成未勝過 SUE；本卡不是加入新訊號，而是平滑同一個 SUE
- （本專案）docs/revenue_surprise_report.md：SUE 的 60 日 IC 大於 20 日，漂移延續

## 台股適用性

直接針對台股的成本結構：證交稅 0.3% 讓每次換倉的成本比美股高很多，fv5 的淨績效對換手敏感（I054、I064 都是成本決定成敗）。資料全在快取，建構程式可沿用。風險是 SUE 最極端的新驚奇（I054 發現最極端 10% 有持續漂移）會被平均稀釋，進場變慢；另外 fv3 時期的緩衝結果顯示降低換手不一定提高 Sharpe。

## 所需資料

- FinMind TaiwanStockMonthRevenue（已快取）：SUE 與 SUE3
- FinMind TaiwanStockPrice、TaiwanStockSecuritiesLending、TaiwanFuturesDaily（已快取）：fv5 建構
- analysis/ls_turnover.py、analysis/borrow_capacity.py：fv5 建構與換手、成本計算

## 檢定計畫（看結果前固定）

- 樣本：前 500 名，2019-01 ~ 2026-04，兩段 2019–2022 / 2023–2026/04；2026-05 以後不用。
- 訊號：SUE3 = 換倉日時最近已公告 3 個月（m、m−1、m−2）SUE 的產業內百分位平均；只有 2 個月可用時取 2 個月平均，只有 1 個月則用單月。SUE 定義與 fv5 完全相同。
- 建構：只把排序分數由 SUE 換成 SUE3；產業內前／後 1/3 等權、三份錯開每 3 個月換倉、借券條件 D、台指期對沖、成本（單邊 0.29625%、借券費）全部照 fv5。
- 通過標準（計入本批 Holm）：年換手相對 fv5 下降 ≥ 20%；fv5-SUE3 相對 fv5 的年化淨報酬差 ≥ +0.10 個百分點、兩段差皆 > 0；兩段 Sharpe 皆不低於 fv5（1.45 / 1.87）；配對日報酬差全期 Newey-West t ≥ 2.58。四項都要成立。
- 只報告：扣成本前的報酬差（分辨是訊號變好還是成本變少）；加權平均 0.5 / 0.3 / 0.2 版本；fv5 架構下的緩衝（新進場前 1/3、續抱前／後 1/2）；fv5x 換成 SUE3；第 501–1000 名與第 1001–1500 名 SUE3 相對 SUE 的 60 日產業內 IC 差（統計版，不交易）。
- 資料窺探：SUE 本身已看過很多次，3 個月年增率與緩衝在 fv3 看過（結果平淡）；SUE3 在 fv5 架構下的結果沒看過。通過也只作為前瞻規格候選，由使用者決定是否另立平行記錄（I053 顯示平行比較檢定力低，應優先考慮直接以成本差判定）。
- 本批 Holm 校正（5 張卡、α = 5%、雙尾）：依 p 值由小到大的門檻為 t ≥ 2.58、2.50、2.39、2.24、1.96。未通過即停止，不改平均月數或權重重測。

## 與已測點子的關係

- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 月營收驚奇, sue, 營收驚奇
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5, SUE, 月營收驚奇
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue, 月營收驚奇
- 金融股自結盈餘驚奇的低換手多空（緩衝換倉）（card:已測：未通過，research/ideas/I017-financial-esue-low-turnover-ls.md）：命中 換手, turnover
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 月營收驚奇, sue
- 用股票期貨執行 fv5：以期交稅取代證交稅、以期貨空單取代借券（card:停止：追蹤誤差未過，research/ideas/I031-fv5-single-stock-futures-execution.md）：命中 交易成本, transaction costs
- 金融股自結盈餘驚奇低換手多空（緩衝換倉）（failed，docs/fin_esue_followup_report.md）：命中 換手
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 當沖比（dt20、dtjump）（failed，docs/daytrading_report.md）：命中 turnover
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 fv5
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）（card:已測：未通過（階段 1 過、階段 2 t 2.8），research/ideas/I043-smallcap-multifactor-composite.md）：命中 sue
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:已測：未通過，research/ideas/I054-fv5-entry-execution-price.md）：命中 fv5
- fv5 空方腿避開融券回補買壓：新空單若在 10 個交易日內遇到停券窗，延到最後回補日收盤再建倉（訊號與名單不變，只改建倉時點）（card:已測：未通過（只在 2023 年後有效），research/ideas/I059-fv5-short-defer-stop-window.md）：命中 fv5
- fv5 家族的稅後績效與除息日建倉規則：個人投資人股利所得稅與二代健保補充保費下，多方新倉延到除息後是否改善稅後報酬（card:已測：R1 未通過（稅後績效已報告），research/ideas/I061-fv5-after-tax-exdiv-entry.md）：命中 fv5
- 月營收驚奇在產業庫存循環下的條件效果：產業存貨相對營收處於自身高檔時，SUE 漂移是否較強（card:待確認，research/ideas/I067-sue-industry-inventory-cycle.md）：命中 營收驚奇
- 月營收的可預期季節性（Chang–Hartzmark–Solomon–Soltes 台股月頻版）：即將公告的月份歷來是營收旺月的股票，公告期報酬較高（card:待確認，research/ideas/I072-revenue-seasonality-announcement-return.md）：命中 月營收
- fv5 持股遇到反向季報反應即出場：多單 QEAR 落在後 1/3、空單 QEAR 落在前 1/3 時，在公告後第 +3 日收盤平倉（名單與換倉日不變，只加事件出場）（card:待確認，research/ideas/I074-fv5-qear-contrary-exit.md）：命中 低換手
- 補充：與 I017（金融股自結盈餘緩衝換倉，未通過）不同：本卡用全部前 500 名的 SUE、在 fv5 架構下平滑分數而非加緩衝帶。與 3 個月年增率（failed，與 SUE 各半合成）不同：本卡不加新訊號，只平均同一個 SUE 的百分位。與 I021（SUE 連續性，接近）不同：I021 測同號連串的交互作用，本卡只關心換手與淨報酬。

研究點子，非投資建議。
