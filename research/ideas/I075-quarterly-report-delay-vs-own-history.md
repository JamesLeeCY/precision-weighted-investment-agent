# I075 季報公告延遲（相對自身去年同季）：過了慣常公告日仍未公告的公司，到公告後 2 日前的產業調整報酬較差

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | A | 事件研究（產業調整 CAR，事件日事前可知） | free | 約 0（公告日已在 I048 抓好；前 1500 名還原價、產業分類、借券已快取）；選做：用 analysis/fetch_fin_report_dates.py 補 2019-01 ~ 2020-06 公告日，約 150–250 次公開資訊觀測站請求（不占 FinMind），只用於報告 | 2026-10-27 |

## 假設

在市值前 500 名中，季報公告比去年同季對應日晚 2 個交易日以上仍未公告的公司，從確認延遲後下一個交易日收盤到實際公告反應日次一日收盤，產業調整報酬平均為負，t ≤ −2.58；第 501–1500 名同號且 t ≤ −2.0。

## 機制（為什麼會有超額報酬）

公司對公告時點有裁量：好消息傾向提早公告，壞消息傾向延後（審計調整、減損、與會計師意見不一）。投資人觀察得到『該公告卻還沒公告』，但文獻顯示市場直到實際公告時才完全反映這個訊息，這是注意力不足與反應不足。台灣公司公告日極為固定（I048 的資料可估計每家的慣常日），延遲本身是事前可知、可在公告前交易的事件，而且進場與事件時間很近，不受 I070 期限後進場的問題影響。

## 出處

- （同儕審查）Johnson、So（2018）Time Will Tell: Information in the Timing of Scheduled Earnings News，Journal of Financial and Quantitative Analysis，https://doi.org/10.1017/s0022109018000492：依摘要，排定公告日晚於預期的公司之後公布較差的消息，且股價要到實際公告才反映
- （同儕審查）Bagnoli、Kross、Watts（2002）The Information in Management's Expected Earnings Report Date: A Day Late, a Penny Short，Journal of Accounting Research，https://doi.org/10.1111/1475-679x.t01-1-00054：依摘要，錯過自訂公告日的公司，每延遲一天盈餘約比共識低 1 美分，股價在錯過日下跌並隨延遲持續下跌
- （同儕審查，新興市場）Haw、Qi、Wu（2000）Timeliness of Annual Report Releases and Market Reaction to Earnings Announcements in an Emerging Capital Market: The Case of China，Journal of International Financial Management and Accounting，https://doi.org/10.1111/1467-646x.00058：依摘要，中國 A 股 1994–1997 好消息公司較早公告年報、虧損公司最晚，且相對自身過去習慣提早好消息、延後壞消息
- （本專案）data_cache/events/fin_report_headlines.csv（I048）：56,641 則財報董事會公告、99% 在 13:30 後公告；docs/margin_surprise_actual_report.md

## 台股適用性

沒有找到台股以『相對自身歷史延遲』為交易訊號的實證（搜尋只找到中國、印尼等新興市場的時點與消息好壞關係）。台灣法定期限固定（Q1 5/15、Q2 8/14、Q3 11/14、Q4 3/31），大型公司多在期限前 1–3 週公告，所以延遲訊號主要出現在習慣早公告的前 500 名，正好是可交易的樣本；習慣在期限當天公告的公司無法被判定延遲，自動排除。放空延遲股需借券（條件 D），但也可用作 fv5 多方腿的出場濾網（只報告）。延遲也可能是無害的原因（董事會改期、併購整合），會稀釋效果。

## 所需資料

- data_cache/events/fin_report_headlines.csv：每家每季的公告日與時間（2020-07 ~ 2026-05），去年同季對應日
- FinMind TaiwanStockPrice 還原價（已快取）：產業調整報酬
- FinMind TaiwanStockSecuritiesLending（已快取）：放空可行性
- config/universe_mcap_membership.csv、config/universe_mcap_membership_1500.csv

## 檢定計畫（看結果前固定）

