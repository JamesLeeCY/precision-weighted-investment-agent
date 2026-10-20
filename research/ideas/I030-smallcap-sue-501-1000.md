# I030 小型股版月營收驚奇：第 501–1000 名獨立多空，以及前 1000 名廣度版本

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | A | 橫斷面 IC＋可交易建構（fv5 建構換股票池） | free | 第一階段 0（第 501–1000 名 611 檔的價格與月營收已全部快取，已逐檔確認 611/611）；第二階段約 1,222（611 檔 × TaiwanDailyShortSaleBalances、TaiwanStockSecuritiesLending 各 1 次，目前快取 0/611；免費每小時 600 次，約 2 小時） | 2026-10-20 |

## 假設

以和 fv5 相同的 SUE 定義與建構，第 501–1000 名的產業內 20 日 IC 不低於前 500 名，且扣成本（含額外衝擊成本）與可借限制後的等權多空，兩段 Sharpe 都 > 0.5；把股票池擴大到前 1000 名的版本，兩段 Sharpe 都不低於 fv5（1.45 / 1.87）。

## 機制（為什麼會有超額報酬）

反應不足與套利限制：小型股的投資人關注、法人持有與套利資金都較少，盈餘／營收消息的價格調整較慢，所以漂移較大；但同樣的原因（流動性差、借券少）也讓成本較高。本專案已看到兩個相關現象：(1) 股票池從前 300 擴到前 500 時 SUE 多空 Sharpe 由 0.93 / 1.79 升到 1.45 / 1.87（廣度與較小型股的貢獻）；(2) 市值加權會稀釋 SUE 的選股能力，alpha 集中在權重小的股票（hedge_construction_report）。本卡把『只在小型股有效』的教訓轉成直接問題：小型股的 SUE 扣成本後是否仍可交易。

## 出處

- Chordia, Goyal, Sadka, Sadka & Shivakumar（2009）Liquidity and the Post-Earnings-Announcement Drift，Financial Analysts Journal 65(4):18–32，https://ideas.repec.org/a/taf/ufajxx/v65y2009i4p18-32.html：盈餘漂移主要出現在流動性最差的股票；最流動組多空月報酬 0.04%、最不流動組 2.43%（市值加權）；交易成本約吃掉帳面利潤的 70–100%（摘要）【同儕審查】
- Fama & French（2008）Dissecting Anomalies，Journal of Finance 63(4):1653–1678，https://ideas.repec.org/a/bla/jfinan/v63y2008i4p1653-1678.html：淨發行、應計、動能在微型、小型、大型股都存在；資產成長只在微型與小型股出現，大型股沒有（摘要）【同儕審查】
- Jegadeesh & Livnat（2006）Revenue surprises and stock returns，Journal of Accounting and Economics，https://doi.org/10.1016/j.jacceco.2005.10.003：營收驚奇本身可預測之後報酬（本次只讀到題目與出處）【同儕審查，未讀摘要】
- Novy-Marx & Velikov（2016）A Taxonomy of Anomalies and Their Trading Costs，Review of Financial Studies，https://doi.org/10.1093/rfs/hhv063：買進與續抱門檻不同的緩衝是最有效的降成本方法；單邊月換手 < 50% 的異常多數扣成本後仍顯著（摘要）【同儕審查】
- 本專案 docs/top500_report.md、docs/hedge_construction_report.md、docs/asset_growth_report.md、docs/revenue_quality_report.md：前 300 → 前 500 SUE 變強；經典因子只在第 501–1000 名有效【本專案實證】

## 台股適用性

台股月營收是全市場強制揭露，小型股同樣每月公告，訊號定義不需改。沒有找到台股按市值分組的月營收驚奇實證。制度限制：(1) 第 501–1000 名的 20 日平均成交金額中位數約新台幣 4–37 百萬元／日（依年份與名次，前 300 名為 134–613 百萬元），衝擊成本明顯較高；(2) 借券供給少、費率高，空方可借比例預期遠低於前 500 名的約 68%；(3) 漲跌停較常見。所以本卡把『訊號強度』與『可交易性』分兩階段，第一階段請求數為 0。

