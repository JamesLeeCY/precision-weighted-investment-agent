# I006 股利政策公告驚奇：董事會決議現金股利相對預期的增減與公告後漂移

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 事件研究（CAR＋日曆時間組合），附截面迴歸控制盈餘驚奇 | free（FinMind）＋manual（公開資訊觀測站董事會決議日） | FinMind：主樣本前 500 名約 1,220 次（TaiwanStockDividend 776 檔中已快取 85 檔→約 690 次；TaiwanStockFinancialStatements 已快取 245 檔→約 530 次）；第 501–1000 名驗證約 1,860 次（股利約 975＋財報約 880）；合計約 3,100 次（免費 600 次/小時，約 6 小時，可分批）。公開資訊觀測站：若『股利分派情形』可不填公司代號整批查詢，約 8 年 × 2 市場 ≈ 16–50 次；若只能逐家查，約 1,800 次（每 3 秒一次約 1.5 小時） | 2026-10-15 |

## 假設

董事會決議的年度現金股利相對預期（主定義：去年配息率 × 今年 EPS 推得的預期股利）明顯偏高的股票，在決議公告後第 +2 ~ +40 個交易日（且不跨入除息交易日公告日）的累積異常報酬高於明顯偏低者；在控制年度盈餘驚奇與月營收 SUE 後，股利驚奇的係數仍為正。

## 機制（為什麼會有超額報酬）

訊號理論與反應不足：股利是管理層對盈餘持續性的承諾（Lintner 平滑），超出盈餘所能解釋的加減配代表管理層的私有資訊；投資人對股利變動的反應不足而延後調整（Michaely, Thaler & Womack 1995 的初次配息／停配後漂移）。台股特有的輔助機制：存股族與高股息 ETF 依殖利率選股，股利公告後殖利率排名改變，資金在之後數週逐步移動（高股息 ETF 多在 5–6 月、11–12 月依殖利率換股，可能帶來延遲價格壓力）。反方證據：Grullon 等（2005）發現股利變動不預示未來獲利；Liu, Szewczyk & Zantout（2008）發現減配／停配後的漂移在控制盈餘後消失——所以本卡的關鍵是『控制盈餘驚奇後是否還有剩』。

## 出處

- （同儕審查）Michaely, Thaler & Womack（1995）Price Reactions to Dividend Initiations and Omissions: Overreaction or Drift?，Journal of Finance，https://doi.org/10.1111/j.1540-6261.1995.tb04796.x：初次配息／停配後一年內價格繼續同向漂移，停配後較強；摘要稱此漂移與盈餘驚奇後的漂移不同且更明顯；NBER 版（https://doi.org/10.3386/w4778）列出公告 3 日反應停配 −7.0%、初次配息 +3.4%
- （同儕審查，反方）Liu, Szewczyk & Zantout（2008）Underreaction to Dividend Reductions and Omissions?，Journal of Finance，https://doi.org/10.1111/j.1540-6261.2008.01337.x：1927–1999 年 2,337 次減配／停配，之後 1 年異常報酬為負，但由盈餘公告後漂移驅動；控制盈餘與偏態後沒有可靠的漂移
- （同儕審查，反方）Grullon, Michaely, Benartzi & Thaler（2005）Dividend Changes Do Not Signal Changes in Future Profitability，Journal of Business，https://doi.org/10.1086/431438：股利變動不能預測未來獲利變化（只讀到標題與引用資訊，未讀全文）
- （同儕審查，台灣）作者未確認（2017）Institutional Trading and Stock Returns around Dividend Announcements: Evidence from Taiwan，中國財務學刊 25(4)，https://doi.org/10.6545/jfs.2017.25(4).4：股利宣告增加時法人沒有資訊優勢、國內法人交易後價格短暫衝擊再反轉；股利宣告減少後外資有資訊優勢、可得較高異常報酬（只讀到摘要，事件日定義與數字未確認）
- （同儕審查，台灣）作者未確認（2001）The Information Content of Dividend Announcements: The Case of Taiwan，Pan-Pacific Management Review，https://doi.org/10.30166/ppmr.200108.0006：1987–1997 台股現金股利公告的『未預期股利』與報酬相關，支持資訊內涵假說，但加入與其他變數的交互作用後結論較弱（只讀到摘要）
- （工作論文／資料庫摘要，台灣，與本卡不同事件日）Price and Volume Reactions to Cash Dividend Announcements: Evidence from Taiwan（2014），https://openalex.org/W1516881029：實際研究的是除息日前後（除息前 11 日買、除息後 10 日賣約 +2.1%），屬於本專案已測的除息日事件，不是董事會公告日
- （部落格／資料庫）Quantpedia Update 2012-08（策略 Dividend Announcement Effect，來源為 Boehme & Sorescu 2002 初次配息與恢復配息後的長期表現），https://vvv.quantpedia.com/?p=517：只作為點子來源，未讀到原文數字

