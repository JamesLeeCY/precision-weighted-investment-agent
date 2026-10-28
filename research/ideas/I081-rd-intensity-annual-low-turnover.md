# I081 研發密度（研發費用 ÷ 市值）的年度低換手訊號：研發密集公司被低估（Chiao–Hung–Lee 台股版），每年 4 月換倉一次

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 橫斷面 IC（Fama-MacBeth 增量，產業內；年度訊號、月頻評估） | manual | FinMind 約 0；公開資訊觀測站約 8,000 次（約 1,000 家 × 2017–2024 年度綜合損益表，前 500 名與第 501–1000 名），若可用 XBRL 整批檔案則約 50 次以內；正式抓取前先試抓 1–2 家確認欄位 | 2026-10-28 |

## 假設

在市值前 500 名有研發支出的公司中，上一年度研發費用 ÷ 3 月底市值（RDME）在產業內排名愈高，之後 12 個月每月的產業調整報酬愈高；控制 log 市值、淨值市價比、12-1 動能與 SUE 後，月頻 Fama-MacBeth 全期 t 達本批 Holm 門檻、兩段同號，第 501–1000 名同號且 t ≥ 2.0。

## 機制（為什麼會有超額報酬）

會計把研發費用當期全額認列，研發密集公司的盈餘與帳面淨值被低估，投資人容易對其無形資產過度悲觀（Chan 等 2001）；研發增加後市場反應不足，之後有正的長期異常報酬（Eberhart 等 2004）。這是年度、慢變動的特徵，一年換倉一次，年換手遠低於 fv5，與月營收驚奇的資訊來源（短期營收動能）不同。

## 出處

- （同儕審查）Chan、Lakonishok、Sougiannis（2001）The Stock Market Valuation of Research and Development Expenditures，Journal of Finance 56(6)，https://doi.org/10.1111/0022-1082.00411：依摘要，有無研發的公司平均報酬相近，但市場對過去表現差的研發密集科技股過度悲觀
- （同儕審查）Eberhart、Maxwell、Siddique（2004）An Examination of Long-Term Abnormal Stock Returns and Operating Performance Following R&D Increases，Journal of Finance 59(2)，https://doi.org/10.1111/j.1540-6261.2004.00644.x：依摘要，1951–2001 年 8,313 次大幅且非預期的研發增加後，股東有顯著正的異常報酬，營運績效也改善，作者解讀為市場反應不足
- （同儕審查，台灣）Chiao、Hung、Lee（2008）Mispricing of Research and Development Investments in a Rapidly Emerging and Electronics-Dominated Market，Emerging Markets Finance and Trade 44(1): 95–116，https://ideas.repec.org/a/mes/emfitr/v44y2008i1p95-116.html：依摘要，台股 1988-07 ~ 2005-06 研發密集公司表現優於低研發公司，無法完全以規模或季節性解釋，效果最長持續 3 年，1996 年後的電子股較明顯
- （台灣，二手轉述，未讀原文）交通大學論文〈研發密集公司超額報酬為風險溢酬之額外證據〉，https://ir.lib.nycu.edu.tw/handle/11536/107932：依搜尋摘要，引述 Fan 與 Lin（2010）認為台股研發密集公司的超額報酬可能來自風險未充分控制；作為反方證據

## 台股適用性

台股以電子業為主，研發支出集中在半導體、電子零組件、電腦週邊，產業內排名可避免把產業差異誤認為研發效果。台灣證據來自 2005 年以前，之後是否仍存在未知；Fan 與 Lin 的風險解釋若成立，控制規模與淨值市價比後可能不顯著。FinMind 的 TaiwanStockFinancialStatements 不含研發費用欄位（已用 2330、2454、2603、2882 確認），需從公開資訊觀測站的綜合損益表（研究發展費用）取得，這是主要成本。只用年度數字（年報 3/31 前公告），4 月第 2 個交易日進場，沒有前視問題。

## 所需資料

- 公開資訊觀測站 綜合損益表（研究發展費用、營業收入）年度數：RDME 與只報告用的研發／營收
- FinMind TaiwanStockBalanceSheet（已快取）：股東權益，淨值市價比控制變數
- FinMind TaiwanStockPrice、TaiwanStockShareholding（已快取）：市值、12-1 動能、產業調整報酬
- FinMind TaiwanStockMonthRevenue（已快取）：SUE 控制變數

## 檢定計畫（看結果前固定）

