# I079 fv5 多方腿改用指數避險取代個股空方腿：台指期 ＋ 中型股指數（0051 代理）的滾動 β 避險，作為不需借券的容量延伸

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過 | A | 濾網或加權（fv5 執行方式修改：以指數避險取代空方腿，與 fv5 建構比較） | free | 約 10（0051 價格 1 次、0051 借券成交與費率約 8 次；其餘前 500 名價格、月營收、台指期、M1F 已快取） | 2026-10-28 |

## 假設

fv5 的多方腿（產業內 SUE 前 1/3 等權、三份錯開每 3 個月換倉）以台指期與中型股指數（0051 還原報酬）做滾動 β 避險後，扣交易成本與避險成本的日淨報酬全期平均為正、Newey-West t 達本批 Holm 門檻，且兩段皆 > 0；同時兩段 Sharpe 皆 ≥ 1.0。

## 機制（為什麼會有超額報酬）

執行面與容量的改善。fv5 的成本有兩塊來自空方腿：約一半的換手（交易成本約 2.7%／年中的一半）與全部借券費（約 1.8%／年）；容量也卡在空方腿：資金 10 億時條件 D 的覆蓋率從 82% 降到 70%，小型股只剩 47%（docs/borrow_capacity_report.md）。先前「等權做多 − β × 台指期」失敗（0.17 / −0.07），原因是等權持股與台積電主導的台指期之間有每年約 −4.5% 的結構差（規模與產業組成），不是 SUE 多方腿沒有 alpha。加入中型股指數當第二個避險因子，可吸收大部分規模差，只留下 SUE 的選股報酬。若成立，本建構可在 fv5 借不到券的資金規模上當延伸部位。

## 出處

- （同儕審查）Israel、Moskowitz（2013）The Role of Shorting, Firm Size, and Time on Market Anomalies，Journal of Financial Economics 108(2): 275–301，https://ideas.repec.org/a/eee/jfinec/v108y2013i2p275-301.html：依摘要，規模、價值、動能的報酬中，多方部位貢獻分別約全部、六成、一半，放空的重要性因策略與市值而異
- （本專案）docs/borrow_capacity_report.md：放空端借券費中位數 1.71%／年、小型股 20% 部位費率 > 5%；資金 10 億時條件 D 覆蓋 70%；等權做多 − β × 台指期 0.17 / −0.07
- （本專案）docs/hedge_construction_report.md：結構差來源是權重方式，下一步建議之一是以中型股 ETF（例如 0051）或小型股組合當對沖工具，至今未測
- （本專案）docs/smallcap_execution_report.md：第 501–1000 名用臺灣中型100期貨（M1F）避險 R² 0.74、殘差波動 8.8%，台指期為 0.47、12.5%；FinMind 的 M1F 只有 2023 年後有效

## 台股適用性

台股放空受借券費、融券強制回補與平盤下放空限制影響，空方腿是 fv5 成本與容量的主要瓶頸；指數避險只需台指期（成本約 0.005%）與 0051 借券或中型100期貨。限制：(1) 0051 是市值第 51–150 名的市值加權，fv5 多方腿是前 500 名等權、以第 150–500 名的檔數居多，避險可能不完全；(2) 0051 成交量小，放空 0051 的借券量與費率需查；中型100期貨在 2023 年前的資料不可用，回測一律用 0051 還原報酬當代理並另計假設成本；(3) 只做多時產業中性不再成立，組合帶有產業曝險。

## 所需資料

- FinMind TaiwanStockPrice 0051（未快取，1 次）：中型股指數代理（還原配息）
- FinMind TaiwanStockSecuritiesLending 0051（約 8 次）：放空 0051 的實際費率；若無成交則用固定 1.5%／年假設
- FinMind TaiwanFuturesDaily TX、M1F（已快取）：避險報酬與 2023 年後的實際期貨版本
- 前 500 名月營收、還原價、產業分類（已快取）：多方腿；analysis/leg_probe.py 的 β 計算與 tx_continuous 可沿用

## 檢定計畫（看結果前固定）

- 樣本：前 500 名，2019-01 ~ 2026-04，兩段 2019–2022 / 2023–2026/04；2026-05 以後不用。
- 多方腿：與 fv5 完全相同（產業內 SUE 前 1/3 等權、三份錯開每 3 個月換倉、單邊 0.29625%），資金 100% 做多。
- 避險（LH）：每個換倉日用前 250 個交易日，將多方腿（以當時持股權重回推）的日報酬對台指期近月報酬與 0051 還原日報酬做迴歸，取兩個係數為空單比率，到下一個換倉日前固定；台指期成本 0.005% 並計每月轉倉；0051 空單扣實際借券費（無資料時 1.5%／年）與單邊 0.29625%。
- 主判定（計入本批 Holm）：LH 日淨報酬全期平均 > 0、Newey-West（落後 5）t 達 Holm 門檻，兩段平均皆 > 0。實務門檻：兩段 Sharpe 皆 ≥ 1.0。兩項都成立才通過。
- 只報告：fv5 與 LH 的日報酬相關；50% fv5 + 50% LH 的 Sharpe；資金 10 億時 fv5（條件 D 覆蓋降低）與 LH 的比較；避險 R² 與殘差波動；2023 年後改用 M1F 實際期貨的版本；三因子避險（加櫃買指數）；fv5 多方腿與空方腿各自相對產業平均的淨貢獻（拆解空方腿扣借券費後還剩多少）。
- 資料窺探：等權做多 − β × 台指期（失敗）已看過；0051 避險與 fv5 多空兩腿的拆解都沒看過。未通過即停止，不改避險工具、估計視窗或改用產業指數重測。
- 本批 Holm 校正（5 張卡、α = 5%、雙尾）：依 p 值由小到大的門檻為 t ≥ 2.58、2.50、2.39、2.24、1.96；單卡至少要過最嚴的 2.58 才保證通過，其餘依 Holm 逐步判定。

