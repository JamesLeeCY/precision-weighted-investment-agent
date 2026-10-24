# I061 fv5 家族的稅後績效與除息日建倉規則：個人投資人股利所得稅與二代健保補充保費下，多方新倉延到除息後是否改善稅後報酬

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 濾網或加權（fv5 稅後核算＋多方建倉時點規則，與 fv5 建構配對比較） | free | 約 0（TaiwanStockDividendResult 除息日與金額已快取）；若要求 AnnouncementDate 判斷事前可知，用 TaiwanStockDividend，與 I058–I060 共用約 690 次 | 2026-10-24 |

## 假設

以個人分開計稅 28%＋補充保費 2.11% 計算，fv5 的稅後年化報酬比回測（含息、未扣稅）低至少 0.5 個百分點；規則 R1（換倉日新建的多單，若已公告的除息交易日落在未來 20 個交易日內，延到除息日收盤才買進，期間以 β × 台指期暫代）使稅後年化報酬提高至少 0.20 個百分點、兩段皆為正，而稅前報酬的損失不超過 0.10 個百分點。

## 機制（為什麼會有超額報酬）

稅負不對稱：fv5 回測用含息報酬，等於假設股利不課稅；實際上個人多方收到的現金股利要繳所得稅與補充保費，借券空方卻要以稅前全額支付權益補償給出借人。高稅率投資人在除息前賣、除息後買的行為在台灣有實證（Chen、Chow、Shiu 2013），代表稅負會影響持有決策。只延後『新』多單不增加股票交易次數；代價是錯過除息前的小幅上漲（本專案：除息前 10 日 +0.84% / +0.34%，2023 年後不顯著），好處是避開股利稅，且除息後 1–20 日本來就偏弱。

## 出處

- （同儕審查，台灣）Chen、Chow 與 Shiu（2013）Ex-dividend prices and investor trades: Evidence from Taiwan，Pacific-Basin Finance Journal 24: 39–65，https://ideas.repec.org/a/eee/pacfin/v24y2013icp39-65.html：1992–2006 年 987 次除息，高稅率投資人在除息前賣出、除息日買回，低稅率者反向（依摘要）
- （學位論文，台灣）李琪（2024）2018年股利稅改新制對除息日股價行為的影響，國立政治大學碩士論文，https://thesis.lib.nccu.edu.tw/thesis/detail/91bd03ddffaf6063932b60981b92da60：2018 年稅改後除息日價格下跌比率顯著上升、相對大盤異常報酬下降，稅改造成結構性改變（依摘要）
- （媒體，制度說明）口袋學堂（2026）股利所得報稅攻略，https://www.pocket.tw/school/articles/7414/：合併計稅可抵減 8.5%、每戶上限 8 萬元；分開計稅單一稅率 28%；單次股利達 2 萬元扣 2.11% 補充保費（以財政部、健保署公告為準）
- （本專案）docs/dividend_events_report.md、docs/exdiv_followup_report.md：除息前 10 日 +0.84%（t 3.6）/ +0.34%（t 1.2）；高殖利率股除息後偏弱配對後 −1.74%（t −2.6）；『SUE 多單排除剛除息的高殖利率股』稅前未改善

## 台股適用性

完全是台灣稅制問題：2018 年起股利所得二選一（合併計稅 8.5% 抵減、上限 8 萬；或分開計稅 28%），另有 2.11% 補充保費；借券的權益補償由借券人支付全額現金股利。外資（21% 扣繳）與法人的情境不同，本卡只做個人情境並列出法人／免稅情境（= 現行回測）。這是實作前必須知道的數字：若稅後 Sharpe 明顯下降，fv5 家族前瞻的採用判斷要改用稅後數字。

## 所需資料

- FinMind TaiwanStockDividendResult（已快取）：除息交易日、除息前收盤與參考價（現金股利金額）
- FinMind TaiwanStockDividend：AnnouncementDate（換倉日是否已知除息日）
- fv5、fv5x 回測的每日持股權重（analysis/ls_turnover.py、analysis/hedge_construction.py、analysis/fv5_invvol.py）
- 稅率參數（使用者需確認）：個人合併計稅邊際稅率、是否選分開計稅、單次股利是否達 2 萬元

## 檢定計畫（看結果前固定）

