# I020 資產成長（投資）異常：總資產年增率高的股票之後報酬較低

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過 | B | 橫斷面 IC（季頻訊號、月頻評估）＋等權多空＋與 SUE 合成 | free（已快取） | 約 0（FinMind TaiwanStockBalanceSheet 已快取 2,154 檔、2017Q1 起，涵蓋前 1000 名大部分；缺額估計 < 100 次） | 2026-10-17 |

## 假設

合併總資產年增率（本季 ÷ 去年同季 − 1）位於產業內前 30% 的非金融股，在財報法定期限後 20 與 60 個交易日的報酬低於後 30% 者；與 SUE 合成時能改善 fv5 式多空。

## 機制（為什麼會有超額報酬）

兩種解釋都指向同一方向：(1) 投資理論（q-theory）：公司在資金成本低（預期報酬低）時擴張，因此高投資對應低預期報酬；(2) 過度外推：投資人把擴張解讀為成長而給高價，之後失望。Watanabe 等（2013）在國際市場發現資產成長與未來報酬負相關，且在較發達、價格較有效率的市場更強，作者傾向最適投資的解釋。對本專案的價值：這是慢變數、低換手，與 SUE（短期營收驚奇）資訊來源不同，可能提供空方或合成的分散。

## 出處

- Watanabe, Xu, Yao & Yu（2013）The asset growth effect: Insights from international equity markets，Journal of Financial Economics 108(2):529–563，https://doi.org/10.1016/j.jfineco.2012.12.002：資產成長與未來報酬的負相關在美國以外普遍存在；在資本市場較發達、價格較有效率的國家較強；套利限制、投資人保護與會計品質無法解釋（摘要）【同儕審查】
- 本專案 docs/taiwan_alpha_literature.md 第 7 列：品質、獲利能力、資產成長、應計在台灣證據溫和、多為碩論；台大碩論（只讀搜尋摘要）https://tdr.lib.ntu.edu.tw/handle/123456789/43350【學位論文，未讀全文】
- AQR, Investing in the Asset Growth Anomaly Across the Globe，https://aqr.com/library/journal-articles/investing-in-the-asset-growth-anomaly-across-the-globe（只看到標題，未讀內容，不引用數字）【業界文章，未讀】

## 台股適用性

國際研究的樣本涵蓋多國市場，但沒有找到台灣單獨、近年的同儕審查結果；本專案的經驗是經典價量與估值因子在台股前 300／500 大多數失效（動能、低波動、估值），所以本卡的先驗不高，但因資料成本為 0、換手低，值得用一次固定規則確認。制度細節：季報法定期限 Q1 5/15、Q2 8/14、Q3 11/14、Q4 3/31（實際多在期限前公告，但 FinMind 沒有公告日，所以一律用期限後次一交易日，屬保守）。金融業總資產成長的意義不同（放款與存款擴張），主樣本排除金融保險業。

## 所需資料

- FinMind TaiwanStockBalanceSheet（已快取）：TotalAssets（合併）
- FinMind TaiwanStockPrice＋除權息還原、TaiwanStockMonthRevenue（已快取）：報酬、SUE 控制
- config/universe_mcap_membership.csv：主樣本前 500 名、驗證第 501–1000 名

## 檢定計畫（看結果前固定）

- 樣本：前 500 名非金融成員；訊號從 2018Q1 財報起可算（需要去年同季），評估期間 2019-01 ~ 2026-04；分兩段 2019–2022 / 2023–2026/04；驗證樣本第 501–1000 名；2026-05 以後不使用。
- 訊號：AG = TotalAssets_q ÷ TotalAssets_q−4 − 1（合併報表）；在該季法定期限的次一個交易日才可使用，之後保持到下一季期限；極端值以每期 1%／99% 分位截尾；產業內排名。合併、減資或分割造成的跳動不另外處理（事前固定，避免看結果後挑選）。
- 主檢定：每月月底的產業內 Spearman IC（−AG 對之後 20 日、60 日報酬），兩段平均與 Newey-West t（60 日用落後 3 期）。
- 增量：Fama-MacBeth 迴歸 r = a + b·AG + c·SUE + d·log 市值 + 產業固定效果；報告 AG 與 SUE 的平均橫斷面相關。
- 可交易版本：(a) 單獨：產業內 AG 後 30% 做多、前 30% 放空，等權、借券條件 D、每 3 個月換倉三份錯開、台指期對沖，成本單邊 0.29625%＋借券費；(b) 合成：fv5 排序分數改為 SUE 排名 2/3 ＋ (−AG) 排名 1/3（事前固定，只測這一組），與 fv5 原版比較。
- 通過標準：(1) 20 日或 60 日 IC 兩段皆 > 0（以 −AG 計）、全期 t > 2；(2) 控制 SUE 與市值後 b 全期 t > 2 且兩段同號；(3) 驗證樣本方向相同；(4) 單獨多空扣成本後兩段 Sharpe > 0，或合成版兩段 Sharpe 都不低於 fv5 原版。

## 與已測點子的關係

- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 金融股, fv5, SUE
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5, 金融股
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 財報 Agent（營收、毛利、存貨、應收）（partial，forward/REPORT.md）：命中 財報
- 金融股自結盈餘驚奇低換手多空（緩衝換倉）（failed，docs/fin_esue_followup_report.md）：命中 金融股
- 年度盈餘驚奇改用實際董事會決議日：年報公告後的盈餘漂移（PEAD）（card:已測：未通過，research/ideas/I007-annual-earnings-surprise-actual-board-da.md）：命中 法定期限
- 季報盈餘驚奇改用實際公告日：公開資訊觀測站重大訊息的財報董事會日期（card:暫緩（I007 顯示 2023 後無可交易漂移），research/ideas/I008-quarterly-pead-actual-announcement-date.md）：命中 法定期限
- 金融股自結盈餘驚奇的低換手多空（緩衝換倉）（card:已測：未通過，research/ideas/I017-financial-esue-low-turnover-ls.md）：命中 金融股
- 補充：與產業內相對估值（失敗）的差別：估值是價格對基本面的比；資產成長是公司實際的擴張速度，不含價格。與財報 Agent（部分有效：營收、毛利、存貨、應收）的差別：財報 Agent 沒有用資產規模成長。與年增率加速（部分有效）可能正相關（擴張的公司營收也成長），所以檢定中控制 SUE。若通過，最可能的用法是合成的空方資訊，而不是單獨策略。


## 結果（2026-10-17）

未通過：主樣本 IC 20 日 +0.011 / −0.008、60 日 +0.019 / −0.004；控制後 t −0.5；驗證樣本（第 501–1000 名）IC 顯著（60 日 +0.046，t 4.0），但單獨多空 −0.72 / −1.15，合成使 fv5 從 1.64 降到 1.50。見 [docs/asset_growth_report.md](../../docs/asset_growth_report.md)。

研究點子，非投資建議。
