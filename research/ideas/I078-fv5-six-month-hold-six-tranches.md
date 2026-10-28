# I078 fv5 延長持有期：每份資金持有 6 個月、六份錯開（每月換 1/6），以降低換手成本（訊號與名單規則不變）

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過 | A | 濾網或加權（fv5 執行方式修改：持有期與資金份數，與 fv5 建構配對比較） | free | 約 0（前 500 名月營收、還原價、產業分類、借券、台指期已快取） | 2026-10-28 |

## 假設

把 fv5 由「三份資金、每份持有 3 個月」改為「六份資金、每份持有 6 個月」（fv5-H6），年換手至少下降 30%，且年化淨報酬相對 fv5 提高至少 0.10 個百分點、兩段皆提高、兩段 Sharpe 都不低於 fv5，配對日報酬差 Newey-West t 達本批 Holm 門檻。

## 機制（為什麼會有超額報酬）

成本面的改善，不是新的報酬來源。fv5 每年交易成本約 2.7%（年換手約 9 倍 × 單邊 0.29625%），借券費約 1.8%。SUE 的 60 日 IC 大於 20 日，漂移延續到 60 日以上；若第 61–120 日的漂移仍為正，持有 6 個月只犧牲一小部分訊號新鮮度，卻能把換手大約減半。I076 平滑 SUE 失敗是因為把舊月份混進排序、新驚奇進場變慢；本卡仍用最新一個月的 SUE 排序，只是每份資金抱得更久，進場時的訊號不被稀釋，損失只來自持有後段的訊號衰減。fv3 時期換倉頻率 1→2→3 個月 Sharpe 單調上升，但 4–6 個月從未測過。

## 出處

- （同儕審查）Novy-Marx、Velikov（2016）A Taxonomy of Anomalies and Their Trading Costs，Review of Financial Studies 29(1)，https://doi.org/10.1093/rfs/hhv063：依摘要，月換手低於 50% 的異常在設計降成本後多數仍有顯著淨價差；降低換倉頻率與緩衝是主要的降成本方法
- （本專案）docs/ls_turnover_report.md：fv3 時期每 1／2／3 個月換倉 Sharpe 0.49 / 1.16 → 0.53 / 1.62 → 0.79 / 1.85，年換手 21 → 12 → 9 倍，交易成本 6.3% → 3.6% → 2.7%／年；更長持有期未測
- （本專案）docs/report_delay_smoothed_sue_report.md：I076 平滑 SUE 扣成本前少 1.52 個百分點、成本只省 0.32 個百分點；顯示稀釋進場訊號的代價高，本卡刻意不改排序分數

## 台股適用性

直接針對台股的成本結構：證交稅 0.3% 讓每次換倉成本高，fv5 的淨績效對換手敏感（I054、I064、I076 都由成本決定成敗）。月營收每月公告，六份錯開時每月仍有 1/6 資金用最新 SUE 換倉，新資訊進入組合的速度只比 fv5 慢一半。風險：(1) SUE 漂移若在 60 日後消失，持有後段等於持有無訊號的多空，報酬被稀釋；(2) 空方腿持有較久，遇到股東會與除權息、借券召回的次數增加；(3) 每份資金規模變為 1/6，個股部位變小，對 2 億資金的借券深度條件較寬鬆。

## 所需資料

- FinMind TaiwanStockMonthRevenue（已快取）：SUE
- FinMind TaiwanStockPrice、TaiwanStockSecuritiesLending、TaiwanDailyShortSaleBalances、TaiwanFuturesDaily（已快取）：fv5 建構、借券條件 D、台指期對沖
- analysis/ls_turnover.py、analysis/borrow_capacity.py、analysis/fv5_smoothed_sue.py：fv5 建構、換手與成本計算可沿用

## 檢定計畫（看結果前固定）

