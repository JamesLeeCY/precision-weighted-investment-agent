# I077 處分效果的未實現獲利（capital gains overhang，Grinblatt–Han 台股版）：以換手率加權的參考價計算，未實現獲利高的股票之後報酬較高

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 橫斷面 IC（Fama-MacBeth 增量，產業內） | free | 約 0（前 1500 名價格與成交量 2017 起、TaiwanStockShareholding 已發行股數 2018-06 起、還原價與 TaiwanStockSplitPrice 已快取）；若要 2018-06 以前的股數補 2017 年，約 1,500 次（不建議，訊號從 2019-07 起即可） | 2026-10-27 |

## 假設

在市值前 500 名中，月底的未實現獲利 CGO（現價相對以換手率加權的平均持有成本）在產業內排名愈高，之後 60 個交易日的產業調整報酬愈高；控制 12-1 動能、1 個月報酬、SUE、log 市值與換手率後，Fama-MacBeth 全期 t ≥ 2.58、兩段同號，第 1001–1500 名同號 t ≥ 2.0。

## 機制（為什麼會有超額報酬）

處分效果：投資人傾向賣出賺錢的股票、抱住賠錢的股票。未實現獲利多的股票有持續的賣壓，價格暫時低於基本價值、之後補漲；未實現虧損多的股票惜售，價格偏高、之後落後。台灣散戶比重高，Barber 等人用台灣全市場交易資料證實處分效果強。Grinblatt 與 Han 認為這是動能的來源之一，而且 CGO 控制動能後仍有預測力；台股 12-1 動能在本專案無效，正好可以檢驗 CGO 是否是與動能不同的機制。

## 出處

- （工作論文，後刊於 Journal of Financial Economics 2005）Grinblatt、Han（2002）The Disposition Effect and Momentum，NBER Working Paper 8734，https://doi.org/10.3386/w8734：依摘要，處分效果讓市價與基本價值之間出現價差，使價格呈現可預測的延續
- （同儕審查）An（2016）Asset Pricing When Traders Sell Extreme Winners and Losers，Review of Financial Studies，https://doi.org/10.1093/rfs/hhv060：依摘要，未實現大賺與大賠的股票下個月都表現較好，月 alpha 0.5–1%，無法以動能、反轉、波動解釋
- （同儕審查，台灣）Barber、Lee、Liu、Odean（2007）Is the Aggregate Investor Reluctant to Realise Losses? Evidence from Taiwan，European Financial Management 13(3): 423–447，https://ideas.repec.org/a/bla/eufman/v13y2007i3p423-447.html：台灣證交所 1995–1999 全部交易，投資人賣出獲利股的機率約為虧損股的 2 倍
- （碩士論文，台灣）展望理論、心理帳戶、與動能效果於台灣股票市場之實證分析（2007，淡江大學），https://doi.org/10.6846/tku.2007.00347：依摘要，以 Grinblatt–Han 架構檢驗台股 CGO 的預測力；未讀到結果

## 台股適用性

處分效果在台灣有最直接的交易層級證據，但 CGO 的報酬預測在台股沒有找到同儕審查的實證。台股換手率高（大型股年換手常超過 100%），以換手率加權的參考價在 1 年內就幾乎收斂，所以 250 日視窗足夠。風險：CGO 與 12-1 動能高度相關，而動能、反轉在本專案都失敗；除息會讓未還原價格出現假的『虧損』，需處理；An（2016）的 V 型版本是月頻、換手高，在台股成本下不易存活，只報告。

## 所需資料

- FinMind TaiwanStockPrice（已快取）：收盤價、成交量
- FinMind TaiwanStockShareholding NumberOfSharesIssued（已快取，2018-06 起）：換手率 = 成交股數 ÷ 已發行股數
- FinMind TaiwanStockSplitPrice／還原價（已快取）：處理減資、分割；除息版本對照
- FinMind TaiwanStockMonthRevenue（已快取）：SUE 控制變數

## 檢定計畫（看結果前固定）

