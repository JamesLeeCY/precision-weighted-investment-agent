# I023 董監事持股設質（質押）比率：高設質股的崩跌風險與報酬，作為做多名單的排除濾網

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | C | 濾網（fv5 做多名單排除）＋下跌月份條件報酬 | free（公開資訊觀測站逐家查詢，已實測）；manual（請求量大） | 公開資訊觀測站：前 500 名不重複約 776 檔 × 每季末月 30 期（2018-12 ~ 2026-03）≈ 23,000 次（每次間隔 3 秒約 19 小時，每頁 30–45 KB）；縮小版：前 300 名 × 每年 6 月 8 期 ≈ 2,400 次（約 2 小時）；FinMind 約 0 | 2026-10-17 |

## 假設

董監事設質比率（設質股數 ÷ 董監持股）位於前 20% 或 ≥ 50% 的股票，在加權指數下跌超過 5% 的月份報酬顯著低於設質比率 0 的同產業股票；把這些股票從 fv5 做多名單排除後，兩段 Sharpe 不降、最大回撤變小。

## 機制（為什麼會有超額報酬）

追繳保證金的連鎖賣壓：內部人以持股質押借款，股價下跌觸發追繳時，若內部人無法補足現金，銀行或內部人賣出質押股，放大跌幅（崩跌風險）。另一管道是內部人為避免追繳而變得保守，損害股東價值。台灣自 1998 年起要求揭露設質，2011 年公司法修正規定設質超過持股一半的部分不計入表決權，是文獻常用的制度衝擊。

## 出處

- Dou, Masulis & Zein（2016 工作論文）Shareholder wealth consequence of insider pledging of company stock as collateral for personal loans，ABFER 2016，https://www.abfer.org/media/abfer-events-2016/annual-conference/corporate-finance/171-shareholder-wealth-consequence-of-insider-pledging-of-company-stock-as-collateral-for-personal-loans.pdf：利用台灣的設質揭露規定與法規變動；經理人大幅降低設質時股東財富改善；價格下跌觸發的追繳會加劇設質公司的崩跌風險（摘要，本次讀第 1–3 頁）【工作論文】
- Wang & Chou（2018）The Impact of Share Pledging Regulations on Stock Trading and Firm Valuation，Journal of Banking & Finance 89:1–13，https://commerce.nccu.edu.tw/en/faculty/facultylist/writing_journal/Wang-Yu-Chun-Robin-K-Chou-2018-04-The-Impact-of-Share-Pledging-Regulations-on-Stock-Trading-and-Firm-Valuation-Journal-of-Banking-and-Finance-Vol-89-pp-1-13-SSCI-4088152：台灣三次設質法規變動前後，董事有設質的公司股價反應顯著較高；2011 公司法修正後法人增持設質公司（依搜尋結果的摘要轉述）【同儕審查】
- Wang & Chen（2020）The Causes and Consequences of Stock Pledging by Controlling Shareholders: The Case of Taiwan，Advances in Pacific Basin Business, Economics and Finance，https://www.emeraldinsight.com/insight/content/doi/10.1108/S2514-465020200000008005：控制股東設質對會計與財務績效有負面影響（依搜尋結果的摘要轉述）【專書章節】
- 本專案 docs/taiwan_alpha_literature.md：董監質押在台灣只有崩跌風險研究，列為不建議優先【本專案文獻整理】

## 台股適用性

有台灣制度與實證（設質揭露、2011 修法），但證據集中在崩跌風險與法規事件，不是平均報酬，所以本卡設計成『下跌月份的條件報酬＋做多名單濾網』而不是多空。金管會每月新聞稿顯示，上市公司設質比率 ≥ 50% 的約 42 家、0% 的約 716 家（115 年 4 月），大型股中高設質的家數可能不多。資料是本卡最大的成本：公開資訊觀測站只有逐家逐月的查詢（本次實測 ajax_stapap1 可查到 108 年資料，不帶公司代號會要求輸入代號），沒有找到整批彙總端點。

## 所需資料

- 公開資訊觀測站 POST mopsov.twse.com.tw/mops/web/ajax_stapap1（co_id、TYPEK=all、year=民國年、month）：董監事、經理人、大股東的目前持股與設質股數（本次實測 2330 民國 113 年 6 月、1101 民國 108 年 6 月）
- （待查）金管會每月新聞稿『董事監察人持股異動及設解質情形』PDF：只列設質 ≥ 50% 與前 10 名的公司，可作為低成本替代或核對；歷史檔案是否可下載未確認
- FinMind TaiwanStockPrice＋除權息還原（已快取）

## 檢定計畫（看結果前固定）

- 樣本：前 500 名成員（若只做縮小版則前 300 名），2019-01 ~ 2026-04，兩段 2019–2022 / 2023–2026/04；2026-05 以後不使用。
- 訊號：PR = 董事（含法人董事本人，不含法人代表人、經理人與大股東）設質股數合計 ÷ 持股合計；資料月 m 的申報在 m+1 月 15 日後才使用；高設質 = PR ≥ 50% 或產業內前 20%（兩個定義都報告，事前以 PR ≥ 50% 為主）。
- 主檢定（崩跌）：每月把高設質股與同產業 PR = 0 的股票比較下一個月報酬；在加權指數月報酬 ≤ −5% 的月份與其他月份分開報告差異與 t 值；另報告兩組的報酬偏態。
- 濾網檢定：fv5 規格（前 500 名、等權多空、借券條件 D、每 3 個月換倉三份錯開、台指期對沖、成本單邊 0.29625%＋借券費）中，做多名單排除高設質股（以下一名遞補），與 fv5 原版比較 Sharpe 與最大回撤。
- 通過標準：(1) 大跌月份高設質 − 零設質的報酬差兩段皆 < 0、全期 t < −2；(2) 濾網版兩段 Sharpe 都不低於 fv5 原版，且全期最大回撤較小。大跌月份估計不到 15 個，(1) 只能作為方向性證據；先用縮小版確認高設質股在前 300 名中至少有 30 檔，否則停止。

## 與已測點子的關係

- 董監事／內部人持股轉讓事前申報（failed，docs/corp_events_report.md）：命中 董監, insider
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 董監事／內部人持股轉讓事前申報：一般交易賣出申報後的股價落後（card:已測：未通過，research/ideas/I011-insider-transfer-predeclaration.md）：命中 董監事
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5
- 補充：與董監事持股轉讓事前申報 I011（失敗）的差別：I011 是內部人賣出的資訊；本卡是內部人以持股借款造成的被迫賣壓與崩跌風險，用途是做多名單的風險濾網。與集保股權分散（失敗）的差別：股權分散看持股結構，本卡看董監持股的抵押狀態。列為 C 的原因：資料要逐家逐月抓、證據是崩跌風險而非平均報酬、大型股中高設質股可能太少。

研究點子，非投資建議。
