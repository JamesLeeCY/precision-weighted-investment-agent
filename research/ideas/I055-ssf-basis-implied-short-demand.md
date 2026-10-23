# I055 股票期貨基差（期貨相對現貨的年化折溢價）：期貨折價深的股票之後報酬較差（隱含放空需求）

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 橫斷面 IC（日頻訊號、月頻評估）＋ Fama-MacBeth 增量＋與 fv5 合成 | free | 約 0–150（245 檔標準型股票期貨 2019–2026/05 已快取；若要補回測期間曾經存在、現已下市的股票期貨，依期交所歷史標的清單約 50–150 次） | 2026-10-23 |

## 假設

在有標準型股票期貨的前 500 名股票中，近月期貨相對現貨的年化基差在同日橫斷面排名越低（折價越深），之後 20／60 個交易日的產業調整報酬越低；控制 SUE、借券費率與 S1（借券餘額 ts_rank）後，基差的 Fama-MacBeth 係數兩段皆為正（t > 2）。

## 機制（為什麼會有超額報酬）

限制套利與放空需求：現股放空受借券供給與費率限制時，想放空的人改用期貨空單，壓低期貨相對現貨的價格；理論上基差應只反映資金成本（同日各股相同），橫斷面差異因此代表『未被滿足的放空需求或借券成本』。美國文獻顯示選擇權買賣權平價的偏離（合成空單價格）與選擇權隱含借券費都能預測個股報酬，且隱含借券費在扣除報價借券費後仍有預測力。台股個股選擇權流動性差，但標準型股票期貨流動性較好，是同一資訊的替代來源。反向機制：散戶用期貨做多（槓桿）也會推高基差，屬於過度樂觀，同樣預期之後報酬較差（溢價高者較差），需事前固定方向。

## 出處

- （同儕審查）Ofek、Richardson 與 Whitelaw（2004）Limited arbitrage and short sales restrictions: evidence from the options markets，Journal of Financial Economics 74(2)，https://www.nber.org/papers/w9423：買賣權平價的偏離方向與放空限制一致，偏離幅度與放空成本都能預測個股報酬（依摘要）
- （同儕審查）Muravyev、Pearson 與 Pollet（2022）Is there a risk premium in the stock lending market? Evidence from equity options，Journal of Finance，https://experts.illinois.edu/en/publications/is-there-a-risk-premium-in-the-stock-lending-market-evidence-from/ ；其工作論文 Understanding returns to short selling using option-implied stock borrowing fees：選擇權隱含借券費能預測未來費率與扣除報價借券費後的報酬（依摘要）
- （本專案）docs/lending_legs_report.md：借券費率 60 日 IC 兩段顯著但單獨多空不賺錢；docs/ts_rank_report.md：S1 與 SUE 合成有效
- （本專案）docs/futures_exec_report.md：245 檔股票期貨 2019–2026 已快取；期貨與現股月報酬差中位數 0.53%（含股利與持有成本差）
- （期交所公告，非研究）2026 年股票期貨契約調整公告，例如 https://www.taifex.com.tw/file/taifex/CHINESE/11/attach/2312_20260623.pdf：現金股利以調整買賣方權益數處理、不調整契約價格（需在前置檢查確認對基差的影響）

## 台股適用性

沒有找到台灣股票期貨基差預測個股報酬的實證（只有指數期貨領先現貨的研究），屬於把美國選擇權文獻移植到台股期貨，證據等級為同儕審查（美國、選擇權）＋無台灣實證。制度差異：(1) 股票期貨一般時段 13:45 收盤、現股 13:30 收盤，有 15 分鐘時差，同日共同的大盤變動在橫斷面排名中大致抵銷，但仍有個股雜訊，訊號用 5 日平均；(2) 現金股利以權益數調整，理論上期貨價格不需扣股利，但 I031 的觀察顯示可能仍有股利差異，需前置檢查；(3) 只有約 245 檔有標準型期貨（偏大型），沒有獨立的中小型股驗證樣本，因此門檻提高到全期 t > 3。與 SUE 預期低相關（價格衍生資訊 vs 營收）。

## 所需資料

- FinMind TaiwanFuturesDaily 股票期貨（已快取 245 檔）：各月份契約結算價、收盤價、成交量、未平倉量
- FinMind TaiwanStockPrice、DividendResult（已快取）：現貨收盤、除息日與現金股利
- FinMind TaiwanStockSecuritiesLending、TaiwanDailyShortSaleBalances（已快取）：借券費率、S1 控制變數
- 期交所股票期貨標的清單與契約調整公告：核對歷史標的與股利調整方式（網頁，約 20–50 次）

## 檢定計畫（看結果前固定）