- 稅率情境（看結果前固定）：T0 不課稅（現行回測、法人近似）；T1 個人合併計稅，邊際稅率 20% − 抵減 8.5% = 淨 11.5%（不計 8 萬上限）＋補充保費 2.11%；T2 個人分開計稅 28% ＋ 補充保費 2.11%。空方借券權益補償一律以稅前全額支付、不抵稅。股票股利依面額課稅（同稅率）。
- 第一部分（不論結果都報告，無通過門檻）：fv5 與 fv5x 在 T0、T1、T2 下的年化淨報酬、Sharpe、回撤，2019–2022 / 2023–2026/04；以及每年股利稅負占組合資金的比例。
- 規則 R1：換倉日 d 新建或加碼的多單，若 AnnouncementDate ≤ d 且除息交易日落在 (d, d + 20 個交易日]，改在除息交易日收盤買進，期間以 β × 台指期多單暫代（期貨 0.005%）；已持有的多單、空方腿、名單、權重不變。
- 只報告的變體（不判定，避免多重比較）：R2 延到除息後第 20 日（利用除息後偏弱）；R3 已持有多單在 T2 下若『股利 × 30.11% > 來回成本 0.59%』則除息前賣出、除息日買回。
- 指標：R1 相對 fv5 的稅後（T2）與稅前（T0）年化淨報酬差、兩段 Sharpe、受影響多單比例、每次換倉配對差 Newey-West t（落後 2）。
- 通過標準：T2 下 R1 年化淨報酬差 ≥ +0.20 個百分點、兩段皆 > 0、兩段稅後 Sharpe 都不低於 fv5、配對差 t > 2；且 T0 下損失 ≤ 0.10 個百分點。計入本批 Holm 校正。
- 資料窺探：除息前後的平均報酬已在 dividend_events 看過，所以 R1 的稅前代價部分可預期；本卡判定的主體是稅負節省，屬機械性計算。2026-05 以後不用。若通過，只作為使用者決定前瞻執行規則與稅後報告的依據，不改已登錄的 fv5 家族紀錄。
- 未通過即停止；不改 20 日視窗或稅率重測。

## 與已測點子的關係

- 除息後偏弱（高殖利率）；SUE 濾網未通過、放空受可借量限制（partial，docs/exdiv_followup_report.md）：命中 除息, ex-dividend
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 外資台指期／台指選擇權淨部位擇時（failed，docs/fut_inst_timing_report.md）：命中 台指期
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 fv5
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- 外資台指期／台指選擇權淨部位：大盤擇時（台指期執行）（card:已測：未通過，research/ideas/I013-foreign-futures-options-positions-timing.md）：命中 台指期
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5
- fv5 家族的合併規格與前瞻採用規則：三項修改同時使用（fv5e＋fv5s＋fv5v）的交互作用，以及多重比較下的事前決策程序（card:已測：fv5x 回測通過（已另立前瞻）；採用規則改為波動調整後報酬差，research/ideas/I051-fv5-family-combined-spec-decision-rule.md）：命中 fv5 家族
- fv5 家族前瞻的輔助判定：以機制指標（增量 IC、日頻波動比）加非劣性檢定，縮短判定時間（不取代已登錄規則）（card:已測：輔助判定規則已登錄（2026-10-24），research/ideas/I053-fv5-family-mechanism-endpoints-power.md）：命中 fv5 家族
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:已測：未通過，research/ideas/I054-fv5-entry-execution-price.md）：命中 fv5
- fv5 家族的影子前瞻：在市值第 501–1000 名平行記錄同一組修改，作為獨立樣本的輔助判定（統計版，不交易）（card:已測：前提不成立（不建立影子前瞻），research/ideas/I057-fv5-family-shadow-universe-forward.md）：命中 fv5 家族
- fv5 空方腿避開融券回補買壓：新空單若在 10 個交易日內遇到停券窗，延到最後回補日收盤再建倉（訊號與名單不變，只改建倉時點）（card:待確認，research/ideas/I059-fv5-short-defer-stop-window.md）：命中 fv5
- 現金股利發放日的再投資買壓（Hartzmark–Solomon 台股版）：大額發放日的加權指數報酬較高，以台指期執行（card:待確認，research/ideas/I060-dividend-payment-reinvestment-pressure.md）：命中 台指期
- 補充：與『除息後偏弱』（partial）及『SUE 多單排除剛除息高殖利率股』（稅前未改善）不同：本卡的主要效益來自稅負，而非報酬預測，且只延後新多單、不增加交易。與 I054（換倉執行時點，未通過）不同：只影響除息日前 20 日內的新多單；需報告是否錯過 SUE 多方漂移。

研究點子，非投資建議。