## 台股適用性

台股的股利決議時點集中且與年報同日：一般公司在 2–3 月（法定期限 3/31 前）董事會同時通過年度財報與盈餘分配案（例：鴻海 2025-03-14 董事會同時通過 2024 年財報與每股 5.8 元現金股利，新聞見 https://www.businesstoday.com.tw/article/category/183015/post/202503140033/ ），季配息公司（台積電等）則在每季財報董事會決議（例：台積電 2025-11-11 決議 2025Q3 每股 6 元，https://finance.technews.tw/2025/11/11/tsmc-q3-dividend-6ntd/ ）。因此台股的股利驚奇幾乎一定與年度盈餘公告同日，必須在同一事件內控制盈餘驚奇，否則只是在測已失敗的『季報盈餘驚奇』（docs/revenue_surprise_plus_report.md，該研究用法定期限、不是實際公告日）。台股配息率高（多數公司 50% 以上）、殖利率導向投資人多，股利訊號的價格影響可能大於美股；但台灣只有摘要層級的實證，而且 2017 年那篇指出增加配息後國內法人造成的價格衝擊會反轉，方向上不一定是漂移。漲跌停 ±10% 對大型股影響小。

## 所需資料

- 公開資訊觀測站 股利分派情形（mopsov.twse.com.tw/mops/web/t05st09_2，欄位含『董事會決議（擬議）分配股利年度』與股利所屬年度；結果是否含決議日期與能否整批查詢待確認）或 重大訊息『董事會決議股利分派』：事件日（董事會決議日）與擬議現金股利 DPS——本卡的關鍵新資料
- FinMind TaiwanStockDividend：CashEarningsDistribution＋CashStatutorySurplus（每股現金股利，用來核對 MOPS 金額、建去年 DPS）、year（股利所屬年度／季度）、AnnouncementDate（經查證為除權息交易日公告日，用作持有期上限，不是事件日）
- FinMind TaiwanStockFinancialStatements：年度 EPS 與歸屬母公司淨利（配息率、盈餘驚奇控制變數；沿用 revenue_surprise_plus.earnings_surprise 的寫法）
- FinMind TaiwanStockDividendResult＋TaiwanStockPrice（已快取）：還原含息報酬、異常報酬（同 dividend_events.py）
- FinMind TaiwanStockMonthRevenue（已快取）：事件日前最新一期月營收 SUE（控制變數）
- config/universe_mcap_membership.csv：市值前 500／第 501–1000 名與產業

## 檢定計畫（看結果前固定）