- 樣本：前 500 名中當日有標準型股票期貨、近月契約未平倉 ≥ 50 口的股票；2019-03 ~ 2026-04，兩段 2019–2022 / 2023–2026/04；2026-05 以後不用。
- 前置檢查（看報酬前）：(a) 基差 B 在除息月與非除息月的橫斷面中位數差，若除息前月份的期貨相對現貨系統性低於股利現值的一半以上，訊號改為扣除已公告現金股利後的版本（只決定定義，不看報酬）；(b) 每日可用股數中位數 ≥ 100 檔，否則停止。
- 訊號：B = ln(F ÷ S) × 365 ÷ 到期天數，F 為近月契約結算價（距到期 < 10 個交易日改用次月），S 為現貨收盤；取 5 個交易日平均；同日橫斷面減去中位數（去除利率）。方向事前固定：B 低（折價深）→ 之後報酬較差，即訊號 = +B。
- 主檢定：每月換倉日（營收公告期限次一交易日）計算 B 與之後 20 日、60 日報酬的產業調整 Spearman IC（同產業 < 3 檔時以全樣本去產業平均）；Fama-MacBeth 控制 SUE、60 日借券費率、S1、規模、20 日反轉，Newey-West 落後 2。
- 附帶（只報告）：B 的極端兩端（前後 10%）分開看，檢查是『折價深者差』還是『溢價高者差』；未平倉量 20 日變化率的 IC。
- 成本與建構：只在通過主檢定後做；fv5 分數 = 0.75 × SUE 產業內百分位 + 0.25 × B 百分位（沒有期貨的股票 B 取中位數），建構其餘同 fv5，成本單邊 0.29625% + 借券費、台指期對沖。
- 通過標準：(1) 60 日 IC 兩段皆 > 0 且 t > 2、全期 t > 3（因無獨立驗證樣本而提高）；(2) 控制借券費率與 S1 後的係數全期 t > 2；(3) 合成後 fv5 兩段 Sharpe 都不低於 fv5（1.45 / 1.87）。全部成立才建議另立前瞻規格。
- 多重檢定與資料窺探：主檢定只有 1 個訊號、1 個方向、2 個視窗（20／60 日，以 60 日為主）；期貨資料已在 I031 抓過但只看過追蹤誤差，從未看過基差與報酬的關係。

## 與已測點子的關係

- 用股票期貨執行 fv5：以期交稅取代證交稅、以期貨空單取代借券（card:停止：追蹤誤差未過，research/ideas/I031-fv5-single-stock-futures-execution.md）：命中 股票期貨, single stock futures, stock futures, short-sale constraints
- 借券賣出餘額比、借券費率、增量、需求量（partial，docs/lending_legs_report.md）：命中 借券, borrow fee
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 股票期貨, single stock futures
- 借券賣出餘額比相對自身歷史（ts_rank）——與 SUE 合成（effective，docs/ts_rank_report.md）：命中 ts_rank, 借券
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 外資台指期／台指選擇權淨部位擇時（failed，docs/fut_inst_timing_report.md）：命中 未平倉
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue
- 融資餘額比、外資持股比例的 ts_rank（failed，docs/ts_rank_report.md）：命中 ts_rank
- 台指選擇權 Put/Call 比逆向擇時（candidate，docs/pcr_timing_report.md）：命中 未平倉
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 相對自身歷史的時間序列排名（ts_rank）：借券賣出餘額比、融資餘額比、外資持股比例（card:已測：S1 通過（S2、S3 未通過），research/ideas/I040-ts-rank-own-history-chip-fields.md）：命中 ts_rank
- PTT 股版討論量暴增（相對自身歷史）：散戶注意力代理，Google 搜尋熱度為穩健性（card:已測：未通過，research/ideas/I041-ptt-discussion-surge-attention.md）：命中 ts_rank
- 中小型股（市值第 501–1000 名）執行面前置檢查：容量、滑價、漲跌停、借券與避險工具（card:已測：L2、S 未過（只做統計檢定），research/ideas/I042-smallcap-execution-precheck.md）：命中 借券
- 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）（card:已測：未通過（階段 1 過、階段 2 t 2.8），research/ideas/I043-smallcap-multifactor-composite.md）：命中 sue
- 補充：與 I031（用股票期貨執行 fv5，追蹤誤差未過）不同：I031 是執行工具，本卡把基差當選股訊號。與借券費率（partial）、S1（effective）同屬放空需求的資訊，但來源不同（期貨市場價格 vs 借券市場報價），所以主檢定要求控制兩者後仍顯著；若只是借券費率的代理，就不採用。評為 B 是因為沒有台灣實證、樣本只有約 245 檔、與借券族可能高度重疊。

研究點子，非投資建議。