- 樣本：前 500 名中上一年度研發費用 > 0 的公司，只用研發公司數 ≥ 5 家的產業；訊號年度 2018–2024（2019-04 ~ 2026-04 共約 85 個月），兩段 2019-04 ~ 2022 / 2023 ~ 2026/04；確認樣本第 501–1000 名；2026-05 以後不用。
- 訊號：RDME = 上一年度研發費用 ÷ 3 月最後一個交易日市值，每年 4 月第 2 個交易日更新，之後 12 個月固定；轉為產業內百分位。
- H1（主判定，計入本批 Holm）：每月月底，被解釋變數為之後 20 個交易日產業調整報酬的產業內百分位；控制 log 市值、淨值市價比、12-1 動能、上月 SUE；Fama-MacBeth、Newey-West 落後 3。通過：全期 t 達 Holm 門檻、兩段同號且第二段 t ≥ 1.5、第 501–1000 名同號且 t ≥ 2.0。
- H2（只在 H1 通過時做）：獨立低換手多空——每年 4 月換倉一次，產業內 RDME 前／後 1/3 等權、借券條件 D、台指期對沖、單邊 0.29625% 與實際借券費；跨越檢定：日淨報酬對 fv5 日淨報酬與 I049 的 5 個風格因子迴歸，截距全期 t ≥ 2.0 且兩段截距 > 0。
- 只報告：研發／營收版本；Eberhart 等的研發大幅增加事件（年增 ≥ 5% 且研發／資產 ≥ 5%）之後 12 個月的配對 CAR；電子業 vs 非電子業；RDME 與 SUE、淨值市價比的相關；多空的年換手。
- 資料窺探：本專案從未用過研發費用；財報類訊號（資產成長、營收品質、利潤率驚奇、GP/A）多數失敗，因此 H1 要控制淨值市價比與 SUE，只看增量。未通過即停止，不改用研發資本化或其他分母重測。
- 本批 Holm 校正（5 張卡、α = 5%、雙尾）：依 p 值由小到大的門檻為 t ≥ 2.58、2.50、2.39、2.24、1.96；單卡至少要過最嚴的 2.58 才保證通過，其餘依 Holm 逐步判定。

## 與已測點子的關係

- 12-1 動能、持續性動能、frog-in-the-pan（failed，docs/revmom_persist_report.md）：命中 動能, 12-1
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 金融股自結盈餘驚奇低換手多空（緩衝換倉）（failed，docs/fin_esue_followup_report.md）：命中 換手
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue
- 金融股自結盈餘驚奇的低換手多空（緩衝換倉）（card:已測：未通過，research/ideas/I017-financial-esue-low-turnover-ls.md）：命中 換手
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 小型股版月營收驚奇：第 501–1000 名獨立多空，以及前 1000 名廣度版本（card:已測：階段一未通過（接近），research/ideas/I030-smallcap-sue-501-1000.md）：命中 第 501–1000 名
- PTT 股版討論量暴增（相對自身歷史）：散戶注意力代理，Google 搜尋熱度為穩健性（card:已測：未通過，research/ideas/I041-ptt-discussion-surge-attention.md）：命中 股版
- 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）（card:已測：未通過（階段 1 過、階段 2 t 2.8），research/ideas/I043-smallcap-multifactor-composite.md）：命中 sue
- 融券強制回補的價格壓力（I050 修訂版）：以官方停券日為事件日，在未看過的第 501–1500 名確認，處理 I056 附帶發現的資料窺探（card:已測：未通過（P2 t 1.3；I059 啟動條件成立），research/ideas/I058-forced-covering-oos-501-1500.md）：命中 第 501–1000 名
- fv5 持股遇到反向季報反應即出場：多單 QEAR 落在後 1/3、空單 QEAR 落在前 1/3 時，在公告後第 +3 日收盤平倉（名單與換倉日不變，只加事件出場）（card:已測：未通過，research/ideas/I074-fv5-qear-contrary-exit.md）：命中 低換手
- fv5 用平滑的月營收驚奇排序以降低換手：最近 3 個月 SUE 產業內百分位的平均取代單月 SUE（其餘建構不變）（card:已測：未通過，research/ideas/I076-fv5-smoothed-sue-low-turnover.md）：命中 換手
- 補充：與財報類已測點子（I020 資產成長、I028 營收品質、I037／I048 利潤率驚奇、I044 GP/A）同屬季報／年報特徵，但機制不同（無形投資被低估），且以年度換倉降低換手；FinMind 沒有研發欄位，所以專案從未測過。

研究點子，非投資建議。
