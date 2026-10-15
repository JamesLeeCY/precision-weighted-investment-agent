# I007 年度盈餘驚奇改用實際董事會決議日：年報公告後的盈餘漂移（PEAD）

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | A | 事件研究（CAR＋日曆時間組合），附截面迴歸控制 SUE，並檢查與 fv3 合成 | free | 主檢定約 0（股利分派彙總表 18,479 列、前 500 名價格與月營收已快取）；驗證樣本的 SUE 與營收年增率控制約 580 次 FinMind 月營收；選做的第 4 季單季淨利（次要定義）約 1,400 次 TaiwanStockFinancialStatements；選做的 2021 年後實際財報日穩健性檢查約 300 次公開資訊觀測站請求（與 I008 共用） | 2026-10-15 |

## 假設

在公開資訊觀測站「股利分派情形彙總表」的董事會決議日（年報實際公告日的上界）之後，年度本期淨利年變動 ÷ 決議前一日市值（ES）位於當年前 30% 的股票，第 +2 ~ +40 個交易日的累積異常報酬高於後 30%；控制事件前最新的月營收 SUE 與全年營收年增率後，ES 的係數仍為正。

## 機制（為什麼會有超額報酬）

反應不足（Ball & Brown 1968；Bernard & Thomas 1989/1990）：投資人沒有充分把當期盈餘對未來盈餘的含意反映進價格，漂移集中在公告後約 60 個交易日。之前的季報盈餘驚奇（failed）用法定期限 3/31、5/15 等作為可用日，最多晚了近 3 個月才使用盈餘資訊，漂移可能早已走完；改用實際公告日就能檢查『失敗是因為時點太晚』這個說法。台股輔助機制：2–3 月是年報、股利、股東會議案同時密集公告的時期，同日公告家數多，注意力被分散（Hirshleifer, Lim & Teoh 2009），反應不足可能比平常更強。反方：台灣有月營收，全年營收早在 1 月 10 日前已知，年度盈餘的新資訊只剩毛利、費用與業外，漂移可能多半已被 SUE 吸收；Fu（2014）發現台股第 4 季（年報）公告後的漂移比第 1 季弱，因為年報的法定期限較長、私有資訊有更多時間擴散。

## 出處

- （本專案事後觀察，非獨立證據）docs/dividend_surprise_report.md：I006 迴歸中當控制變數的『本期淨利年變動 ÷ 市值』排名，對 CAR[+2,+40] 的係數為 +5.9%（t 5.4，事件數 3,270，前 500 名），2019–2022 為 +6.2%（t 4.3）、2023–2026/04 為 +4.4%（t 2.8）；同一迴歸含股利驚奇（與盈餘變動相關 −0.40）、SUE、殖利率、市值、產業與年度。這是看過結果才挑出來的係數，只能當假設來源
- （同儕審查）Ball & Brown（1968）An Empirical Evaluation of Accounting Income Numbers，Journal of Accounting Research，https://doi.org/10.2307/2490232：年度盈餘的正負變動與公告前後的異常報酬同向，公告後仍有延續（PEAD 的起點；本次只核對書目，未讀全文數字）
- （同儕審查）Bernard & Thomas（1989）Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?，Journal of Accounting Research，https://doi.org/10.2307/2491062：PEAD 較支持延遲反應而非風險補償（只讀到書目與關鍵詞）
- （同儕審查）Bernard & Thomas（1990）Evidence that stock prices do not fully reflect the implications of current earnings for future earnings，Journal of Accounting and Economics，https://doi.org/10.1016/0165-4101(90)90008-R：價格沒有充分反映當期盈餘對未來盈餘的含意（只核對書目）
- （同儕審查）Livnat & Mendenhall（2006）Comparing the Post-Earnings Announcement Drift for Surprises Calculated from Analyst and Time Series Forecasts，Journal of Accounting Research，https://doi.org/10.1111/j.1475-679x.2006.00196.x：摘要指出用分析師預期定義驚奇的漂移明顯大於時間序列模型——本卡只能用時間序列（年變動）型驚奇，效果可能偏小
- （同儕審查）Hirshleifer, Lim & Teoh（2009）Driven to Distraction: Extraneous Events and Underreaction to Earnings News，Journal of Finance，https://doi.org/10.1111/j.1540-6261.2009.01501.x：同日其他公司公告越多，公告當下反應越弱、之後漂移越強
- （同儕審查）Chambers & Penman（1984）Timeliness of Reporting and the Stock Price Reaction to Earnings Announcements，Journal of Accounting Research，https://doi.org/10.2307/2490700：公告時點本身帶資訊（早公告多為好消息、晚公告多為壞消息；只核對書目，內容依常見引述）；Haw, Qi & Wu（2000）JIFMA https://doi.org/10.1111/1467-646x.00058 在中國 A 股得到同樣結果，虧損公司最晚公布——所以本卡要控制公告時點
- （同儕審查，國際）Hung, Li & Wang（2015）Post-Earnings-Announcement Drift in Global Markets: Evidence from an Information Shock，Review of Financial Studies，https://doi.org/10.1093/rfs/hhu092：非美國市場普遍有 PEAD，財報品質提高（IFRS）後漂移下降，支持有限注意力的解釋
- （同儕審查，台灣，反方）Fu（2014）Seasonality of Earnings Momentum in an Emerging Market: The Taiwan Experiences，International Journal of Financial Research，https://doi.org/10.5430/ijfr.v5n1p71：台股第 1 季公告後 6–12 個月的漂移明顯大於第 4 季（年報），作者歸因於年報法定期限較長；摘要未給數字
- （工作論文，台灣）Huang, Chiu & Tsai（2024）Investors' Trading Behavior and Post-Earnings-Announcement Drift: Evidence from Taiwan，SSRN https://doi.org/10.2139/ssrn.4785992 及同作者 https://doi.org/10.2139/ssrn.4853649：台股 PEAD 與各類投資人交易的關係（SSRN 擋下讀取，只讀到標題，未確認結論）
- （研究計畫摘要，台灣）Timely Monthly Sales Disclosure, Earnings Volatility, and Market Reactions to Earnings Surprises（2020，文化大學機構典藏），https://openalex.org/W7111563851：預期及時的月營收揭露會減少盈餘公告後的延遲反應——對應本卡必須控制 SUE
- （同儕審查，方法）Harvey, Liu & Zhu（2016）… and the Cross-Section of Expected Returns，Review of Financial Studies，https://doi.org/10.1093/rfs/hhv059：多重檢定下新因子應要求 t > 3；本卡的主樣本係數是事後選出，所以判定以獨立驗證樣本為主
- （論壇）PTT Stock 每季有大量『[情報] XXXX 財報 EPS』貼文（例：https://www.ptt.cc/bbs/Stock/M.1786010457.A.639.html），只說明散戶在公告當天就看到數字，不是報酬證據

