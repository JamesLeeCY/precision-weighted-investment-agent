# I029 淨發行股數（股本膨脹）：過去 12 個月經配股調整後股數增加多的股票之後報酬較低

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過 | C | 橫斷面 IC（月頻）＋等權多空＋與 SUE 合成 | free（已快取） | FinMind 約 0–300（TaiwanStockShareholding 已快取 1,056 檔、TaiwanStockDividendResult／TaiwanStockSplitPrice 已快取 1,689 檔；第 501–1000 名缺額估計 < 300 次）；公開資訊觀測站 0 次 | 2026-10-18 |

## 假設

過去 12 個月經股票股利與分割調整後的流通股數成長率（NSI）高的股票，之後 20 與 60 個交易日的產業內報酬排名較低（產業內 IC(−NSI) > 0），且控制資產成長與 SUE 後仍成立。

## 機制（為什麼會有超額報酬）

市場擇時：管理層在股價高估時發行新股（現金增資、可轉債轉換、員工限制型股票），在低估時買回註銷；投資人對發行的長期含意反應不足。McLean、Pontiff 與 Watanabe（2009）在 41 個國家的非美國樣本發現發行可預測報酬，大型股與小型股都成立，且非美國的效果主要來自發行後的低報酬。這是經典因子中少數有『大型股也成立』國際證據的一個，因此值得在前 500 名確認一次。

## 出處

- McLean, Pontiff & Watanabe（2009）Share Issuance and Cross-Sectional Returns: International Evidence，Journal of Financial Economics 94(1):1–17，https://ideas.repec.org/a/eee/jfinec/v94y2009i1p1-17.html：41 國非美國樣本中發行可預測報酬，顯著性高於規模與動能、與淨值市價比相近；大小型股都成立；主要來自發股後的低報酬；在發行活動多、市場發達、投資人保護強的國家較強（摘要）【同儕審查】
- Pontiff & Woodgate（2008）Share Issuance and Cross-sectional Returns，Journal of Finance 63(2):921–945，https://ideas.repec.org/a/bla/jfinan/v63y2008i2p921-945.html：美國淨發行可預測報酬（本次只讀到題目與出處）【同儕審查，未讀摘要】
- Equity Anomalies and Idiosyncratic Risk Around the World（2015）Multinational Finance Journal，https://doi.org/10.17578/19-1-2：淨發行、資產成長、應計等異常在各國的異常報酬差異很大，新興與已開發市場不同（摘要）【同儕審查】
- 本專案 docs/corp_events_report.md（I012 現金增資與可轉債公告：公告隔日即反映、之後無可交易超額）、docs/asset_growth_report.md（資產成長在前 500 名 IC ≈ 0，只在第 501–1000 名有效）【本專案實證】

## 台股適用性

沒有找到台股前 500 名的淨發行實證。台股股數變動來源很多：盈餘或資本公積轉增資（需調整掉，屬機械性）、現金增資、可轉債轉換、員工限制型股票、庫藏股註銷、減資。資料都已快取（FinMind TaiwanStockShareholding 的 NumberOfSharesIssued 從 2018-06 起每日一筆），請求數接近 0。風險很高：(1) 同族的資產成長在前 500 名完全失效，淨發行與資產成長正相關；(2) I012 顯示現金增資與可轉債的資訊在公告隔日就反映；(3) 2019–2026 的高成長股常同時增資擴產，可能重演資產成長多空大虧的情形。所以列為 C，只在想確認『經典因子在大型股全面失效』時再做。

## 所需資料

- FinMind TaiwanStockShareholding（已快取）：已發行股數（每日）
- FinMind TaiwanStockDividendResult＋TaiwanStockSplitPrice（已快取）：股票股利、分割、減資的調整因子
- FinMind TaiwanStockBalanceSheet（已快取）：資產成長控制變數
- FinMind TaiwanStockMonthRevenue、TaiwanStockPrice（已快取）：SUE 與報酬

## 檢定計畫（看結果前固定）

- 樣本：前 500 名，2019-07 ~ 2026-04 每月月底（股數資料從 2018-06 起，需 12 個月）；兩段 2019-07–2022 / 2023–2026/04；驗證樣本第 501–1000 名；2026-05 以後不使用。
- 訊號（看結果前固定）：NSI = log(調整後股數_t ÷ 調整後股數_{t−12 個月})，調整後股數 = 已發行股數 ÷ 期間內累積的股票股利與分割因子（以除權參考價比例計算）；每期 1%／99% 截尾；全部產業（金融股另報）。
- 主檢定 (1)：產業內 Spearman IC(−NSI, 之後 20／60 日報酬)，月份平均與 t 值（60 日用 Newey-West 調整重疊）。
- 主檢定 (2)：Fama-MacBeth，控制資產成長 AG、SUE、log 市值、過去 12-1 月報酬、產業固定效果，報告 NSI 係數。
- 可交易版本 (3)：(a) 單獨等權多空（產業內前／後 30%，借券條件 D、每 3 個月換倉三份錯開、台指期對沖，成本單邊 0.29625%＋借券費）；(b) 與 fv5 合成：2/3 SUE 排名＋1/3（−NSI）排名，與 fv5（1.45 / 1.87，全期 1.64）比較。
- 通過標準：(1) 主樣本 20 日 IC 兩段 > 0、全期 t > 2；(2) Fama-MacBeth 控制 AG 後全期 t > 2；(3) 驗證樣本同號；(4) (b) 合成版兩段 Sharpe 都不低於 fv5。(1)(2) 不成立就停止，不做 (3)。
- 只報告：只用股數增加（發行端）與只用股數減少（買回端）的分項；NSI 與 AG 的平均橫斷面相關。

## 與已測點子的關係

- 現金增資與可轉債發行公告：董事會決議後的長期落後與 CB 發行期賣壓（card:已測：未通過，research/ideas/I012-seo-cb-issuance-underperformance.md）：命中 可轉債, equity issuance
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 外資台指期／台指選擇權淨部位擇時（failed，docs/fut_inst_timing_report.md）：命中 market timing
- 資產成長（投資）異常（failed，docs/asset_growth_report.md）：命中 資產成長
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 現金增資與可轉債發行公告（failed，docs/corp_events_report.md）：命中 可轉債
- 庫藏股買回（failed，docs/event_study_report.md）：命中 庫藏股
- 均線擇時（0050）（failed，docs/timing_oos_report.md）：命中 market timing
- 外資台指期／台指選擇權淨部位：大盤擇時（台指期執行）（card:已測：未通過，research/ideas/I013-foreign-futures-options-positions-timing.md）：命中 market timing
- 台指選擇權 Put/Call 比（成交量與未平倉）：逆向情緒擇時（card:已測：未通過（接近，建議前瞻記錄），research/ideas/I014-txo-put-call-ratio-timing.md）：命中 market timing
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE
- 資產成長（投資）異常：總資產年增率高的股票之後報酬較低（card:已測：未通過，research/ideas/I020-asset-growth.md）：命中 資產成長
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:待確認，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 補充：與 I012 現金增資／可轉債（失敗）的差別：I012 是公告日事件，本卡是 12 個月累積的連續股數變化，含轉換、員工股與註銷。與資產成長（失敗）同屬投資／融資類因子，相關性預期為正，所以必須控制 AG；若 IC 在前 500 名同樣接近 0，就可確認本專案『經典因子在大型股失效』的結論，不必再測其他同族因子。

研究點子，非投資建議。
