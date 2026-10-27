# I073 季報公告反應的事件時間進場（I070 後續）：QEAR 前 1/3 在反應窗結束後立即做多、持有 60 日、台指期對沖，檢驗 I070 H2 失敗是否來自期限後才進場

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 事件型可交易建構（事件時間進場的日曆時間組合）＋跨越檢定 | free | 約 0（公告日已在 I048 抓好；前 1500 名還原價、漲跌停價、產業分類、台指期已快取） | 2026-10-27 |

## 假設

在市值前 500 名中，季報公告後 2 日產業調整報酬（QEAR）落在事前門檻前 1/3 的股票，於 QEAR 視窗結束後下一個交易日收盤（公告後第 +3 個交易日）逐檔做多、持有 60 個交易日並以台指期對沖 β，其日淨報酬對 fv5 與 5 個風格因子的跨越截距 t ≥ 2.58、兩段截距皆 > 0。

## 機制（為什麼會有超額報酬）

I070 顯示 QEAR 對之後 60 日產業調整報酬的預測力很強（前 500 名 Fama-MacBeth t 6.5），但統一在法定期限後才進場的多空全期 Sharpe −0.22。公告日距期限中位數 5 個交易日、25% 超過 12 日，若漂移集中在公告後頭幾週，期限後才進場會錯過大部分。機制是投資人對財報資訊的反應不足（PEAD 文獻），而台灣季報 99% 在盤後公告、反應日後仍有延續。改成事件時間進場只動進場時點；只做多方可避開借券限制（I042／I056 的教訓），並把換手限制在每檔每季一次來回。

## 出處

- （本專案）docs/ear_quarterly_tom_report.md（I070）：QEAR 對 60 日產業調整報酬的 FM 係數前 500 名 +0.103（t 6.5）、第 1001–1500 名 +0.100（t 6.1）；QEAR 三分組 60 日產業調整報酬由低到高 −1.16%、−0.82%、+1.66%；期限後進場的多空全期 Sharpe −0.22，落差原因沒有拆解
- （工作論文）Brandt、Kishore、Santa-Clara、Venkatachalam（2006）Earnings Announcements are Full of Surprises，SSRN，https://doi.org/10.2139/ssrn.909563：以公告期報酬衡量盈餘驚奇的漂移研究；本次未讀到摘要，只作為出處線索
- （同儕審查）Chan、Jegadeesh、Lakonishok（1996）Momentum Strategies，Journal of Finance 51(5)，https://doi.org/10.1111/j.1540-6261.1996.tb05222.x：以公告期報酬等盈餘資訊衡量的盈餘動能，與價格動能各自預測報酬；本次未重讀全文
- （本專案）research/ideas/I070-quarterly-report-announcement-return.md：QEAR 定義與公告日資料（公開資訊觀測站財報董事會公告，2020-07 起）

## 台股適用性

有台灣實證（本專案 I070，三個名次組都顯著），但只有統計上的 60 日預測力；可交易版本未通過。台灣季報期限 Q1 5/15、Q2 8/14、Q3 11/14、Q4 3/31，公告集中在期限前，前 500 名的大公司較早公告，所以事件時間進場對大型股的影響應最大。風險：只做多加台指期對沖會留下產業曝險；公告集中在期限前，部位會在每季期限附近大量建立，持股數隨季節起伏，資金使用率不到 100%。另外漲跌停：反應日後第 +3 日進場時若漲停買不到，該筆不進場（記錄比例）。

## 所需資料

- data_cache/events/fin_report_headlines.csv：財報董事會公告日與時間（2020-07 ~ 2026-05）
- FinMind TaiwanStockPrice 還原價（已快取）：QEAR、持有期報酬、漲停判斷
- FinMind TaiwanFuturesDaily TX（已快取）：β 對沖
- analysis/quarterly_ear.py、analysis/quarterly_ear_h2.py：QEAR 視窗與 I070 H2 建構，可直接改寫
- config/universe_mcap_membership.csv、config/universe_mcap_membership_1500.csv

## 檢定計畫（看結果前固定）

