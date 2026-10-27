# I070 季報公告的價格反應（季報 EAR）：以公開資訊觀測站實際財報董事會日期計算的 2 日產業調整報酬，對 SUE 與月營收 EAR 的增量

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 事件型橫斷面訊號（Fama-MacBeth 增量）＋跨越檢定與可交易建構 | free | 約 0（公告日期已在 I048 抓好；前 1500 名還原價、月營收、產業分類已快取） | 2026-10-27 |

## 假設

在市值前 500 名中，季報公告（公開資訊觀測站『董事會通過第 X 季財務報告』）反應日與次日的 2 日產業調整報酬（QEAR）愈高，公告後第 +2 日起 60 個交易日的產業調整報酬愈高；控制最新月營收 SUE、最新月營收 EAR、前 60 日報酬與市值後，Fama-MacBeth 全期 t ≥ 2.58、兩段同號，第 1001–1500 名同號 t ≥ 2.0。

## 機制（為什麼會有超額報酬）

季報揭露月營收沒有的資訊（毛利、費用、業外、存貨），I037／I048 用會計數字算的利潤率驚奇在前 500 名不顯著，可能是會計驚奇量測雜訊大（季報沒有分析師預期可比較）；價格反應直接整合市場對整份季報的解讀，若後續反應不足，QEAR 應有漂移（Brandt 等 2008 以公告期報酬衡量驚奇；Chan 等 1996）。I063 已證實同一個邏輯在月營收公告上成立。反方：前 500 名法人多、季報資訊在 2 日內反映完畢，或 I007 顯示盈餘訊號的漂移在 2023 年後消失。

## 出處

- （工作論文，經二手摘要）Brandt、Kishore、Santa-Clara、Venkatachalam（2008）Earnings announcements are full of surprises，Duke University 工作論文，Quantpedia 摘要 https://quantpedia.com/strategy-tags/earnings-announcement/：以公告期價格反應排序有公告後漂移；全文未讀到，數字不引用
- （同儕審查）Chan、Jegadeesh、Lakonishok（1996）Momentum Strategies，Journal of Finance 51(5)，https://ideas.repec.org/a/bla/jfinan/v51y1996i5p1681-1713.html：依摘要，盈餘驚奇（含公告期報酬衡量）與過去報酬各自預測漂移
- （工作論文，NBER）Novy-Marx（2015）Fundamentally, momentum is fundamental momentum，https://www.nber.org/papers/w20984：依摘要，盈餘驚奇在橫斷面迴歸中涵蓋過去報酬的預測力
- （本專案）docs/revenue_ear.md（I063）：月營收公告期報酬在三個名次組、兩段都顯著
- （本專案）docs/margin_surprise_actual_report.md（I048）：同一批公開資訊觀測站財報董事會公告（56,641 則），會計利潤率驚奇在前 500 名不顯著（t 1.0）、中小型股顯著
- （本專案）docs/earnings_board_date_report.md（I007）：年度盈餘驚奇在實際決議日有預測力，但集中在 2019–2022

## 台股適用性

台灣季報公告日分散在法定期限（Q1 5/15、Q2 8/14、Q3 11/14、年報 3/31）前數週；I048 已把公開資訊觀測站重大訊息整理成 data_cache/events/fin_report_headlines.csv（2020-07 ~ 2026-05，含發言時間 spoke_time），可判斷盤中或盤後公告。限制：(1) 2020 上半年以前多數公司不發此類公告，樣本只有 2020Q2 財報起（約 23 季），第一段較短；(2) 季報與月營收在 4、5、8、11 月的公告期重疊，必須控制同月的月營收 EAR，以免重複計算；(3) 公告在盤後者，反應日為下一交易日；漲跌停截斷比例需報告。沒有找到台股以季報公告期報酬為訊號的研究。

## 所需資料

- data_cache/events/fin_report_headlines.csv（公開資訊觀測站財報董事會公告，I048 已抓）：公告日與發言時間
- FinMind TaiwanStockPrice 還原價（已快取）：QEAR、後續報酬、前 60 日報酬
- FinMind TaiwanStockMonthRevenue（已快取）：SUE、月營收 EAR
- config/universe_mcap_membership.csv、config/universe_mcap_membership_1500.csv
- analysis/margin_surprise_actual.py（公告標題解析與季別對應的寫法）

## 檢定計畫（看結果前固定）

