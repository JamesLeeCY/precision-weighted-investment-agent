# I028 營收品質濾網：應收帳款與存貨成長超過營收成長的高 SUE 股漂移較弱

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 濾網或加權（SUE 條件分組＋交互項） | free（已快取） | FinMind 約 0（TaiwanStockBalanceSheet 已快取 2,159 檔，含 AccountsReceivableNet、Inventories、TotalAssets；季營收以已快取的月營收加總，不需 TaiwanStockFinancialStatements）；缺額估計 < 100 次；公開資訊觀測站 0 次 | 2026-10-18 |

## 假設

在產業內 SUE 前 30% 的非金融股中，最近一季『應收帳款＋存貨』年增率減去同季營收年增率（超額營運資金成長，EWC）位於產業內前三分之一者，之後 20 與 60 個交易日的報酬低於 EWC 後三分之一者；Fama-MacBeth 中 SUE × EWC 交互項為負。

## 機制（為什麼會有超額報酬）

營收成長若伴隨應收帳款或存貨更快累積，代表成長可能來自放寬授信、塞貨給通路，或需求轉弱、產品賣不掉，後續營收較難延續。Thomas 與 Zhang（2002）發現 Sloan 應計異常主要來自存貨變動，並推測與需求轉變和盈餘管理有關；Stubben 的裁量性營收研究用應收帳款與營收的關係衡量營收管理。月營收投資人只看到營收，看不到同時累積的應收與存貨，這正是 SUE 可能『誤判持久性』的情況。這張卡不單獨把 EWC 當因子（資產成長、季報盈餘驚奇在前 500 名都失效），而是用它分辨同一個高 SUE 的品質。

## 出處

- Thomas & Zhang（2002）Inventory Changes and Future Returns，Review of Accounting Studies 7:163–187，https://doi.org/10.1023/a:1020221918065（工作論文版 https://www3.ntu.edu.sg/home/HuaiZhang/inventory%20paper-RAST.pdf）：應計項目與未來異常報酬的負向關係主要來自存貨變動；作者推測需求轉變與盈餘管理是原因（摘要）【同儕審查】
- Stubben（2006 工作論文；2010 刊於 The Accounting Review）Do Firms Use Discretionary Revenues to Meet Earnings and Revenue Targets，https://openalex.org/W2292884418：以營收與應收帳款的關係建模裁量性營收，發現剛好達標的公司有正的裁量性營收（工作論文摘要）【工作論文／同儕審查】
- Jegadeesh & Livnat（2006）Post-Earnings-Announcement Drift: The Role of Revenue Surprises，Financial Analysts Journal，https://doi.org/10.2469/faj.v62.n2.4081：營收帶來的驚奇較持久、漂移較強（摘要）【同儕審查】
- Revenue recognition and channel stuffing in the Taiwanese semiconductor industry（2022）International Journal of Disclosure and Governance 19(3)，https://ideas.repec.org/a/pal/ijodag/v19y2022i3d10.1057_s41310-022-00144-6.html：台灣半導體業的營收認列與塞貨（只讀到標題，內容未確認）【同儕審查，未讀】
- 國際應計異常文獻（例如 Journal of International Accounting Research 2014，https://doi.org/10.2308/jiar-50700）：應計異常在大陸法系國家與普通法系國家表現不同（摘要）；台灣屬大陸法系，單獨的應計因子可能較弱【同儕審查】
- 本專案 docs/asset_growth_report.md（資產成長在前 500 名 IC ≈ 0）、docs/revenue_surprise_plus_report.md（季報盈餘驚奇合成稀釋 SUE）、forward/REPORT.md（財報 Agent 用存貨與應收週轉天數，電子股 100 檔 IC +0.029）【本專案實證】

## 台股適用性

台股電子業的存貨循環明顯，媒體常報導『庫存調整』『塞貨』，月營收公告又讓投資人特別注意營收、忽略資產負債表，機制上適用。沒有找到台股『SUE × 應收存貨品質』的實證。限制：(1) 季報資料要到法定期限後才能用（Q1 5/15、Q2 8/14、Q3 11/14、Q4 3/31），所以 EWC 與當月 SUE 最多相隔約 4 個月，是較慢的品質特徵；(2) 單獨的應計／資產成長類因子在前 500 名失效，本卡只檢定交互作用；(3) 財報 Agent（部分有效）已用過存貨與應收週轉天數，但那是無條件分數、只在電子股 100 檔，本卡是條件在 SUE 上、前 500 名全產業。