- 樣本：前 500 名，財報季 2021Q2 ~ 2025Q4（19 季；需要去年同季公告日）；兩段 2021-08 ~ 2022 / 2023 ~ 2026-03；確認樣本第 501–1500 名；2026-05 以後不用。前置條件：前 500 名事件數 ≥ 300，否則只做第 1–1500 名合併的統計版並標明。
- 慣常日：去年同季公告日距該季法定期限的交易日數 d；今年的預期日 = 今年期限往前 d 個交易日。
- 事件：預期日後第 2 個交易日收盤時仍未公告（以公開資訊觀測站發言日期判斷，該日任何時間的公告都算已公告），且距法定期限至少還有 2 個交易日。進場：該日的下一個交易日收盤；若當日跌停則延到下一個非跌停日；若在進場日 13:30 前已公告（約 1%），該事件剔除。出場：實際公告反應日次一日收盤（與 QEAR 視窗結束相同）；期限後仍未公告者在期限後第 2 個交易日收盤出場。
- 報酬：每日相對同產業（前 500 名等權）的超額報酬，累加為 CAR；個別事件 CAR 平均，以財報季為群做群聚標準誤；另報告日曆時間組合（每日持有所有事件股等權、台指期對沖）。
- 通過標準（計入本批 Holm）：前 500 名平均 CAR < 0、t ≤ −2.58，兩段皆 < 0；第 501–1500 名同號且 t ≤ −2.0。
- 只報告：延遲事件的 QEAR 是否低於同季準時公告者（內容驗證）；提前公告（比去年早 ≥ 3 日）事件的 QEAR 與之後 20 日報酬（無法事前交易，只當對照）；延遲天數分組；Q4（年報）與 Q1–Q3 分開；借券條件 D 下可放空的比例與扣借券費、0.59% 來回成本後的淨報酬；作為 fv5 多單出場濾網的效果。
- 資料窺探：本專案沒有看過公告時點與報酬的任何關係（I048、I070 只用公告日計算視窗）。未通過即停止，不改 2 日容忍、慣常日定義或出場日重測。
- 本批 Holm 校正（5 張卡、α = 5%、雙尾）：依 p 值由小到大的門檻為 t ≥ 2.58、2.50、2.39、2.24、1.96。

## 與已測點子的關係

- 季報公告的價格反應（季報 EAR）：以公開資訊觀測站實際財報董事會日期計算的 2 日產業調整報酬，對 SUE 與月營收 EAR 的增量（card:已測：H1 通過、H2 未通過（不另立前瞻），research/ideas/I070-quarterly-report-announcement-return.md）：命中 季報公告, 公告反應, 公開資訊觀測站
- 月營收依公告日提早進場（failed，docs/sue_event_entry_report.md）：命中 公告日, announcement timing
- 財報 Agent（營收、毛利、存貨、應收）（partial，forward/REPORT.md）：命中 財報
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- 年度盈餘驚奇改用實際董事會決議日：年報公告後的盈餘漂移（PEAD）（card:已測：未通過，research/ideas/I007-annual-earnings-surprise-actual-board-da.md）：命中 announcement timing
- 季報盈餘驚奇改用實際公告日：公開資訊觀測站重大訊息的財報董事會日期（card:暫緩（I007 顯示 2023 後無可交易漂移），research/ideas/I008-quarterly-pead-actual-announcement-date.md）：命中 公告時點
- 營收已知下的利潤率驚奇：季報營業利益率相對月營收隱含水準的驚奇（card:已測：未通過（前 500 名 t 1.9，驗證樣本顯著），research/ideas/I037-operating-margin-surprise-given-revenue.md）：命中 季報
- 季報公告溢酬：預期即將公告季報的前 500 名股票在公告前後是否有正報酬（與 I048 共用公告日資料）（card:待確認，research/ideas/I052-quarterly-earnings-announcement-premium.md）：命中 季報公告
- 月營收公告期間的市場反應（公告期報酬）對 SUE 的增量：價格反應是否帶有營收數字以外的資訊（card:已測：H1 通過、H2 未通過（不另立前瞻），research/ideas/I063-revenue-announcement-window-return-ear.md）：命中 EAR
- 月營收公告期報酬（EAR）的獨立多空與 fv5 各半組合：EAR 是否提供 fv5 之外的報酬來源（I063 後續，以跨越檢定判定）（card:已測：未通過，research/ideas/I068-ear-standalone-ls-fv5-blend.md）：命中 EAR
- fv5 腿內依 EAR 加權（SUE 與公告期報酬同向加碼、反向減碼）：名單不變只調權重，以第 501–1000 名選規則、第 1001–1500 名確認（card:待確認，research/ideas/I069-fv5-inleg-ear-agreement-weight.md）：命中 EAR
- 月營收的可預期季節性（Chang–Hartzmark–Solomon–Soltes 台股月頻版）：即將公告的月份歷來是營收旺月的股票，公告期報酬較高（card:待確認，research/ideas/I072-revenue-seasonality-announcement-return.md）：命中 EAR
- 補充：與 sue_event_entry（月營收依公告日提早進場，failed）不同：那是依公告日改進場時點，本卡把『未如期公告』本身當訊號，而且是季報。與 I070（QEAR）不同：本卡在公告前交易，報酬期間結束於 QEAR 視窗，不依賴公告後漂移。與 I008（季報盈餘驚奇改用實際公告日，暫緩）不同：本卡不計算盈餘驚奇。

研究點子，非投資建議。