- 樣本：前 500 名（公告當時成員），2020Q2 ~ 2025Q4 財報（公告日 2020-07 ~ 2026-04-30；2026Q1 財報公告在 5 月、屬保留樣本不用）；兩段以公告日分 2020-07 ~ 2022-12 / 2023-01 ~ 2026-04；確認樣本第 1001–1500 名；第 501–1000 名只報告。同一公司同季只取第一則（排除更正公告）。
- 訊號：反應日 t0 = 發言時間 13:30 前為公告日、否則為下一交易日；QEAR = 收盤(t0−1) → 收盤(t0+1) 的報酬減同產業等權平均。
- 被解釋變數：收盤(t0+1) → 收盤(t0+61) 的產業調整報酬（以 t0+1 收盤進場，可交易視窗從 +2 起）。
- H1（主判定）：每個財報季的橫斷面迴歸（被解釋變數與自變數皆為產業內百分位），控制 t0 前最新月營收 SUE、最新月營收 EAR、t0−1 前 60 日產業調整報酬、log 市值；Fama-MacBeth 跨季平均。通過：全期 t ≥ 2.58（本批 Holm 最嚴門檻）、兩段同號且第二段 t ≥ 1.5、第 1001–1500 名同號且 t ≥ 2.0。
- H2（只在 H1 通過時做，可交易）：每個法定期限後第一個交易日，以期限前 60 日內公告的 QEAR 排序，產業內前／後 1/3 等權多空，持有 60 個交易日、借券條件 D、單邊 0.29625% 成本、借券費、台指期對沖；以 I068 的跨越迴歸（對 fv5 與 5 個風格因子）判定，截距 t ≥ 2.0 且兩段 > 0，且 fv5 與 QEAR 多空各半資金的全期 Sharpe ≥ 1.74。
- 只報告：事件時間的平均累積異常報酬（+2 ~ +61，QEAR 三分組）；QEAR 與 I048 利潤率驚奇的相關；盤後公告比例；反應日觸及漲跌停的比例；只用年報或只用 Q1–Q3 的版本。
- 資料窺探：同一批公告日已用於 I048 的會計驚奇（前 500 名不顯著）；公告期價格反應從未計算。I063 的成功是本卡的動機，所以門檻沿用 2.58 並要求獨立樣本確認；未通過即停止，不改反應視窗（如 3 日、5 日）重測。

## 與已測點子的關係

- 月營收公告期間的市場反應（公告期報酬）對 SUE 的增量：價格反應是否帶有營收數字以外的資訊（card:已測：H1 通過、H2 未通過（不另立前瞻），research/ideas/I063-revenue-announcement-window-return-ear.md）：命中 公告期報酬, 價格反應, earnings announcement return, announcement return, EAR
- 月營收公告期報酬（EAR）的獨立多空與 fv5 各半組合：EAR 是否提供 fv5 之外的報酬來源（I063 後續，以跨越檢定判定）（card:待確認，research/ideas/I068-ear-standalone-ls-fv5-blend.md）：命中 公告期報酬, EAR, announcement return, earnings announcement return, fundamental momentum
- 年度盈餘驚奇改用實際董事會決議日：年報公告後的盈餘漂移（PEAD）（card:已測：未通過，research/ideas/I007-annual-earnings-surprise-actual-board-da.md）：命中 實際公告日, post-earnings announcement drift, pead
- 季報盈餘驚奇改用實際公告日：公開資訊觀測站重大訊息的財報董事會日期（card:暫緩（I007 顯示 2023 後無可交易漂移），research/ideas/I008-quarterly-pead-actual-announcement-date.md）：命中 財報董事會, post-earnings announcement drift, pead
- 年度盈餘驚奇改用實際董事會決議日（failed，docs/earnings_board_date_report.md）：命中 pead, 實際公告日
- 季報盈餘驚奇（failed，docs/revenue_surprise_plus_report.md）：命中 pead, post-earnings announcement drift
- fv5 腿內依 EAR 加權（SUE 與公告期報酬同向加碼、反向減碼）：名單不變只調權重，以第 501–1000 名選規則、第 1001–1500 名確認（card:待確認，research/ideas/I069-fv5-inleg-ear-agreement-weight.md）：命中 公告期報酬, EAR
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 財報 Agent（營收、毛利、存貨、應收）（partial，forward/REPORT.md）：命中 財報
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue
- 月營收依公告日提早進場（failed，docs/sue_event_entry_report.md）：命中 公告日
- 12-1 動能、持續性動能、frog-in-the-pan（failed，docs/revmom_persist_report.md）：命中 momentum
- 美股大型科技公司財報反應對台股連結股的延遲傳遞（客戶／同業財報 → 台灣供應鏈）（card:已測：未通過，research/ideas/I016-us-earnings-to-taiwan-linked-stocks.md）：命中 earnings announcement return
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 營收已知下的利潤率驚奇：季報營業利益率相對月營收隱含水準的驚奇（card:已測：未通過（前 500 名 t 1.9，驗證樣本顯著），research/ideas/I037-operating-margin-surprise-given-revenue.md）：命中 季報
- 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）（card:已測：未通過（階段 1 過、階段 2 t 2.8），research/ideas/I043-smallcap-multifactor-composite.md）：命中 sue
- 利潤率驚奇改用季報實際公告日：前 500 名的期限前漂移（I037 的事後追加，以從未看過的視窗與第 1001–1500 名確認）（card:已測：未通過（前 500 名 t 1.0；中小型股顯著），research/ideas/I048-margin-surprise-actual-announcement-date.md）：命中 財報董事會日期
- 季報公告溢酬：預期即將公告季報的前 500 名股票在公告前後是否有正報酬（與 I048 共用公告日資料）（card:待確認，research/ideas/I052-quarterly-earnings-announcement-premium.md）：命中 季報公告
- 融券強制回補的價格壓力（I050 修訂版）：以官方停券日為事件日，在未看過的第 501–1500 名確認，處理 I056 附帶發現的資料窺探（card:已測：未通過（P2 t 1.3；I059 啟動條件成立），research/ideas/I058-forced-covering-oos-501-1500.md）：命中 第 1001–1500 名
- 補充：與 I037／I048（會計利潤率驚奇）不同：本卡用價格反應而非會計數字。與 I052（季報公告前後的溢酬，事件本身的報酬）不同：本卡把公告期報酬當訊號，預測公告後 60 日。與 I007（年度盈餘驚奇，2023 年後無效）不同：涵蓋四季且是價格反應。與 I063 不同：事件是季報而非月營收，並控制月營收 EAR。

研究點子，非投資建議。