- 樣本：前 500 名，2019-01 ~ 2026-04，兩段 2019–2022 / 2023–2026/04；2026-05 以後不用。前 6 個月為建倉期，兩個版本都從同一天開始計算績效（fv5 也從第 6 個換倉日起算，避免起點差異）。
- fv5-H6：資金分 6 份，第 k 份在第 k、k+6、k+12… 個月營收換倉日換倉；換倉時用當月最新 SUE，產業內前／後 1/3 等權、借券條件 D、台指期對沖、單邊 0.29625% 與實際借券費，全部照 fv5。持有期間空單若不再符合條件 D 的處理方式與 fv5 相同。
- 對照：fv5（三份、3 個月）在同一期間的日淨報酬。
- 通過標準（計入本批 Holm）：年換手相對 fv5 下降 ≥ 30%；年化淨報酬差 ≥ +0.10 個百分點、兩段差皆 > 0；兩段 Sharpe 皆不低於 fv5；配對日報酬差全期 Newey-West（落後 5）t 達 Holm 門檻。四項都要成立。
- 只報告：四份、4 個月版本；fv5x 改為 H6；扣成本前與扣成本後的報酬差拆解（訊號衰減 vs 省下的成本與借券費）；SUE 對第 1–60、61–120、121–180 日產業調整報酬的產業內 IC（前 500 名與第 1001–1500 名），說明持有後段是否仍有漂移；空方腿持有期間遇到停券或召回的次數。
- 資料窺探：fv3 時期的 1、2、3 個月結果已看過，4–6 個月與 SUE 61 日以後的 IC 都沒看過。通過也只作為前瞻規格候選，由使用者決定是否另立平行記錄；未通過即停止，不改為 5 個月或其他份數重測。
- 本批 Holm 校正（5 張卡、α = 5%、雙尾）：依 p 值由小到大的門檻為 t ≥ 2.58、2.50、2.39、2.24、1.96；單卡至少要過最嚴的 2.58 才保證通過，其餘依 Holm 逐步判定。

## 與已測點子的關係

- fv5 用平滑的月營收驚奇排序以降低換手：最近 3 個月 SUE 產業內百分位的平均取代單月 SUE（其餘建構不變）（card:已測：未通過，research/ideas/I076-fv5-smoothed-sue-low-turnover.md）：命中 降低換手, 換手, 交易成本, turnover reduction
- 金融股自結盈餘驚奇的低換手多空（緩衝換倉）（card:已測：未通過，research/ideas/I017-financial-esue-low-turnover-ls.md）：命中 換手, turnover
- 金融股自結盈餘驚奇低換手多空（緩衝換倉）（failed，docs/fin_esue_followup_report.md）：命中 換手
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 當沖比（dt20、dtjump）（failed，docs/daytrading_report.md）：命中 turnover
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 fv5
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5
- 用股票期貨執行 fv5：以期交稅取代證交稅、以期貨空單取代借券（card:停止：追蹤誤差未過，research/ideas/I031-fv5-single-stock-futures-execution.md）：命中 交易成本
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:已測：未通過，research/ideas/I054-fv5-entry-execution-price.md）：命中 fv5
- fv5 空方腿避開融券回補買壓：新空單若在 10 個交易日內遇到停券窗，延到最後回補日收盤再建倉（訊號與名單不變，只改建倉時點）（card:已測：未通過（只在 2023 年後有效），research/ideas/I059-fv5-short-defer-stop-window.md）：命中 fv5
- fv5 家族的稅後績效與除息日建倉規則：個人投資人股利所得稅與二代健保補充保費下，多方新倉延到除息後是否改善稅後報酬（card:已測：R1 未通過（稅後績效已報告），research/ideas/I061-fv5-after-tax-exdiv-entry.md）：命中 fv5
- fv5 持股遇到反向季報反應即出場：多單 QEAR 落在後 1/3、空單 QEAR 落在前 1/3 時，在公告後第 +3 日收盤平倉（名單與換倉日不變，只加事件出場）（card:已測：未通過，research/ideas/I074-fv5-qear-contrary-exit.md）：命中 低換手
- 補充：與 I076（平滑 SUE，failed）不同：I076 改排序分數、把舊月份混入，本卡排序分數完全不變，只延長每份資金的持有期。與 fv3 時期換倉頻率比較（ls_turnover）同族，但當時只測到 3 個月，且為前 300 名、fv3 建構。

研究點子，非投資建議。
