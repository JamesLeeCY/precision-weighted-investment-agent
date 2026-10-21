# I040 相對自身歷史的時間序列排名（ts_rank）：借券賣出餘額比、融資餘額比、外資持股比例

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：S1 通過（S2、S3 未通過） | A | 橫斷面 IC（產業內 20／60 日）＋ Fama-MacBeth 增量＋與 fv5 合成 | free | 前 500 名約 0（三個資料集皆已快取 776/776，已逐檔確認）；第 501–1000 名驗證約 1,780 次（Shareholding 582＋MarginPurchaseShortSale 582＋DailyShortSaleBalances 611，已用 2477 試抓確認免費可用；免費每小時 600 次，約 3 小時） | 2026-10-21 |

## 假設

在市值前 500 名中，(1) 借券賣出餘額比、(2) 融資餘額比在自身過去 250 個交易日的百分位排名越高，之後 60 個交易日的產業內報酬越差；(3) 外資持股比例在自身過去 250 日的排名越高，之後 60 日產業內報酬越好；且三者在控制 SUE 與同欄位的絕對水準、20 日變化後仍成立。

## 機制（為什麼會有超額報酬）

絕對水準混合了各股長期、與資訊無關的結構差異（例如可轉債套利與 ETF 避險讓某些股票的借券餘額長期偏高、外資偏好大型權值股、融資戶偏好特定族群），所以水準排序其實是在比『哪些股票通常如此』。ts_rank 把每檔股票和自己的過去一年比，只留下『這檔股票現在異常地如何』，類似 52 週高點（George 與 Hwang 2004）與本專案有效的營收創新高（rec24）的作法。各欄位的預期方向：(1) 借券賣出處於自身一年高點，代表知情放空增加到超過該股的正常避險量，預期之後報酬差（放空者的資訊優勢）；(2) 融資餘額處於自身一年高點，代表散戶槓桿買盤集中，依 Miller 意見分歧與 Ting、Lu、Chou（2018）的台股證據，會把價格推高、之後報酬較低；(3) 外資持股處於自身一年高點，代表外資在一年尺度上持續加碼，外資流量有持續性且在台股短期與報酬正相關（Chuang 2015），預期之後 1–3 個月報酬較高。

## 出處

- George 與 Hwang（2004）The 52-Week High and Momentum Investing，Journal of Finance 59(5)，https://doi.org/10.1111/j.1540-6261.2004.00695.x：同儕審查；價格相對自身 52 週高點的位置可預測報酬（錨定），是『相對自身歷史』訊號的經典出處（未重讀全文，只引用其主旨）。
- Rapach、Ringgenberg 與 Zhou（2016）Short Interest and Aggregate Stock Returns，Journal of Financial Economics，https://doi.org/10.1016/j.jfineco.2016.03.004：同儕審查；把加總放空餘額去趨勢、標準化後，高放空預測之後 1–12 個月大盤報酬較低（依搜尋摘要與 CRAN 複製文件 https://cran.r-project.org/web/packages/forecastdom/vignettes/rrz2016-ivx-qll.html）；這是時間序列去趨勢版本，但在大盤層級，不是個股。
- Asquith、Pathak 與 Ritter（2004）Short Interest, Institutional Ownership, and Stock Returns，NBER Working Paper 10434，https://www.nber.org/system/files/working_papers/w10434/w10434.pdf：工作論文；以較長樣本指出個股放空水準的預測力比先前文獻描述的更不穩定（依搜尋摘要）。
- Ting、Lu 與 Chou（2018）Margin Trading, Differences of Opinion, and Stock Returns，Academia Economic Papers 46(3) 323–366，https://pure.lib.cgu.edu.tw/en/publications/margin-trading-differences-of-opinion-and-stock-returns/：同儕審查（台灣）；2006–2015 上市股月資料，個人融資買進把價格推高、之後報酬較低。
- Chuang（2015）Institutional Ownership and Stock Returns，Tohoku University DSSR Discussion Paper 47，https://econpapers.repec.org/RePEc:toh:dssraa:47：工作論文（台灣）；2001–2014 月資料，法人持股變化與報酬短期正相關、長期負相關。
- 本專案 docs/lending_legs_report.md：借券賣出餘額比（水準）60 日 IC +0.056（t 4.3）/ +0.058（t 5.6），但單獨多空 Sharpe −0.02 / 0.89，與 SUE 合成 2019–2022 變差；20 日增量 60 日 IC t 3.4 / 3.5。
- 本專案 docs/leg_pool_report.md：foreign_chg（外資持股比例 20 日變化）超額 Sharpe −1.38 / 0.23；券資比、融券增量失敗；融資餘額本身未單獨測過。