- 樣本：前 500 名（公告當時的成員），財報季 2020Q3 ~ 2025Q4（21 季；2020Q2 只用來定門檻）；兩段 2020-08 ~ 2022 / 2023 ~ 2026-04；持有期截到 2026-04-30，2026-05 以後不用（2026Q1 季報不納入）。
- 訊號：QEAR 與 I070 完全相同（反應日前一日收盤到反應日次一日收盤的 2 日產業調整報酬）。門檻：前 1 ~ 4 季（至少 1 季）全部前 500 名公告的 QEAR 2/3 與 1/3 分位數，事前可知；不用同季尚未公告者，避免前視。
- 進場：QEAR 視窗結束後下一個交易日（公告後第 +3 個交易日；盤中公告者以公告日為反應日）收盤買進 QEAR ≥ 前 2/3 門檻者；當日漲停則不進場。出場：持有 60 個交易日後收盤，或下一季公告反應日前一日收盤，取較早者。
- 權重：每筆部位固定為資本的 1/K，K = 前一年度每日平均同時持有檔數（事前可知；第一年用 160）；未投入資金報酬記為 0；每日以持股 250 日 β 加總的台指期空單對沖。
- 成本：股票單邊 0.29625%（每筆一次來回）、台指期單邊 0.005% 加轉倉；不做空方腿（空方只報告，借券條件 D）。
- P1（主判定，計入本批 Holm）：組合日淨報酬 = a + b·fv5 日淨報酬 + 5 個 I049 風格因子 + e，Newey-West 落後 5；通過：全期 a 的 t ≥ 2.58、兩段 a 皆 > 0。
- P2：全期 Sharpe（扣成本、對沖後）> 0.5，且 50% fv5 + 50% 本組合的全期 Sharpe > fv5 的 1.64。P1、P2 都成立才算通過。
- 只報告：前 1/3 部位 60 日報酬拆成『進場到法定期限』與『期限後到第 60 日』兩段（直接回答 I070 落差來源）；空方腿（後 1/3、借券條件 D）；第 501–1000 名加 0.46% 額外滑價的同一建構；第 1001–1500 名只算毛報酬；漲停未進場比例；持股數的季節分布。
- 資料窺探：QEAR 的 60 日預測力在前 500 名與第 1001–1500 名都已看過，本卡唯一的新資訊是事件時間進場的淨報酬；I070 報告已寫明『不改進場日重測』，因此本卡需使用者明確同意才執行。通過也不直接併入 fv5，只能另立前瞻記錄，以 2026Q2 起的季報做樣本外確認。
- 本批 Holm 校正（5 張卡、α = 5%、雙尾）：依 p 值由小到大的門檻為 t ≥ 2.58、2.50、2.39、2.24、1.96；單卡至少要過最嚴的 2.58 才保證通過，其餘依 Holm 逐步判定。未通過即停止，不改門檻、持有期或進場日重測。

## 與已測點子的關係