## 台股適用性

台股的年報與年度盈餘分配案多半在同一次董事會通過：用本次快取的 3 個 2–3 月旺季日期比對公開資訊觀測站『每日重大訊息』中『董事會通過年度財務報告』的日期，約 80% 與股利表的決議日同一天，其餘大多是股利決議晚於財報（晚 1–8 週）。所以決議日是財報實際公告日的『上界』：不會偷看未來，最多晚用。決議日晚於 3/31（法定期限）的事件占前 500 名的 12–20%，這些公司的財報在 3/31 前已公告，決議日不是盈餘的公告日，事先排除在主檢定外。台股沒有可用的免費分析師預期，只能用年變動（季節性隨機漫步）定義驚奇；年度資料一年只有一個點，所以只能做『今年 − 去年』型的驚奇。月營收讓全年營收在 1 月 10 日前就已公開，年度淨利變動有一部分已被 SUE 反映，這是本卡最大的反方風險。漲跌停 ±10% 對前 500 名影響小（I006 的第 +1 日漲停 3.6%、跌停 1.8%）。

## 所需資料

- 公開資訊觀測站 股利分派情形彙總表（data_cache/events/mops_dividend/，已快取 107–115 年上市與上櫃）：董事會決議日、股利所屬期間、本期淨利、現金股利總額。已查證：不配息與虧損公司也有列（年度列中現金股利 0 占 25%，其中 73% 為虧損；前 500 名每年 7–11% 為 0 股利、5–10% 為虧損），決議日 108 年起 > 96% 有值、109 年起 > 99.8%；107 年（2018 決議）全為空值
- config/universe_mcap_membership.csv：當年 1 月市值前 500／第 501–1000 名、產業、1 月市值；事件市值 = 1 月市值 × （t0−1 收盤 ÷ 1 月換股日收盤）——不配息公司在股利表內無每股股利，不能用『總額 ÷ 每股』算股數
- FinMind TaiwanStockPrice、TaiwanStockDividendResult、TaiwanStockTotalReturnIndex（已快取，dividend_events.load_sample）：還原含息報酬、β、除息日
- FinMind TaiwanStockMonthRevenue（前 500 名已快取；第 501–1000 名約 580 次）：t0 前最新 SUE（data/revenue_signal.revenue_surprise）與全年營收年增率
- FinMind TaiwanStockSecuritiesLending、TaiwanDailyShortSaleBalances（已快取）：可借條件與借券費；TaiwanFuturesDaily：台指期對沖
- （選做）FinMind TaiwanStockFinancialStatements：第 4 季單季淨利（次要定義 ES_q4）
- （選做）公開資訊觀測站 每日重大訊息 ajax_t05st02（每天一次請求，已試抓 10 天）：2021 年後『董事會通過年度財務報告』的實際日期，用來做事件日穩健性檢查

