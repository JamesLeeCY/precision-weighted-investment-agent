# I048 利潤率驚奇改用季報實際公告日：前 500 名的期限前漂移（I037 的事後追加，以從未看過的視窗與第 1001–1500 名確認）

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | A | 橫斷面 IC（季頻事件、對齊實際公告日）＋同事件期限對照；通過後另立前瞻規格 | free（FinMind）＋manual（公開資訊觀測站重大訊息爬取） | FinMind 約 50（前 500 名 TaiwanStockFinancialStatements 缺 35 檔、第 1001–1500 名缺 6 檔；價格、資產負債表、月營收全部已快取）；公開資訊觀測站約 600–1,000 次（2020-07 ~ 2026-05 每季公告期間的每日重大訊息 ajax_t05st02，或全文檢索 ajax_t51sb10 以『財務報告』分頁；每次間隔 3 秒，約 35–50 分鐘，不占 FinMind 額度） | 2026-10-22 |

## 假設

在市值前 500 名非金融股中，以公開資訊觀測站重大訊息的財報董事會日為事件日，營收已知下的利潤率驚奇 MS 的產業內排名，與『實際公告後第 +2 日 ~ 法定期限次一交易日』這段過去沒用過的視窗報酬正相關（兩段皆 > 0、全期 t > 2）；同一批事件改從實際日起算的 60 日 IC 全期 t > 2.5。

## 機制（為什麼會有超額報酬）

盈餘公告後反應不足（PEAD）集中在公告後幾週；大型股季報多半在法定期限前 2–4 週公告，I037 用法定期限進場時，最有資訊的前段漂移已經走完，留下的只有尾段（前 500 名 IC +0.030、t 1.9）。季報旺季單日上百家同時公告，符合有限注意力造成的延遲反應。月營收已先揭露營收，所以季報真正的新資訊是利潤率，與 SUE 幾乎無關（等級相關 −0.01）。

## 出處

- （本專案）docs/margin_surprise_report.md：I037 在法定期限進場，前 500 名 60 日 IC +0.030（t 1.9），第 501–1000 名 +0.061（t 5.6）；報告指出可用 I008 的實際公告日重測，但屬於事後追加
- （本專案）docs/smallcap_composite_report.md：第 1001–1500 名 MS 單獨 60 日 IC +0.023（t 3.0，法定期限）——三個名次組都已看過期限版本，所以本卡的乾淨檢定必須放在實際日到期限之間的新視窗
- （同儕審查）Bernard 與 Thomas（1989）Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?，Journal of Accounting Research，https://doi.org/10.2307/2491062：盈餘公告後的延遲反應（只核對書目）
- （同儕審查）Hirshleifer、Lim 與 Teoh（2009）Driven to Distraction，Journal of Finance，https://doi.org/10.1111/j.1540-6261.2009.01501.x：同日公告家數越多，當下反應越弱、漂移越強（依 I008 卡的摘要轉述）
- （制度，新聞）經濟日報（2026）證交所設專區整合財報董事會預計召開日期，https://money.udn.com/money/story/5607/9786572：2026 年第 3 季財報起集中揭示，前瞻可直接取得公告日

## 台股適用性

台股季報公告日分散在法定期限（Q1 5/15、Q2 8/14、Q3 11/14、Q4 3/31）前數週，大型股尤其提早；I008 已驗證公開資訊觀測站每日重大訊息可辨識『董事會通過第 X 季財務報告』，但 2020 年上半年以前多數公司不發，樣本只能從 2020Q3 財報開始（第一段比其他卡短）。資料窺探：MS 的期限版本在前 500、第 501–1000、第 1001–1500 名都已看過結果，所以 (1) 主檢定改用『實際日到期限』這段從未計算過的視窗；(2) 門檻提高到 t > 2.5；(3) 最終採用只看 2026Q3 起的前瞻紀錄（證交所集中揭示專區）。另外，I037 的 MS 用同產業同季營收年增率迴歸去除營收部分，若在實際日使用會用到尚未公告的同業資料，必須改用前 8 季的產業斜率。

## 所需資料

- 公開資訊觀測站 ajax_t05st02（每日重大訊息）或 ajax_t51sb10（全文檢索）：財報董事會實際日期與發言時間
- FinMind TaiwanStockFinancialStatements（大多已快取）：單季營業收入、營業利益（沿用 analysis/margin_surprise.py 的 MS）
- FinMind TaiwanStockMonthRevenue、TaiwanStockPrice、還原資料、TaiwanStockBalanceSheet（已快取）：SUE、報酬、市值、帳面市值比控制
- 股利分派彙總表（已快取）：季配公司的季度決議日，用來核對重大訊息日期
- 既有程式：analysis/margin_surprise.py（MS）、analysis/earnings_board_date.py（實際日事件的寫法）、analysis/event_study.py、analysis/ts_rank_validate.py（fv5 合成的寫法）

## 檢定計畫（看結果前固定）

