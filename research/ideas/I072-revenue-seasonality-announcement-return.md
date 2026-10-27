# I072 月營收的可預期季節性（Chang–Hartzmark–Solomon–Soltes 台股月頻版）：即將公告的月份歷來是營收旺月的股票，公告期報酬較高

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | C | 橫斷面 IC（Fama-MacBeth，被解釋變數為公告期報酬）＋高門檻的可交易檢查 | free | 約 0（前 1500 名月營收、還原價、產業分類已在 I063 使用） | 2026-10-27 |

## 假設

在市值前 500 名中，即將公告的月份在過去 36 個月營收中排名愈高（歷來的旺月）的股票，該月營收公告期間（I063 的 EAR 視窗）的產業調整報酬愈高；控制上月 SUE、上月 EAR、上月公告後報酬與市值後，Fama-MacBeth 全期 t ≥ 2.58、兩段同號，第 1001–1500 名同號 t ≥ 2.0。

## 機制（為什麼會有超額報酬）

Chang、Hartzmark、Solomon、Soltes（2017）發現歷來盈餘較大的季度，公司在公告時有較高報酬，分析師預測誤差在這些季度也偏正；作者認為投資人過度依賴最近較低的盈餘，低估可預期的季節旺季。台灣月營收的季節性比季盈餘更強（電子業的備貨旺季、零售的年節），而且每月公告，若投資人以上月或近月營收水準形成預期，旺月公告前就會低估。SUE 用年增率衡量，已去除季節性，所以這個訊號預測的是公告期報酬本身，而不是 SUE。

## 出處

- （同儕審查）Chang、Hartzmark、Solomon、Soltes（2017）Being Surprised by the Unsurprising: Earnings Seasonality and Stock Returns，Review of Financial Studies 30(1): 281–323，https://ideas.repec.org/a/oup/rfinst/v30y2017i1p281-323..html（SSRN https://papers.ssrn.com/abstract=2460166）：依摘要，歷來盈餘較大季度的公司在該季公告時報酬較高，分析師預測誤差在這些季度偏正，風險與成交量等解釋都無法說明
- （本專案）docs/revenue_ear.md（I063）：月營收公告期報酬是穩定的訊號，視窗定義可直接沿用
- （本專案）docs/reversal_signals_report.md：Heston–Sadka 型的同月份報酬季節性與季節性動能在台股前 300 名無效；本卡是營收（基本面）的季節性，不是報酬的季節性

## 台股適用性

台灣月營收逐月公布，季節性可用過去 36 個月精確估計，資料已快取。產業調整會去掉整個產業共同的旺季（例如零售業 12 月），訊號只剩同產業內公司間的季節差異，例如客戶組合不同的電子零組件公司。最大限制是可交易性：訊號預測的是約 8 個交易日的公告期報酬，必須在月底建倉、公告期結束平倉，每月來回成本約 0.59%（多方）加上空方借券與成本，效果要很大才付得起；因此主要價值可能是統計知識與 EAR 的清理（扣掉可預期的季節性反應後的 EAR 是否更準），先做統計檢定、可交易門檻設得很高。沒有找到台股或新興市場的實證。

## 所需資料

- FinMind TaiwanStockMonthRevenue（已快取）：過去 36 個月營收排名、SUE
- FinMind TaiwanStockPrice 還原價（已快取）：EAR 與控制變數
- config/universe_mcap_membership.csv、config/universe_mcap_membership_1500.csv
- analysis/revenue_ear.py（EAR 視窗與 PRE 控制的寫法）

## 檢定計畫（看結果前固定）