## 所需資料

- FinMind TaiwanStockMonthRevenue（已快取）：SUE
- FinMind TaiwanStockPrice、TaiwanStockDividendResult、TaiwanStockSplitPrice（已快取）：含息報酬、成交金額
- FinMind TaiwanDailyShortSaleBalances、TaiwanStockSecuritiesLending（第 501–1000 名需補抓）：可借條件 D 與借券費
- config/universe_mcap_membership.csv：每年前 1000 名成員（無存活偏誤）

## 檢定計畫（看結果前固定）

- 樣本：每年市值第 501–1000 名（主問題）與前 1000 名（廣度版本），2019-01 ~ 2026-04；兩段 2019–2022 / 2023–2026/04；2026-05 以後不使用。
- 訊號：完全沿用 fv5 的 SUE 定義、公告期限次一交易日進場、產業內排序；不調任何參數。
- 階段一（0 次請求）(1)：產業內 Spearman IC（20 日、60 日；60 日用 Newey-West），依名次分四組報告：1–300、301–500、501–750、751–1000；另報不扣成本的產業內前／後 30% 等權多空報酬差。
- 階段一通過標準：第 501–1000 名 20 日 IC 兩段 > 0、全期 t > 2，且全期 IC 不低於前 500 名的 IC 減 0.005。不成立就停止，不抓借券資料。
- 階段二 (2) 小型股獨立多空：fv5 建構（產業內前／後 30%、每 3 個月換倉三份錯開、只放空可借條件 D 的股票、台指期對沖剩餘 β），資金 1 億與 2 億兩種；成本 = 單邊 0.29625%＋借券費，另對 20 日平均成交金額 < 新台幣 20 百萬元的股票每邊加 0.15% 衝擊成本；單檔每次交易量上限為其 20 日平均成交金額的 10%（超過部分不成交）。
- 階段二 (3) 前 1000 名廣度版本：同 fv5 建構、同成本規則，與 fv5（1.45 / 1.87，全期 1.64）比較。
- 通過標準：(2) 1 億資金兩段 Sharpe 都 > 0.5，且與 fv5 每日報酬相關 < 0.6 才考慮另立 fv5s；(3) 兩段 Sharpe 都不低於 fv5 才考慮擴大 fv5 股票池。兩者只要一個通過，就另立前瞻規格，不改 fv5。
- 只報告：空方可借比例、平均借券費、因成交量上限未成交的比例、只做多小型股 − β × 台指期的結構差、與 fv5 各半合成的 Sharpe。

## 與已測點子的關係

- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 月營收驚奇, sue, 營收驚奇
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5, SUE, 月營收驚奇
- Amihud 非流動性、異常成交量（failed，docs/leg_pool_report.md）：命中 illiquidity, 流動性
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 月營收驚奇, sue
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 年度盈餘驚奇改用實際董事會決議日（failed，docs/earnings_board_date_report.md）：命中 pead
- 季報盈餘驚奇（failed，docs/revenue_surprise_plus_report.md）：命中 pead
- 年度盈餘驚奇改用實際董事會決議日：年報公告後的盈餘漂移（PEAD）（card:已測：未通過，research/ideas/I007-annual-earnings-surprise-actual-board-da.md）：命中 pead
- 季報盈餘驚奇改用實際公告日：公開資訊觀測站重大訊息的財報董事會日期（card:暫緩（I007 顯示 2023 後無可交易漂移），research/ideas/I008-quarterly-pead-actual-announcement-date.md）：命中 pead
- 補充：與已測點子的差別：之前的驗證樣本只用來確認『其他訊號』在小型股的方向，從未直接檢查 SUE 本身在第 501–1000 名的強度與可交易性。I004（低法人關注）是在前 500 名內做條件分組，不是換股票池。這次可能不同的理由：本專案所有經典因子都呈現『小型股有效』，SUE 又已知在前 300 → 前 500 時變強；小型股的主要風險是成本與借券，這正是階段二要量化的。

研究點子，非投資建議。