- 樣本：前 500 名，2019-07 ~ 2026-04 每月底（需 250 個交易日的換手資料）；兩段 2019-07 ~ 2022 / 2023 ~ 2026/04；確認樣本第 1001–1500 名；2026-05 以後不用。
- 訊號：參考價 RP = Σ_{n=1..250} w_n · P_{t−n}，w_n = V_{t−n} · Π_{τ=1..n−1}(1 − V_{t−n+τ})，再除以 Σ w_n 正規化；V 為日換手率（上限 1）、P 為只調整減資與分割、不調整除息的收盤價（反映投資人的名目成本）。CGO = (P_{t−5} − RP_{t−5}) / P_{t−5}，跳過最近 5 個交易日以避開短期反轉。轉為產業內百分位。
- H1（主判定，計入本批 Holm）：被解釋變數為之後 60 個交易日產業調整報酬的產業內百分位；控制 12-1 動能、前 20 日報酬、上月 SUE、log 市值、前 250 日平均換手率；Fama-MacBeth、Newey-West 落後 2。通過：全期 t ≥ 2.58、兩段同號且第二段 t ≥ 1.5、第 1001–1500 名同號且 t ≥ 2.0。
- H2（只在 H1 通過時做）：照 I040 的做法，0.75 SUE + 0.25 CGO 百分位的 fv5 建構；通過：兩段 Sharpe 皆高於 fv5（1.45 / 1.87）、全期 > 1.64。
- 只報告：不控制動能的原始 IC；An（2016）的 V 型分數（未實現獲利與虧損分開）；用還原價計算的 CGO；CGO 與 12-1 動能、SUE 的相關；CGO 單獨等權多空扣成本後的 Sharpe 與年換手。
- 資料窺探：本專案沒有計算過 CGO；12-1 動能與反轉已失敗，因此 H1 必須控制兩者。未通過即停止，不改視窗長度、價格調整方式或跳過天數重測。
- 本批 Holm 校正（5 張卡、α = 5%、雙尾）：依 p 值由小到大的門檻為 t ≥ 2.58、2.50、2.39、2.24、1.96。

## 與已測點子的關係

- 12-1 動能、持續性動能、frog-in-the-pan（failed，docs/revmom_persist_report.md）：命中 動能, 12-1
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 金融股自結盈餘驚奇低換手多空（緩衝換倉）（failed，docs/fin_esue_followup_report.md）：命中 換手
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue
- 處置股（做空與做多）（failed，docs/event_study_report.md）：命中 disposition
- 金融股自結盈餘驚奇的低換手多空（緩衝換倉）（card:已測：未通過，research/ideas/I017-financial-esue-low-turnover-ls.md）：命中 換手
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- PTT 股版討論量暴增（相對自身歷史）：散戶注意力代理，Google 搜尋熱度為穩健性（card:已測：未通過，research/ideas/I041-ptt-discussion-surge-attention.md）：命中 股版
- 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）（card:已測：未通過（階段 1 過、階段 2 t 2.8），research/ideas/I043-smallcap-multifactor-composite.md）：命中 sue
- 融券強制回補的價格壓力（I050 修訂版）：以官方停券日為事件日，在未看過的第 501–1500 名確認，處理 I056 附帶發現的資料窺探（card:已測：未通過（P2 t 1.3；I059 啟動條件成立），research/ideas/I058-forced-covering-oos-501-1500.md）：命中 第 1001–1500 名
- fv5 用平滑的月營收驚奇排序以降低換手：最近 3 個月 SUE 產業內百分位的平均取代單月 SUE（其餘建構不變）（card:待確認，research/ideas/I076-fv5-smoothed-sue-low-turnover.md）：命中 換手
- 補充：與 12-1 動能、持續性動能、frog-in-the-pan（failed）不同：CGO 以換手率加權的持有成本衡量賣壓，主判定控制 12-1 動能與前 20 日報酬，只看增量。與處置股（disposition，failed）只是英文字面相同：處置股是交易所的處置措施，本卡是行為面的處分效果。

研究點子，非投資建議。