## 檢定計畫（看結果前固定）

- 事後選擇的處理（先寫清楚）：主樣本（前 500 名）2019–2026/04 的盈餘變動係數已經在 I006 看過，所以主樣本結果只算『確認沒有改變』；判定以第 501–1000 名驗證樣本為主（I006 在驗證樣本沒有跑盈餘變動迴歸，是乾淨的），另外把主樣本事件擴大到 I006 排除的『去年與今年都不配息』公司；本卡也排在前瞻紀錄之前，前瞻（2026-05 以後，下一次為 2027 年 2–3 月）才是最終驗證。本卡只測 1 個主定義、1 個主視窗、1 種分組，其餘只報告。
- 樣本：股利分派彙總表中股利所屬期間為『年度』的列（不論是否配息、是否虧損），每家公司每個會計年度取最早的決議日；決議日 2019-01 ~ 2026-04（2018 決議日全空，無法使用；2026-05 以後保留給前瞻）；主樣本 = 決議當年市值前 500 名，驗證 = 第 501–1000 名；兩段 2019–2022 / 2023–2026/04。主檢定只用決議日 ≤ 當年 3/31 的事件（決議日 ≈ 財報日）；決議日晚於 3/31 的事件（12–20%）單獨報告，事件日仍用決議日（不可用 3/31 代替，因為 2020 年疫情期間可能有延期申報，3/31 不一定安全）。
- 樣本選擇（必須報告）：(a) 季配與半年配公司沒有年度列（前 500 名 2023 年後約 10%，多為台積電、聯發科等大型股），從主檢定排除，列出每年被排除的比例與其市值占比；其第 4 季／下半年列只在 I008 使用。(b) 前 500 名每年約 1–6% 既無年度列也無季度列，列出名單特徵。(c) 不配息公司要納入（I006 只看有配息的事件）；另報告『只看有配息公司』的結果，看選擇偏誤是否改變結論。(d) 去年本期淨利缺值（新上市）的事件剔除。
- 事件日與進場：t0 = 決議日（視為盤後公告；若為非交易日，取下一個交易日）；第 +1 日收盤進場，可交易視窗從第 +2 日起。報告第 +1 日漲停（做多買不到）比例。
- 盈餘驚奇（事先固定）：主定義 ES = （今年本期淨利 − 去年本期淨利）÷ t0−1 日市值，與 I006 的附帶發現一致。次要定義（只報告）：ES_g = 淨利年變動 ÷ |去年淨利|，限制在 [−1, +1]（不需市值，對市值尺度不敏感）；ES_q4 = 第 4 季單季淨利年變動 ÷ 市值（去掉 Q1–Q3 已公告的舊資訊，需 FinMind 財報）；ES_sd = 淨利年變動 ÷ 過去年變動的標準差（至少 4 年，需 FinMind 2015 年後財報）。EPS 年變動 ÷ 股價在股數不變時等同 ES，不另做。年度資料沒有分析師預期，一年只有一個觀測，所以只能做『今年 − 去年』的季節性隨機漫步驚奇。
- 分組：每年在事件樣本內依 ES 排名，前 30%（好消息）、後 30%（壞消息）、中間；主要比較前 30% − 後 30%。另報告十分位單調性（只報告）。
- 異常報酬：還原含息報酬 − β × 加權指數含息報酬（250 日 β，dividend_events.py 的寫法）；t 值以決議日聚集（event_study.date_clustered）。視窗：[−1, +1] 公告反應（不可交易，只報告）、[+2, +20]、[+2, +40]（主要）、[+2, +60]（只報告）。
- 除息重疊：持有期上限沿用 I006——若該年度除息日早於 t0+40，在除息日往前 15 個交易日截止（避開已測的除息前布局與除息後偏弱）；報告截止比例。不配息公司沒有上限。迴歸中控制殖利率。
- 控制 SUE 與股利（關鍵）：每段做合併迴歸 CAR[+2,+40] = a + b1·ES 排名 + b2·SUE 排名 + b3·全年營收年增率排名 + b4·股利驚奇 DS 排名（I006 定義；不配息公司 DS = 0 的組內排名）+ b5·殖利率排名 + b6·log 市值 + b7·公告提前天數排名（今年決議日相對去年決議日提前的天數，控制 Chambers & Penman 的時點效果）+ 產業與年度虛擬變數；排名為年內百分位 − 0.5，標準誤依決議日分群（dividend_surprise.ols_cluster）。SUE = t0 前最新可得月營收 SUE（每月 10 日後才用當月公告值，同 dividend_surprise.latest_sue）。看 b1；另報告 ES 與 SUE、營收年增率、DS 的等級相關，以及『ES 對營收年增率迴歸的殘差』排序的前後 30% 差（只報告）。
- 可交易版本（日曆時間組合，event_study.simulate_daily 的寫法）：(i) 只做多：第 +1 日收盤等權買進前 30%，持有到第 +40 日或除息上限，剩餘 β 以台指期對沖；(ii) 多空：另放空後 30% 中可借者（可借條件 D 同 borrow_capacity.py／fv3：前 60 日有借券成交、需借股數 ≤ 借券賣出額度與 60 日成交量 × 0.1、費率 ≤ 5%），扣借券費。事件集中在 2–3 月，組合一年約 3 個月有部位，報告有持股的日子比例。
- 成本：股票單邊 0.29625%（每個事件一買一賣約 0.59%）；台指期單邊 0.005%；借券費逐日扣（缺值以 5%／年計）。
- 通過標準（全部成立才算通過）：(1) 主樣本 CAR[+2,+40] 前 30% − 後 30% 在兩段皆 > 0，全期 t > 2；(2) 主樣本控制 SUE、營收年增率、DS、殖利率、時點後，b1 兩段皆 > 0、全期 t > 3（因為已事後看過，提高門檻）；(3) 第 501–1000 名驗證樣本：前 30% − 後 30% 全期 > 0 且 t > 2，且含 SUE 控制的 b1 > 0、t > 2；(4) 只做多（台指期對沖）扣成本後，主樣本兩段 Sharpe 皆 > 0，且驗證樣本全期 Sharpe > 0。(1)–(3) 成立但 (4) 不成立記為 partial；(1)(3) 成立但控制 SUE 後 b1 不顯著，記為『年度盈餘變動只是營收驚奇的代理』＝failed。
- 與 fv3 合成（通過 (1)–(4) 後才做，決定是否採用）：在 fv3 建構（前 300 名、每 3 個預測日、三份錯開、緩衝、可借條件 D、台指期對沖、扣成本與借券費）中，於每個預測日把最近 40 個交易日內有決議事件的股票分數改為『SUE 產業內百分位與 ES 產業內百分位的平均』，其餘仍用 SUE。採用標準：合成版兩段 Sharpe 皆高於 fv3（0.93 / 1.79 為三起點平均），且 3–5 月預測日的產業內 IC 增量兩段皆 > 0；任一不成立就不改 fv3，只把 ES 當獨立的季節性部位記錄。
- 穩健性（只報告，不改判定）：(a) 2021 年後改用每日重大訊息的『董事會通過年度財務報告』日期當 t0（約 300 次請求，與 I008 共用）；(b) 次要定義 ES_g、ES_q4、ES_sd；(c) 分市場（上市／上櫃）；(d) 排除金融業；(e) 公告反應 [−1,+1] 與之後漂移的關係（反應大的是否漂移較小）。

## 與已測點子的關係

- 季報盈餘驚奇（failed，docs/revenue_surprise_plus_report.md）：命中 盈餘驚奇, earnings surprise, pead, post-earnings announcement drift
- 月營收依公告日提早進場（failed，docs/sue_event_entry_report.md）：命中 公告日, announcement timing
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 補充：與季報盈餘驚奇（failed）同族，但機制與資料不同：失敗的版本用法定期限（3/31、5/15、8/14、11/14）當可用日、以過去 8 季年差標準化；本卡改用實際董事會決議日、只用年度資料、事件研究而非每月 IC，並且直接處理已知的反方（SUE 吸收、Fu 2014 第 4 季漂移較弱）。與 I006 股利驚奇（failed）共用同一張表與事件日，差別是訊號（盈餘而非股利）與樣本（納入不配息公司）；盈餘變動係數來自 I006 的事後觀察，所以判定以第 501–1000 名驗證樣本與更高的 t 門檻為主。與除息事件以 I006 的除息前 15 日上限隔開。季報版本見 I008。

研究點子，非投資建議。