- 樣本：前 500 名，2019-03 ~ 2026-04 每月（需至少 36 個月營收歷史）；兩段 2019–2022 / 2023–2026/04；確認樣本第 1001–1500 名；2026-05 以後不用。
- 訊號：SEAS = 在 m 月月底（m 月營收尚未公告）時，過去 36 個月營收（m−36 ~ m−1）中與 m 同月份的 3 個值，其在 36 個月內排名百分位的平均；轉為產業內百分位。只用 m 月月底前已公告的營收。
- 被解釋變數：m+1 月的 EAR（m 月最後交易日收盤 → m+1 月 fv5 換倉日前一日收盤的產業調整報酬，與 I063 相同），轉為產業內百分位。
- H1（主判定）：控制 m−1 月 SUE、m−1 月 EAR、m 月公告後報酬 PRE、log 市值，Fama-MacBeth、Newey-West 落後 1。通過：全期 t ≥ 2.58（本批 Holm 最嚴門檻）、兩段同號且第二段 t ≥ 1.5、第 1001–1500 名同號且 t ≥ 2.0。
- H2（可交易，只在 H1 通過時做）：m 月最後交易日收盤，產業內 SEAS 前 1/3 等權做多、台指期對沖，m+1 月換倉日前一日收盤平倉。通過：兩段扣成本（來回 0.59%）後月均超額報酬皆 > 0 且全期 t ≥ 2.0。放空腿只報告（借券成本不確定）。
- 只報告：SEAS 前／後 1/3 的 EAR 差（月、百分比，未扣成本）；EAR 扣掉 SEAS 可預期部分的殘差版本對之後 60 日報酬的 FM 係數（與 I063 原版比較）；SEAS 與 SUE 的相關；只用電子業的版本。
- 資料窺探：本專案沒有看過營收季節性的任何結果；I063 的 EAR 主效果已看過，但本卡的被解釋變數是 EAR 本身，不是 EAR 之後的報酬。未通過即停止，不改 36 個月視窗或排名方法重測。

## 與已測點子的關係

- 月營收公告期間的市場反應（公告期報酬）對 SUE 的增量：價格反應是否帶有營收數字以外的資訊（card:已測：H1 通過、H2 未通過（不另立前瞻），research/ideas/I063-revenue-announcement-window-return-ear.md）：命中 公告期報酬, announcement return, EAR, 月營收公告
- 月營收公告期報酬（EAR）的獨立多空與 fv5 各半組合：EAR 是否提供 fv5 之外的報酬來源（I063 後續，以跨越檢定判定）（card:待確認，research/ideas/I068-ear-standalone-ls-fv5-blend.md）：命中 公告期報酬, EAR, announcement return
- 季節性、季節性動能（failed，docs/reversal_signals_report.md）：命中 季節性, seasonality
- fv5 腿內依 EAR 加權（SUE 與公告期報酬同向加碼、反向減碼）：名單不變只調權重，以第 501–1000 名選規則、第 1001–1500 名確認（card:待確認，research/ideas/I069-fv5-inleg-ear-agreement-weight.md）：命中 公告期報酬, EAR
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）（card:已測：未通過（階段 1 過、階段 2 t 2.8），research/ideas/I043-smallcap-multifactor-composite.md）：命中 sue
- 融券強制回補的價格壓力（I050 修訂版）：以官方停券日為事件日，在未看過的第 501–1500 名確認，處理 I056 附帶發現的資料窺探（card:已測：未通過（P2 t 1.3；I059 啟動條件成立），research/ideas/I058-forced-covering-oos-501-1500.md）：命中 第 1001–1500 名
- 季報公告的價格反應（季報 EAR）：以公開資訊觀測站實際財報董事會日期計算的 2 日產業調整報酬，對 SUE 與月營收 EAR 的增量（card:待確認，research/ideas/I070-quarterly-report-announcement-return.md）：命中 announcement return
- 補充：與已失敗的報酬季節性（Heston–Sadka 同月份報酬、季節性動能）不同：本卡用營收的季節型態預測公告期報酬。與 I026 工作日調整 SUE（去除日曆雜訊）不同：本卡不改 SUE，而是預測價格反應。與 I063 不同：I063 用 EAR 預測之後 60 日，本卡預測 EAR 本身。

研究點子，非投資建議。
