# I074 fv5 持股遇到反向季報反應即出場：多單 QEAR 落在後 1/3、空單 QEAR 落在前 1/3 時，在公告後第 +3 日收盤平倉（名單與換倉日不變，只加事件出場）

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過 | B | 濾網或加權（fv5 持有期間的事件出場規則，與 fv5 建構配對比較） | free | 約 0（公告日已在 I048 抓好；前 500 名還原價、漲跌停價、借券、台指期、fv5 持股紀錄皆已快取或可重建） | 2026-10-27 |

## 假設

在 fv5 的持股中，若季報公告後 2 日產業調整報酬（QEAR）與持有方向相反（多單落在事前門檻後 1/3、空單落在前 1/3），於公告後第 +3 個交易日收盤平倉、資金留到該份資金下次換倉，fv5 的年化淨報酬會提高至少 0.10 個百分點、兩段皆提高，且配對日報酬差 t ≥ 2.58。

## 機制（為什麼會有超額報酬）

I070 的 QEAR 在控制月營收 SUE 後仍預測之後 60 日的產業調整報酬（前 500 名 t 6.5），代表季報帶有月營收以外的資訊（利潤率、業外、財測語氣）。fv5 每 3 個月才換倉，持有期間遇到季報時，與持有方向相反的價格反應就是新的反向訊號。只對少數衝突持股出場，換手增加遠小於另建 QEAR 多空（I068、I070 失敗的主因是整份換名單的成本），而且出場的部位本來多半在下次換倉也會換掉。

## 出處

- （本專案）docs/ear_quarterly_tom_report.md（I070）：QEAR 的 60 日增量預測力前 500 名 t 6.5、第 1001–1500 名 t 6.1；另建 QEAR 多空扣成本後全期 Sharpe −0.22
- （本專案）docs/ear_quarterly_tom_report.md（I068 診斷）：月營收 EAR 合成換入的多方股票之後 60 日 +1.21%、換出的 −0.82%；空方換入 +0.01%、換出 −1.09%，說明價格反應在多方有幫助、在空方可能換掉正確的空單
- （同儕審查）Novy-Marx、Velikov（2016）A Taxonomy of Anomalies and Their Trading Costs，Review of Financial Studies 29(1)，https://doi.org/10.1093/rfs/hhv063：依摘要，建立部位比維持部位要求更嚴的做法最能降低成本；本卡反過來只在出現強反向證據時提早出場
- （同儕審查）Chan、Jegadeesh、Lakonishok（1996）Momentum Strategies，Journal of Finance 51(5)，https://doi.org/10.1111/j.1540-6261.1996.tb05222.x：公告期報酬等盈餘資訊的動能與價格動能各自預測報酬；本次未重讀全文

## 台股適用性

季報公告日已有（公開資訊觀測站，2020-07 起），fv5 回測框架、借券條件 D、台指期對沖都可沿用。fv5 名單偏向高／低營收驚奇，季報反應與 SUE 正相關，所以衝突持股的比例應低於 1/3（需報告）。空單提前回補在除權息與股東會季不受影響；多單出場若遇跌停賣不掉，延到下一個非跌停日收盤（記錄比例）。

## 所需資料

- data_cache/events/fin_report_headlines.csv：財報董事會公告日
- FinMind TaiwanStockPrice 還原價（已快取）：QEAR 與持有期報酬
- fv5 建構程式（analysis/borrow_capacity.py、analysis/ls_turnover.py 的三份錯開建構）
- analysis/quarterly_ear.py：QEAR 計算

## 檢定計畫（看結果前固定）

- 樣本：前 500 名、fv5 原建構；比較期間 2020-08 ~ 2026-04（QEAR 從 2020Q2 季報起才有），兩段 2020-08 ~ 2022 / 2023 ~ 2026-04；2026-05 以後不用。
- 訊號：QEAR 與 I070 相同；門檻為前 1 ~ 4 季（至少 1 季）全部前 500 名公告 QEAR 的 1/3 與 2/3 分位數（事前可知，與 I073 相同）。
- 規則 R：fv5 多單的 QEAR ≤ 1/3 門檻、或空單的 QEAR ≥ 2/3 門檻時，於公告後第 +3 個交易日收盤平倉；釋出的資金不再投入，到該份資金下次換倉才依 fv5 規則重建；台指期對沖依新的淨 β 調整。其餘（名單、換倉日、權重、借券條件 D、成本）完全照 fv5。
- 成本：股票單邊 0.29625%、借券費依實際持有天數、台指期 0.005%。
- 通過標準（計入本批 Holm）：fv5 + R 相對 fv5 的年化淨報酬差 ≥ +0.10 個百分點、兩段差皆 > 0、兩段 Sharpe 皆不低於 fv5、配對日報酬差全期 Newey-West t ≥ 2.58。
- 只報告：只用多方出場、只用空方出場兩個拆解版本（不作判定，避免事後挑選）；釋出資金平均加碼到同份資金同腿其他持股的版本；衝突持股比例與其之後 60 日報酬；年換手與成本的變化；fv5x + R。
- 資料窺探：QEAR 的 60 日預測力已看過；fv5 持股內的衝突出場效果沒看過。I068 的診斷提示空方可能有害，但事前固定兩腿都用，拆解只報告。通過也只作為是否加入 fv5 前瞻執行規則的依據，由使用者決定，不改寫已登錄的 fv5 家族紀錄。
- 本批 Holm 校正（5 張卡、α = 5%、雙尾）：依 p 值由小到大的門檻為 t ≥ 2.58、2.50、2.39、2.24、1.96。未通過即停止，不改門檻、出場日或改為加權重測。