- 樣本：董事會決議年度現金股利的事件，決議日 2019-01 ~ 2026-04；主樣本為決議當年市值前 500 名，獨立驗證為第 501–1000 名（兩者不重疊）；分 2019–2022 與 2023–2026/04 兩段；2026-05 以後不用。只用『年度』股利（股利所屬期間為全年）；季配／半年配公司（台積電、聯發科等）單獨列表報告，不納入通過判定。去年未配、今年也未配的公司不算事件。
- 事件日 t0：公開資訊觀測站的董事會決議日；若申報時間在收盤後或無時間資訊，一律視為盤後公告。可交易視窗從第 +2 日起（第 +1 日收盤進場），與本專案慣例一致。先抽 30 檔與新聞核對決議日；若決議日拿不到，改用備案（見最後一條）。
- 股利驚奇（看結果前固定）：主定義 DS_payout =（今年 DPS − 去年配息率 × 今年 EPS）÷ t0−1 日收盤價；去年配息率 = 去年 DPS ÷ 去年 EPS，限制在 [0, 1.5]，去年 EPS ≤ 0 時改用 DS_raw。次要定義（只報告）DS_raw =（今年 DPS − 去年 DPS）÷ t0−1 日收盤價。另標記初次配息（去年 0、今年 > 0）、停配（去年 > 0、今年 0）兩類，單獨報告。DPS = 盈餘配息＋公積配息（現金），以 MOPS 金額為準，與 FinMind CashEarningsDistribution＋CashStatutorySurplus 交叉核對。
- 分組：每年在事件樣本內依 DS_payout 分三組（前 30% ＝ 加配、後 30% ＝ 減配、中間），主要比較『前 30% − 後 30%』。
- 異常報酬：還原含息報酬 − β × 加權指數含息報酬（沿用 dividend_events.py 的 ar 建構與 event_study.car、date_clustered 的日期分群 t 值）。視窗：[−1, +1]（公告反應，不可交易，只報告）、[+2, +20]、[+2, +40]（主要）。持有期上限：若除權息交易日公告日（FinMind AnnouncementDate）早於 t0+40，則在該日前一個交易日截止——避開已測的『除息前布局』（除息前 10 日約 +0.6–1.0%）與『除息後偏弱』兩個已知效果。另報告截止比例。
- 控制盈餘驚奇（關鍵）：每段做截面迴歸（以事件年為群、標準誤依決議日分群）CAR[+2,+40] = a + b1·DS_payout_rank + b2·ES_rank + b3·SUE_rank + b4·殖利率_rank + b5·log 市值 + 產業虛擬變數；ES = 年度歸屬母公司淨利年差 ÷ 過去 8 季年差標準差（同 revenue_surprise_plus.earnings_surprise，但在實際決議日使用而不是 3/31），SUE = t0 前最新月營收 SUE（data/revenue_signal.revenue_surprise），殖利率 = 今年 DPS ÷ t0−1 收盤價。報告 DS_payout 與 ES、SUE 的相關。看 b1；另報告雙重排序（ES 三分位內的 DS 前後 30% 差）。
- 可交易版本（日曆時間組合）：第 +1 日收盤等權做多加配組、放空減配組，持有至 +40 日或除權息交易日公告日前一日；可借條件與借券費同 borrow_capacity.py（條件 D），剩餘 β 以台指期對沖；同時報告只做多（台指期對沖）的版本，因為減配股的可借量可能不足。事件集中在 2–3 月，所以組合約有 2–3 個月有部位；用 event_study.calendar_portfolio＋simulate_daily 的寫法。
- 成本：股票單邊 0.29625%（買進手續費＋賣出手續費與 0.3% 證交稅），每個事件一買一賣約 0.59%；借券費逐日扣；台指期單邊 0.005%。另報告第 +1 日漲停（做多買不到）、跌停（放空借不到或賣不掉）比例。
- 通過標準（全部成立）：(1) 主樣本 CAR[+2,+40] 前 30% − 後 30% 在兩段同號且皆 > 0、日期分群 t > 2；(2) 控制 ES、SUE、殖利率後，b1 在兩段皆 > 0，合併 t > 2；(3) 第 501–1000 名驗證樣本 (1) 同號且 t > 2；(4) 多空或只做多（台指期對沖）版本扣成本後兩段 Sharpe 皆 > 0。若 (1)(3) 成立但 (2) 不成立，記為『股利驚奇只是盈餘驚奇的代理』＝failed；若 (1)–(3) 成立但 (4) 不成立，記為 partial（可改當 SUE 做多名單的濾網，另立新假設）。
- 備案（決議日拿不到時，事前固定，只能得出較弱結論）：事件日改為年報法定期限 3/31，第一個交易日收盤進場，用同一個 DS_payout，在每年 4 月初做一次產業內 IC（leg_probe.within_ic，fwd20／fwd40）與控制 ES、SUE 的 Fama-MacBeth；通過標準為兩段 IC > 0 且合併 t > 2、控制後係數同號。注意已失敗的盈餘驚奇正是在這種法定期限時點下失敗，所以備案通過的機率較低，只能測『公告後 1 個月以上的慢漂移』。

## 與已測點子的關係

- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 除息後偏弱（高殖利率）（candidate，docs/dividend_events_report.md）：命中 除息
- 月營收依公告日提早進場（failed，docs/sue_event_entry_report.md）：命中 公告日
- 季報盈餘驚奇（failed，docs/revenue_surprise_plus_report.md）：命中 盈餘驚奇
- 補充：與已測的除權息事件（docs/dividend_events_report.md：除息前布局、填息無效；除息後偏弱為候選）不同：事件日是董事會決議股利的日子（多在 2–3 月），不是除息日（多在 6–9 月）。經查證 FinMind TaiwanStockDividend 的 AnnouncementDate 是除權息交易日的公告日（在除息日前約 2–4 週；例：鴻海 2025 年 AnnouncementDate 為 06-17，但董事會決議是 03-14；台積電 2025Q3 股利 AnnouncementDate 為 2026-03-02，但董事會決議是 2025-11-11），之前 dividend_events.py 也是這樣用它；所以本卡不能直接用 FinMind 的日期當事件日，需要公開資訊觀測站的決議日。重疊控制：持有期在除權息交易日公告日前一日截止，並在迴歸中控制殖利率。與月營收 SUE（effective）與季報盈餘驚奇（failed，用 3/31 法定期限）的關係：台股年度股利與年報同日董事會通過，股利驚奇很可能只是盈餘驚奇的代理；本卡用『超出去年配息率 × 今年 EPS 的部分』定義驚奇，並在同一實際公告日控制 ES 與 SUE，通過與否以控制後的係數為準。附帶產出：MOPS 決議日同時是年報實際公告日，可用來重測『盈餘驚奇用實際公告日』（revenue_surprise_plus_report 的結論提到值得重測），但那是另一個假設，不列入本卡的通過判定。

研究點子，非投資建議。