- 前置（看任何報酬前）：抓 2020-07 ~ 2026-05 公告期間的重大訊息，主旨含『財務報告』且不含『預計』『更正』『補正』者，每家每季取最早一筆；計算前 500 名逐季覆蓋率（有日期者 ÷ 有財報者），< 80% 的季度整季剔除並列出；抽 30 筆與季配公司股利表日期核對；報告實際日早於法定期限的交易日數分布。沒有日期的公司不以期限補值。
- 樣本：主樣本＝公告當年市值前 500 名非金融股；確認＝第 1001–1500 名（config/universe_mcap_membership_1500.csv）；第 501–1000 名只報告。2020Q3 ~ 2026Q1 財報（事件日 ≤ 2026-04-30），兩段 2020Q3–2022 / 2023–2026/04；2026-05 以後不用。
- 訊號（看結果前改定義並寫死）：MS* = 單季營業利益率年變動，扣掉『產業 × 季營收年增率』的預期部分，斜率改用前 8 季（全部已公告）的同產業合併迴歸估計，再除以公司前 8 季該差值的標準差；期限版與實際日版都用 MS*，讓比較只差時點。產業內百分位，1%／99% 截尾。
- 事件日：t0 = 重大訊息發言日；發言時間 ≥ 13:30 或非交易日，t0 移到下一個交易日；一律第 +1 日收盤進場（保守）。d = 法定期限次一交易日。
- 主檢定 P1（新視窗）：每季截面，MS* 與報酬 [t0+2, d+1] 的產業內 Spearman IC，只用 d − t0 ≥ 5 個交易日的事件；Newey-West 落後 2。
- P2：實際日版 60 日 IC（[t0+2, t0+61]）；只報告：期限版 60 日 IC 與兩者差。
- 控制：每季 Fama-MacBeth，[t0+2, t0+61] 報酬 = MS* + t0 前最新 SUE + 季營收年增率 + 前 20 日報酬 + log 市值 + 帳面市值比 + 產業虛擬變數（百分位 − 0.5）。
- 通過標準（全部成立）：(1) 前 500 名 P1 兩段皆 > 0、全期 t > 2；(2) 前 500 名 P2 兩段皆 > 0、全期 t > 2.5（因期限版已看過而提高）；(3) Fama-MacBeth MS* 係數全期 t > 2；(4) 第 1001–1500 名 P1 同號且 t > 1.65。
- 可交易版本（(1)–(4) 成立才做）：fv5 建構（三份錯開、條件 D 借券、台指期對沖、單邊 0.29625% + 借券費），分數 = 0.75 × SUE 百分位 + 0.25 × MS* 百分位（只對 t0+1 ≤ 預測日且 60 個交易日內有事件者，其餘 MS* 以 0.5 代入），權重比照 fv5s 事前固定、不調參；報告與 fv5 的 Sharpe 差。無論回測結果如何，只能另立平行前瞻規格（暫名 fv5m，日期來源用證交所集中揭示專區），不直接改 fv5。
- 未通過即停止，不改用毛利率版、不換視窗長度重測。

## 與已測點子的關係

- 營收已知下的利潤率驚奇：季報營業利益率相對月營收隱含水準的驚奇（card:待確認，research/ideas/I037-operating-margin-surprise-given-revenue.md）：命中 利潤率驚奇, 營業利益率, 季報, 營收已知, margin surprise, operating margin
- 季報盈餘驚奇改用實際公告日：公開資訊觀測站重大訊息的財報董事會日期（card:暫緩（I007 顯示 2023 後無可交易漂移），research/ideas/I008-quarterly-pead-actual-announcement-date.md）：命中 季報實際公告日, 財報董事會, 重大訊息, 法定期限, actual announcement date
- 年度盈餘驚奇改用實際董事會決議日：年報公告後的盈餘漂移（PEAD）（card:已測：未通過，research/ideas/I007-annual-earnings-surprise-actual-board-da.md）：命中 實際公告日, 法定期限, actual announcement date
- 非金融按月自結公司的盈餘驚奇：同月 ESUE 相對 SUE 的增量（card:待確認，research/ideas/I038-nonfinancial-esue-increment.md）：命中 非金融, 利潤率驚奇, margin surprise
- 年度盈餘驚奇改用實際董事會決議日（failed，docs/earnings_board_date_report.md）：命中 實際公告日, actual announcement date
- 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）（card:待確認，research/ideas/I043-smallcap-multifactor-composite.md）：命中 利潤率驚奇, margin surprise
- 財報 Agent（營收、毛利、存貨、應收）（partial，forward/REPORT.md）：命中 財報
- 金融股自結盈餘驚奇低換手多空（緩衝換倉）（failed，docs/fin_esue_followup_report.md）：命中 金融股
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 金融股
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- 融資餘額比、外資持股比例的 ts_rank（failed，docs/ts_rank_report.md）：命中 margin
- 月營收依公告日提早進場（failed，docs/sue_event_entry_report.md）：命中 公告日
- 金融股自結盈餘驚奇的低換手多空（緩衝換倉）（card:已測：未通過，research/ideas/I017-financial-esue-low-turnover-ls.md）：命中 金融股
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 金融股
- 補充：直接延伸 I037（期限版，前 500 名 t 1.9 未通過）與 I008（暫緩）。與 I008 的差別：I008 用季盈餘驚奇 SUE_e（與營收 SUE 相關 +0.29，已失敗），本卡用與 SUE 無關的 MS；與 I007（年度、已失敗）共用資料抓取方式。資料窺探的處理：主檢定只用過去沒有計算過的『實際日到期限』視窗、門檻提高、確認樣本與前瞻把關。

研究點子，非投資建議。