## 台股適用性

三個欄位都是台股每日公開、FinMind 免費的籌碼資料，前 500 名已全部快取（Shareholding、MarginPurchaseShortSale、DailyShortSaleBalances 各 776/776 檔）。資料起點 2018-06-01，250 日完整視窗要到 2019-06；計畫用最少 120 日（2018-12 起可算），2019 上半年的訊號用較短視窗。快速實測（不看報酬）：2019-01 ~ 2026-04 每月月底，前 500 名可算出 ts_rank 的比例為借券 96%、融資 96%、外資 97%（2019 上半年 95–96%）；ts_rank 與同欄位水準的橫斷面排名相關平均只有 +0.26（借券）、+0.11（融資）、+0.04（外資），與 20 日變化的相關約 +0.46 ~ +0.53，代表它是介於『水準』與『短期流量』之間的不同訊號，但與 20 日變化有一半重疊。制度差異：融資餘額會因除權息、增資等事件而有機械性變動，計畫不另做處理，只在『只報告』中加一個排除除權息前後 5 日的版本；融資資格變動（新上市、全額交割）期間為缺值。

## 所需資料

- FinMind TaiwanDailyShortSaleBalances：SBLShortSalesCurrentDayBalance（借券賣出餘額）
- FinMind TaiwanStockMarginPurchaseShortSale：MarginPurchaseTodayBalance（融資餘額，張）
- FinMind TaiwanStockShareholding：ForeignInvestmentSharesRatio（外資持股比例）、NumberOfSharesIssued（分母）
- 已快取的價格、月營收（SUE、rec24）、借券成交（fv5 可借限制）

## 檢定計畫（看結果前固定）