- 季報公告的價格反應（季報 EAR）：以公開資訊觀測站實際財報董事會日期計算的 2 日產業調整報酬，對 SUE 與月營收 EAR 的增量（card:已測：H1 通過、H2 未通過（不另立前瞻），research/ideas/I070-quarterly-report-announcement-return.md）：命中 季報公告, 季報公告期報酬, 公告反應, QEAR, earnings announcement return, announcement return, post-earnings announcement drift, PEAD
- 月營收公告期間的市場反應（公告期報酬）對 SUE 的增量：價格反應是否帶有營收數字以外的資訊（card:已測：H1 通過、H2 未通過（不另立前瞻），research/ideas/I063-revenue-announcement-window-return-ear.md）：命中 公告期報酬, earnings announcement return, announcement return, EAR, 反應不足
- 月營收公告期報酬（EAR）的獨立多空與 fv5 各半組合：EAR 是否提供 fv5 之外的報酬來源（I063 後續，以跨越檢定判定）（card:已測：未通過，research/ideas/I068-ear-standalone-ls-fv5-blend.md）：命中 公告期報酬, EAR, announcement return, earnings announcement return
- 月營收的可預期季節性（Chang–Hartzmark–Solomon–Soltes 台股月頻版）：即將公告的月份歷來是營收旺月的股票，公告期報酬較高（card:待確認，research/ideas/I072-revenue-seasonality-announcement-return.md）：命中 公告期報酬, EAR, announcement return
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日, calendar
- 季報盈餘驚奇（failed，docs/revenue_surprise_plus_report.md）：命中 pead, post-earnings announcement drift
- 年度盈餘驚奇改用實際董事會決議日：年報公告後的盈餘漂移（PEAD）（card:已測：未通過，research/ideas/I007-annual-earnings-surprise-actual-board-da.md）：命中 post-earnings announcement drift, pead
- 季報盈餘驚奇改用實際公告日：公開資訊觀測站重大訊息的財報董事會日期（card:暫緩（I007 顯示 2023 後無可交易漂移），research/ideas/I008-quarterly-pead-actual-announcement-date.md）：命中 post-earnings announcement drift, pead
- fv5 腿內依 EAR 加權（SUE 與公告期報酬同向加碼、反向減碼）：名單不變只調權重，以第 501–1000 名選規則、第 1001–1500 名確認（card:待確認，research/ideas/I069-fv5-inleg-ear-agreement-weight.md）：命中 公告期報酬, EAR
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 外資台指期／台指選擇權淨部位擇時（failed，docs/fut_inst_timing_report.md）：命中 台指期
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 fv5
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- 年度盈餘驚奇改用實際董事會決議日（failed，docs/earnings_board_date_report.md）：命中 pead
- 外資台指期／台指選擇權淨部位：大盤擇時（台指期執行）（card:已測：未通過，research/ideas/I013-foreign-futures-options-positions-timing.md）：命中 台指期
- 美股大型科技公司財報反應對台股連結股的延遲傳遞（客戶／同業財報 → 台灣供應鏈）（card:已測：未通過，research/ideas/I016-us-earnings-to-taiwan-linked-stocks.md）：命中 earnings announcement return
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5
- 營收已知下的利潤率驚奇：季報營業利益率相對月營收隱含水準的驚奇（card:已測：未通過（前 500 名 t 1.9，驗證樣本顯著），research/ideas/I037-operating-margin-surprise-given-revenue.md）：命中 季報
- 季報公告溢酬：預期即將公告季報的前 500 名股票在公告前後是否有正報酬（與 I048 共用公告日資料）（card:待確認，research/ideas/I052-quarterly-earnings-announcement-premium.md）：命中 季報公告
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:已測：未通過，research/ideas/I054-fv5-entry-execution-price.md）：命中 fv5
- fv5 空方腿避開融券回補買壓：新空單若在 10 個交易日內遇到停券窗，延到最後回補日收盤再建倉（訊號與名單不變，只改建倉時點）（card:已測：未通過（只在 2023 年後有效），research/ideas/I059-fv5-short-defer-stop-window.md）：命中 fv5
- 現金股利發放日的再投資買壓（Hartzmark–Solomon 台股版）：大額發放日的加權指數報酬較高，以台指期執行（card:已測：未通過，research/ideas/I060-dividend-payment-reinvestment-pressure.md）：命中 台指期
- fv5 家族的稅後績效與除息日建倉規則：個人投資人股利所得稅與二代健保補充保費下，多方新倉延到除息後是否改善稅後報酬（card:已測：R1 未通過（稅後績效已報告），research/ideas/I061-fv5-after-tax-exdiv-entry.md）：命中 fv5
- 月底月初效應（turn of the month）以台指期執行：每月最後 1 個交易日到次月第 3 個交易日做多台指期，作為與 fv5 低相關的附加部位（card:已測：未通過，research/ideas/I071-turn-of-month-tx-futures.md）：命中 台指期
- 補充：I070 H2 在法定期限後第一個交易日統一換倉、多空、產業內前／後 1/3；本卡改為各檔公告後第 +3 日進場、只做多、固定每筆資本比例，用來拆解 I070 的落差。與 I068（月營收 EAR 獨立多空）不同：季報一年只有 4 次，換手約為月營收版本的 1/3。與 I074（fv5 持股遇反向 QEAR 出場）共用訊號，但本卡是獨立部位。

研究點子，非投資建議。