## 所需資料

- FinMind TaiwanStockBalanceSheet（已快取）：應收帳款淨額（含關係人應收帳款）、存貨、總資產
- FinMind TaiwanStockMonthRevenue（已快取）：SUE 與季營收（3 個月加總）
- FinMind TaiwanStockPrice＋除權息還原（已快取）：報酬
- analysis/asset_growth.py：季報法定期限的可用日處理方式可直接沿用
- fv5 建構程式：濾網版本比較

## 檢定計畫（看結果前固定）

- 樣本：前 500 名非金融股，2019-01 ~ 2026-04 每月營收公告後；兩段 2019–2022 / 2023–2026/04；驗證樣本第 501–1000 名；2026-05 以後不使用。
- 訊號（看結果前固定）：WC = 應收帳款淨額＋關係人應收帳款＋存貨；EWC = WC_q ÷ WC_{q−4} − 1 −（營收_q ÷ 營收_{q−4} − 1），營收_q 為該季 3 個月月營收合計；WC_{q−4} 或營收_{q−4} ≤ 0 時設缺值；每期 1%／99% 截尾。在該季法定期限的次一交易日才可使用，之後沿用到下一季可用為止。
- 主檢定 (1)：每月在產業內把 SUE 分三組；SUE 前 30% 組內再依 EWC 產業內三分組，比較 EWC 後三分之一 − 前三分之一的 20 日報酬（第 +1 日收盤進場，等權，月份群集標準誤）；SUE 後 30% 組同樣報告（預期高 EWC 更差，作為輔證）。
- 主檢定 (2)：Fama-MacBeth，r = a + b1·SUE + b2·EWC + b3·SUE×EWC + 控制（資產成長 AG、log 市值、產業固定效果）；報告 b3（預期 < 0）與 b2。
- 可交易版本 (3)：fv5 規格（前 500 名、等權多空、借券條件 D、每 3 個月換倉三份錯開、台指期對沖，成本單邊 0.29625%＋借券費）中，做多名單排除 EWC 產業內前三分之一者（依原排序遞補），放空名單不變；與 fv5（1.45 / 1.87，全期 1.64）比較；事前只測這一個規則。
- 通過標準：(1) SUE 前 30% 組的 EWC 低 − 高兩段皆 > 0、全期 t > 2；(2) b3 兩段同為負、全期 t < −2；(3) 驗證樣本 (1) 同號；(4) 濾網版扣成本後兩段 Sharpe 都不低於 fv5。只有 (1)(2) 成立才做 (4)。
- 只報告：只用存貨、只用應收帳款兩個分項；60 日版本；電子業與非電子業分開；EWC 與 SUE、AG 的平均橫斷面相關。

## 與已測點子的關係

- 財報 Agent（營收、毛利、存貨、應收）（partial，forward/REPORT.md）：命中 inventory, receivable, accrual, 存貨週轉, 應收帳款
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 金融股, SUE
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 金融股自結盈餘驚奇低換手多空（緩衝換倉）（failed，docs/fin_esue_followup_report.md）：命中 金融股
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 金融股
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 月營收驚奇 × 低法人關注：注意力低的股票漂移較強（條件分組與加權）（card:已測：未通過，research/ideas/I004-sue-x-low-attention.md）：命中 SUE interaction
- 金融股自結盈餘驚奇的低換手多空（緩衝換倉）（card:已測：未通過，research/ideas/I017-financial-esue-low-turnover-ls.md）：命中 金融股
- 月營收變動原因說明（備註）：併購、一次性認列造成的營收驚奇漂移較弱（card:待確認，research/ideas/I025-revenue-remark-transitory-sue.md）：命中 SUE interaction
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:待確認，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 補充：命中財報 Agent（部分有效：營收、毛利、存貨、應收）。差別：財報 Agent 把存貨與應收週轉天數年增率放進無條件的綜合分數、只在電子股 100 檔；本卡只檢定『同一個高 SUE 的品質差異』（交互作用），並用月營收加總的季營收算超額成長。與資產成長（失敗）的差別：AG 是總資產成長、單獨當因子；本卡控制 AG，只看營運資金相對營收的超額累積，且只當 SUE 的條件。若 (1)(2) 不成立就停止，不再單獨做應計因子。

研究點子，非投資建議。