- 事前只測 3 個欄位，不增減、不換視窗；月營收年增率不納入（SUE 本身已是相對自身 24 個月的標準化，rec24 已是相對自身高點），毛利率不納入（季頻、一年只有 4 點，且與 I037 重疊），投信持股不納入（沒有持股水準資料，只能累加買超）。
- 樣本：主樣本市值前 500 名（config/universe_mcap_membership.csv，每年初成員），2019-01 ~ 2026-04，分 2019–2022 與 2023–2026/04 兩段；驗證樣本第 501–1000 名；2026-05 以後不使用。
- 原始欄位（第 t 日只用 t−1 日以前）：x1 = 借券賣出餘額 ÷ 已發行股數；x2 = 融資餘額 × 1000 ÷ 已發行股數；x3 = 外資持股比例。
- ts_rank：x 在自身過去 250 個交易日（含 t−1）中的百分位，(小於的個數 + 0.5 ×（相等個數 − 1））÷（有效個數 − 1），範圍 0 ~ 1；有效值少於 120 日或視窗內最大值為 0（從未被借券放空）設缺值。方向：S1 = −ts_rank(x1)、S2 = −ts_rank(x2)、S3 = +ts_rank(x3)。
- 包裝：沿用 analysis/leg_probe.py 的固定包裝（產業內 z → 20 日平均 → 對產業與 log 市值取殘差），以腿格式加入。
- IC：88 個月營收換倉日（同 daytrading_leg.py），產業內 Spearman IC 對之後 20 日與 60 日報酬，Newey-West t。主指標為 60 日（借券與營收創新高的經驗都是 60 日較強），20 日只要求同號。
- Fama-MacBeth（每個換倉日橫斷面迴歸 60 日報酬）：同時控制 SUE、rec24、同欄位水準（例如 x1 本身）、同欄位 20 日變化、12-1 動能、前 20 日報酬、log 市值、20 日周轉率；看 S 的係數。
- 多重檢定：3 個欄位，用 Bonferroni，雙尾 5% ÷ 3 → t 門檻 2.39。
- 通過標準（逐欄位，事前固定）：(a) 主樣本 60 日 IC 兩段皆 > 0、全期 t > 2.39，20 日 IC 兩段同號；(b) Fama-MacBeth 係數全期 t > 2.39、兩段同號；(c) 驗證樣本 60 日 IC > 0、t > 2。(a)–(c) 全過才做 (d)。
- (d) 可交易：fv5 建構（等權多空、限制可借、每 3 個月換倉、三份資金錯開、扣單邊 0.29625% 與借券費、台指期對沖、前 500 名），fv5 分數改為 SUE 與 S 的產業內百分位 0.75 / 0.25 加權（權重事前固定、不調）；要求兩段 Sharpe 都不低於 fv5（1.45 / 1.87）且全期高於 1.64。通過的欄位各自合成，不把多個欄位一起合成（避免事後挑組合）。
- 只報告（不作判準）：S 單獨多空 Sharpe（借券水準的經驗是 IC 顯著但多空不賺，要先看清楚）、S 與 SUE 的分數相關、ts_rank 視窗 120 日與 500 日的版本、未包裝的原始 ts_rank IC、融資版本排除除權息前後 5 日。
- 停止條件：任一欄位 (a) 不成立即停止該欄位；三個都不過就把『ts_rank 籌碼』整族登錄為 failed，不再試其他視窗或欄位。

## 與已測點子的關係

- 借券賣出餘額比、借券費率、增量、需求量（partial，docs/lending_legs_report.md）：命中 借券, short interest, 借券賣出
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 外資台指期／台指選擇權淨部位擇時（failed，docs/fut_inst_timing_report.md）：命中 外資
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue
- 法人公告前交易預告營收驚奇（failed，docs/clarification_inst_report.md）：命中 外資
- 券資比、融券增量（failed，docs/leg_pool_report.md）：命中 融資
- 投信買超、外資持股變化（failed，docs/leg_pool_report.md）：命中 外資
- 月營收驚奇 × 低法人關注：注意力低的股票漂移較強（條件分組與加權）（card:已測：未通過，research/ideas/I004-sue-x-low-attention.md）：命中 外資持股比例
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 法人公告前交易是否預告營收驚奇：未被預先交易的驚奇漂移較強（card:已測：未通過，research/ideas/I036-institutional-anticipation-sue.md）：命中 外資
- 補充：與 lending_legs（partial）的差別：那裡是借券餘額比的橫斷面水準與 20 日增量；本卡比的是每檔相對自己一年的位置（實測與水準相關 +0.26、與 20 日變化 +0.50），並在 Fama-MacBeth 同時控制水準與增量，只認增量。與 foreign_chg（failed）的差別：20 日差分很吵且受單日外資大買賣主導，ts_rank 是一年尺度的位置（與 20 日變化相關 +0.53）。與券資比、融券增量（failed）的差別：本卡用融資（多方槓桿）本身，未測過。與 I004 低法人關注（failed）的差別：I004 用外資持股水準當注意力，本卡用外資持股相對自身的變化當資訊。風險：借券水準的 IC 顯著但多空不賺，同族訊號可能重演；所以判準 (d) 以 fv5 合成為準。


## 結果（2026-10-21）

S1 借券賣出餘額比 ts_rank 通過 (a)–(d)：60 日 IC +0.038 / +0.066（全期 t 5.3）、控制後 t 3.0、驗證 +0.031（t 2.4）、fv5 合成 1.48 / 2.15（全期 1.78 vs 1.64）。S2 融資餘額比方向相反且顯著（t −3.0），S3 外資持股比例不顯著。見 [docs/ts_rank_report.md](../../docs/ts_rank_report.md)。

研究點子，非投資建議。