## 與已測點子的關係

- 中小型股（市值第 501–1000 名）執行面前置檢查：容量、滑價、漲跌停、借券與避險工具（card:已測：L2、S 未過（只做統計檢定），research/ideas/I042-smallcap-execution-precheck.md）：命中 容量, capacity, 借券, 中型100期貨, 避險
- fv5 空方腿改以融券為主、借券補足：借券費與強制回補成本的取捨（訊號與名單不變）（card:已測：未通過（保守情境 +0.41%），research/ideas/I056-fv5-short-leg-margin-vs-sbl.md）：命中 借券, 借券費, 空方腿
- fv5 空方腿避開融券回補買壓：新空單若在 10 個交易日內遇到停券窗，延到最後回補日收盤再建倉（訊號與名單不變，只改建倉時點）（card:已測：未通過（只在 2023 年後有效），research/ideas/I059-fv5-short-defer-stop-window.md）：命中 fv5, 空方腿, 借券
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5, SUE
- fv5 腿內依 EAR 加權（SUE 與公告期報酬同向加碼、反向減碼）：名單不變只調權重，以第 501–1000 名選規則、第 1001–1500 名確認（card:待確認，research/ideas/I069-fv5-inleg-ear-agreement-weight.md）：命中 多方腿, 空方腿
- fv5 延長持有期：每份資金持有 6 個月、六份錯開（每月換 1/6），以降低換手成本（訊號與名單規則不變）（card:待確認，research/ideas/I078-fv5-six-month-hold-six-tranches.md）：命中 交易成本, fv5
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 借券賣出餘額比、借券費率、增量、需求量（partial，docs/lending_legs_report.md）：命中 借券
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 外資台指期／台指選擇權淨部位擇時（failed，docs/fut_inst_timing_report.md）：命中 台指期
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 fv5
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- 借券賣出餘額比相對自身歷史（ts_rank）——與 SUE 合成（effective，docs/ts_rank_report.md）：命中 借券
- 外資台指期／台指選擇權淨部位：大盤擇時（台指期執行）（card:已測：未通過，research/ideas/I013-foreign-futures-options-positions-timing.md）：命中 台指期
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 用股票期貨執行 fv5：以期交稅取代證交稅、以期貨空單取代借券（card:停止：追蹤誤差未過，research/ideas/I031-fv5-single-stock-futures-execution.md）：命中 交易成本
- fv5 腿內波動調整權重：以逆變異數權重取代等權（card:已測：未通過（W2 接近），research/ideas/I033-fv5-inverse-volatility-leg-weights.md）：命中 等權
- 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）（card:已測：未通過（階段 1 過、階段 2 t 2.8），research/ideas/I043-smallcap-multifactor-composite.md）：命中 sue
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:已測：未通過，research/ideas/I054-fv5-entry-execution-price.md）：命中 fv5
- 現金股利發放日的再投資買壓（Hartzmark–Solomon 台股版）：大額發放日的加權指數報酬較高，以台指期執行（card:已測：未通過，research/ideas/I060-dividend-payment-reinvestment-pressure.md）：命中 台指期
- fv5 家族的稅後績效與除息日建倉規則：個人投資人股利所得稅與二代健保補充保費下，多方新倉延到除息後是否改善稅後報酬（card:已測：R1 未通過（稅後績效已報告），research/ideas/I061-fv5-after-tax-exdiv-entry.md）：命中 fv5
- fv5 多方腿改用股票期貨的稅後執行（I031 修訂版）：期交所現金股利權益數調整＋期貨交易所得停徵，避開股利稅與賣出證交稅（card:已測：未通過（轉倉成本大於節稅），research/ideas/I064-fv5-long-leg-ssf-after-tax.md）：命中 多方腿
- fv5 多方持股出借（借券收入）：上限估計與稅務查核，先判斷值不值得做（card:待確認，research/ideas/I066-fv5-long-leg-securities-lending-income.md）：命中 fv5 多方腿
- 月底月初效應（turn of the month）以台指期執行：每月最後 1 個交易日到次月第 3 個交易日做多台指期，作為與 fv5 低相關的附加部位（card:已測：未通過，research/ideas/I071-turn-of-month-tx-futures.md）：命中 台指期
- 季報公告反應的事件時間進場（I070 後續）：QEAR 前 1/3 在反應窗結束後立即做多、持有 60 日、台指期對沖，檢驗 I070 H2 失敗是否來自期限後才進場（card:待確認，research/ideas/I073-qear-event-time-long-entry.md）：命中 只做多
- fv5 用平滑的月營收驚奇排序以降低換手：最近 3 個月 SUE 產業內百分位的平均取代單月 SUE（其餘建構不變）（card:已測：未通過，research/ideas/I076-fv5-smoothed-sue-low-turnover.md）：命中 交易成本
- 補充：與 I042（第 501–1000 名執行前置檢查）不同：I042 只檢查中小型股的避險工具 R²，本卡是前 500 名 fv5 多方腿的完整淨報酬檢定。與 borrow_capacity 的「等權做多 − β × 台指期」同族，但新增中型股指數這個避險因子，針對其失敗原因（規模結構差）。與 I056、I059、I065 不同：那些改空方腿的放空方式或時點，本卡完全不放空個股。

研究點子，非投資建議。