## 與已測點子的關係

- 季報公告的價格反應（季報 EAR）：以公開資訊觀測站實際財報董事會日期計算的 2 日產業調整報酬，對 SUE 與月營收 EAR 的增量（card:已測：H1 通過、H2 未通過（不另立前瞻），research/ideas/I070-quarterly-report-announcement-return.md）：命中 季報公告, 季報公告期報酬, QEAR, earnings announcement return, announcement return, post-earnings announcement drift
- 季報公告反應的事件時間進場（I070 後續）：QEAR 前 1/3 在反應窗結束後立即做多、持有 60 日、台指期對沖，檢驗 I070 H2 失敗是否來自期限後才進場（card:待確認，research/ideas/I073-qear-event-time-long-entry.md）：命中 季報公告期報酬, QEAR, post-earnings announcement drift, earnings announcement return, I070 後續
- 月營收公告期間的市場反應（公告期報酬）對 SUE 的增量：價格反應是否帶有營收數字以外的資訊（card:已測：H1 通過、H2 未通過（不另立前瞻），research/ideas/I063-revenue-announcement-window-return-ear.md）：命中 公告期報酬, earnings announcement return, announcement return, EAR
- 月營收公告期報酬（EAR）的獨立多空與 fv5 各半組合：EAR 是否提供 fv5 之外的報酬來源（I063 後續，以跨越檢定判定）（card:已測：未通過，research/ideas/I068-ear-standalone-ls-fv5-blend.md）：命中 公告期報酬, EAR, announcement return, earnings announcement return
- 月營收的可預期季節性（Chang–Hartzmark–Solomon–Soltes 台股月頻版）：即將公告的月份歷來是營收旺月的股票，公告期報酬較高（card:待確認，research/ideas/I072-revenue-seasonality-announcement-return.md）：命中 公告期報酬, EAR, announcement return
- fv5 腿內依 EAR 加權（SUE 與公告期報酬同向加碼、反向減碼）：名單不變只調權重，以第 501–1000 名選規則、第 1001–1500 名確認（card:待確認，research/ideas/I069-fv5-inleg-ear-agreement-weight.md）：命中 公告期報酬, EAR
- 金融股自結盈餘驚奇低換手多空（緩衝換倉）（failed，docs/fin_esue_followup_report.md）：命中 換手
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 fv5
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- 季報盈餘驚奇（failed，docs/revenue_surprise_plus_report.md）：命中 post-earnings announcement drift
- 年度盈餘驚奇改用實際董事會決議日：年報公告後的盈餘漂移（PEAD）（card:已測：未通過，research/ideas/I007-annual-earnings-surprise-actual-board-da.md）：命中 post-earnings announcement drift
- 季報盈餘驚奇改用實際公告日：公開資訊觀測站重大訊息的財報董事會日期（card:暫緩（I007 顯示 2023 後無可交易漂移），research/ideas/I008-quarterly-pead-actual-announcement-date.md）：命中 post-earnings announcement drift
- 美股大型科技公司財報反應對台股連結股的延遲傳遞（客戶／同業財報 → 台灣供應鏈）（card:已測：未通過，research/ideas/I016-us-earnings-to-taiwan-linked-stocks.md）：命中 earnings announcement return
- 金融股自結盈餘驚奇的低換手多空（緩衝換倉）（card:已測：未通過，research/ideas/I017-financial-esue-low-turnover-ls.md）：命中 換手
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5
- 營收已知下的利潤率驚奇：季報營業利益率相對月營收隱含水準的驚奇（card:已測：未通過（前 500 名 t 1.9，驗證樣本顯著），research/ideas/I037-operating-margin-surprise-given-revenue.md）：命中 季報
- 季報公告溢酬：預期即將公告季報的前 500 名股票在公告前後是否有正報酬（與 I048 共用公告日資料）（card:待確認，research/ideas/I052-quarterly-earnings-announcement-premium.md）：命中 季報公告
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:已測：未通過，research/ideas/I054-fv5-entry-execution-price.md）：命中 fv5
- fv5 空方腿避開融券回補買壓：新空單若在 10 個交易日內遇到停券窗，延到最後回補日收盤再建倉（訊號與名單不變，只改建倉時點）（card:已測：未通過（只在 2023 年後有效），research/ideas/I059-fv5-short-defer-stop-window.md）：命中 fv5
- fv5 家族的稅後績效與除息日建倉規則：個人投資人股利所得稅與二代健保補充保費下，多方新倉延到除息後是否改善稅後報酬（card:已測：R1 未通過（稅後績效已報告），research/ideas/I061-fv5-after-tax-exdiv-entry.md）：命中 fv5
- 補充：與 I069（依月營收 EAR 調整腿內權重，建議暫緩）不同：本卡用季報反應、事件時間觸發、只做出場不加碼，換手增加有限。與 I073 共用 QEAR 訊號，但本卡不另建部位。與 I065（空方停損，看價格累積漲幅）不同：本卡只在季報公告這個資訊事件觸發。

研究點子，非投資建議。
