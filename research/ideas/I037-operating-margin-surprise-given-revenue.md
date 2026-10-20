# I037 營收已知下的利潤率驚奇：季報營業利益率相對月營收隱含水準的驚奇

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 橫斷面 IC（季頻訊號、20／60 日評估）＋與 SUE 合成 | free | FinMind TaiwanStockFinancialStatements：前 500 名約 531 次（快取 245/776）＋第 501–1000 名約 582 次（快取 29/611），合計約 1,100 次（免費每小時 600 次，約 2 小時）；選做實際公告日：公開資訊觀測站約 650–1,000 次（I008 估計） | 2026-10-21 |

## 假設

季報公布後，營業利益率年變動（控制已由月營收得知的季營收年增率後的殘差）高的股票，在法定期限次一交易日後第 +2 ~ +60 日報酬高於殘差低的股票，且在控制 SUE 後仍成立。

## 機制（為什麼會有超額報酬）

台股季營收在季報公布前就已由月營收完全揭露，季報唯一的新資訊是成本與費用面（毛利率、營業費用率）。若投資人主要盯月營收、對利潤率資訊注意不足，利潤率驚奇會像營收驚奇一樣緩慢反映。用營業利益而非稅後淨利，可去掉業外損益、匯兌與投資收益等持續性低的雜訊；先扣掉營收年增率的部分，可避免重複計入 SUE 已捕捉的資訊（營運槓桿）。

## 出處

- Ertimur、Livnat 與 Martikainen（2003）Differential Market Reactions to Revenue and Expense Surprises，Review of Accounting Studies 8，https://doi.org/10.1023/a:1024409311267：同儕審查；投資人對同金額的營收驚奇反應大於費用驚奇，差異隨成長／價值與成本結構而變（依 RePEc 摘要轉述）。
- Jegadeesh 與 Livnat（2006）Revenue Surprises and Stock Returns，Journal of Accounting and Economics，https://doi.org/10.1016/j.jacceco.2005.10.003：同儕審查；本次未讀到摘要，只作為『營收驚奇與盈餘驚奇各自有資訊』這一研究脈絡的出處。
- 陳柔君、劉晏睿、蕭朝興（2022）台灣股市的未預期月營收：綜合分析，管理學報 39(4)，https://lawdata.com.tw/tw/detail.aspx?no=484826：同儕審查（台灣）；本專案先前引用其結論：未預期月營收與季盈餘各自獨立解釋報酬。
- 本專案 docs/revenue_surprise_plus_report.md：稅後淨利 SUE_e（法定期限）產業內 IC 20 日 +0.013（t 0.6）/ +0.038（t 2.2），60 日 −0.002 / +0.051（t 2.4），與營收 SUE 排名相關 +0.29，合成後稀釋。

## 台股適用性

台灣月營收制度讓『營收已知、利潤率未知』的切分比美國乾淨，這是本卡的出發點。主要限制是時點：免費資料沒有季報實際公告日，只能用法定期限（Q1 5/15、Q2 8/14、Q3 11/14、Q4 3/31），大型股多半提早數週公告，訊號會延遲。I007 顯示年度盈餘在 2023 年後沒有可交易漂移，這是本卡最大的失敗風險；但 I007／先前 SUE_e 用的是淨利且未扣除營收部分，本卡的利潤率殘差資訊與 SUE 重疊較少。若主檢定接近門檻，可再用 I008 的公開資訊觀測站實際公告日做穩健性（另計請求數）。

## 所需資料

- FinMind TaiwanStockFinancialStatements：Revenue、GrossProfit、OperatingIncome（2017Q1 起；已確認欄位存在）
- FinMind TaiwanStockMonthRevenue：季營收年增率（月營收加總）與 SUE
- 已快取的價格、借券資料

## 檢定計畫（看結果前固定）

- 樣本：2019-01 ~ 2026-04 前 500 名非金融股（金融業無營業毛利結構）；驗證第 501–1000 名。
- 訊號：ΔOPM = 本季營業利益率 − 去年同季營業利益率；MS = ΔOPM 對同產業同季『季營收年增率』截面迴歸的殘差，再除以該公司過去 8 季 ΔOPM 標準差（至少 4 季）。次要：毛利率版本 MS_gm。營業利益率分母為營收，營收 ≤ 0 或 |ΔOPM| > 50 個百分點者剔除。
- 時點：法定期限次一交易日為 +0，+1 收盤進場；只用期限已過的最新一季。
- 評估：產業內 Spearman IC（MS 對第 +2 ~ +21 日與 +2 ~ +61 日報酬），每季一個截面，用 Newey-West；Fama-MacBeth 控制最新 SUE、季營收年增率、前 20 日報酬、市值、帳面市值比。
- 成本與可交易：若 IC 通過，(a) 與 fv5 合成：fv5 分數改為 SUE 與 MS 產業內百分位 0.75 / 0.25 加權（權重事前固定）；(b) 扣單邊 0.29625% 與借券費、台指期對沖，與 fv5 1.45 / 1.87（全期 1.64）比較。
- 通過標準（事前固定）：60 日 IC 兩段皆 > 0、全期 t > 2，且 Fama-MacBeth 控制 SUE 後 MS 係數全期 t > 2；驗證樣本同號；合成版兩段 Sharpe 都不低於 fv5。任一不成立即停止。
- 只報告：MS_gm 版本、20 日 IC、電子與非電子分組。

## 與已測點子的關係

- 財報 Agent（營收、毛利、存貨、應收）（partial，forward/REPORT.md）：命中 gross margin, 毛利率
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE, earnings surprise
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue
- 年度盈餘驚奇改用實際董事會決議日（failed，docs/earnings_board_date_report.md）：命中 earnings surprise
- 季報盈餘驚奇（failed，docs/revenue_surprise_plus_report.md）：命中 earnings surprise
- 年度盈餘驚奇改用實際董事會決議日：年報公告後的盈餘漂移（PEAD）（card:已測：未通過，research/ideas/I007-annual-earnings-surprise-actual-board-da.md）：命中 法定期限
- 季報盈餘驚奇改用實際公告日：公開資訊觀測站重大訊息的財報董事會日期（card:暫緩（I007 顯示 2023 後無可交易漂移），research/ideas/I008-quarterly-pead-actual-announcement-date.md）：命中 法定期限
- 每月自結損益驚奇：金控、銀行與少數公司按月公告的自結稅後盈餘（card:已測：通過（可交易性弱），research/ideas/I015-monthly-self-reported-earnings-surprise.md）：命中 earnings surprise
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 補充：與已失敗的季報盈餘驚奇（稅後淨利 SUE_e）差別：(1) 用營業利益率而非淨利，去除業外；(2) 先扣掉月營收已揭露的營收年增率，只留利潤率資訊；(3) 主檢定看 60 日（先前 60 日 IC 2023 年後 t 2.4）。與財報 Agent（毛利率等，partial）差別：財報 Agent 是電子股 100 檔的綜合分數，本卡是單一、事前定義的驚奇。I008（實際公告日）暫緩，本卡不依賴它。

研究點子，非投資建議。
