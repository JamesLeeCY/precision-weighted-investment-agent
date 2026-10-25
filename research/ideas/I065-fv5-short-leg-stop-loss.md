# I065 fv5 空方腿的個股停損（軋空保護）：空單相對 β × 台指期漲幅達 20% 時回補，降低尾端損失

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 濾網或加權（fv5 空方停損規則，與 fv5 建構配對比較，主看尾端風險） | free | 約 0（前 500 名價格、漲跌停價、借券、台指期皆已快取） | 2026-10-25 |

## 假設

fv5 的空單若自建倉後相對 β × 台指期的累積超額報酬達 +20%，在次一個非漲停交易日收盤回補、該份資金到下次換倉前不再放空該股，則 fv5 日報酬的 1% 條件風險值（CVaR）與最大回撤在兩段都改善至少 10%（相對值），而全期年化淨報酬損失不超過 0.20 個百分點。

## 機制（為什麼會有超額報酬）

空方損失沒有上限、報酬右偏；台股有題材股連續漲停、借券召回與融券回補造成的軋空。停損把單一空單的損失截斷，可能降低組合的尾端風險。文獻證據來自動能策略：Han、Zhou、Zhu 用 10% 停損把等權動能最差月損失大幅縮小。支持續漲的本專案證據：前 500 名處置股（急漲被處置）之後 20 日仍有 +5.3% 異常報酬，代表急漲股的空單可能繼續虧。反方：高放空股單日暴漲後傾向反轉（IHS Markit 引述 Xu 與 Liu 2013），本專案也有 1 日短期反轉，停損可能在高點回補；所以主判定看尾端風險，報酬只要求不明顯變差。

## 出處

- （工作論文）Han、Zhou、Zhu（2014 初版，2016 更新）Taming Momentum Crashes: A Simple Stop-Loss Strategy，摘要轉載見 https://www.crossingwallstreet.com/?p=28384 與 Alpha Architect 摘要 https://alphaarchitect.com/taming-the-momentum-roller-coaster-fact-or-fiction/：1926–2011 月資料，10% 停損使等權動能最大月損失由約 −49.8% 降到約 −11.3%（各版本數字略有出入；扣成本前）
- （業界研究）IHS Markit，The long and short of short squeezes，https://cdn.ihsmarkit.com/www/pdf/0521/The_long_and_short_of_short_squeezes.pdf：引述 Xu 與 Liu（2013），高放空股單日價格暴漲後傾向反轉，與大盤、產業同步大漲時軋空較嚴重（依搜尋摘要）
- （本專案）docs/event_study_report.md：前 500 名處置股第 +2 ~ +21 日異常報酬 +5.3%（t 4.4），但第 501–1000 名驗證只剩 +2.8%
- （本專案）docs/short_term_reversal_report.md：1 日短期反轉 IC t 3.4 / 2.4，隔日成交即消失（停損在次日收盤執行，可避開大部分當日反轉）
- （本專案）docs/forced_covering_dividend_tax_report.md：高融券股回補前已多漲 1.8%、回補後 5 日回吐 1.1%（第 501–1000 名）

## 台股適用性

台股 ±10% 漲跌幅讓急漲股常連續漲停，漲停時回補（買進）可能買不到，所以規則要延到第一個非漲停收盤；這也是台股空方尾端特別的地方。借券空單可隨時回補；回補後該部位改為現金，台指期對沖依新的淨 β 調整。沒有找到台股多空因子停損的研究。

## 所需資料

- fv5 回測的每份資金每日空方持股與建倉價（analysis/ls_turnover.py、borrow_capacity 一類）
- FinMind TaiwanStockPrice（已快取）：收盤價與漲停判斷（收盤 ≥ 前日收盤 × 1.095 視為漲停，或用漲停價欄位）
- 台指期近月（已快取）、個股 β（fv5 既有估計）

## 檢定計畫（看結果前固定）

- 樣本：fv5 前 500 名、2019-03 ~ 2026-04，兩段 2019–2022 / 2023–2026/04；2026-05 以後不用。
- 規則 SL20（只有這一個門檻）：每份資金的每檔空單，自建倉日收盤起計算個股報酬減 β × 台指期報酬的累積值；收盤時 ≥ +20% 即觸發，於次一交易日收盤回補；若該日收盤為漲停，順延到第一個非漲停收盤。回補後該部位為現金，到該份資金下次換倉前不再放空該股，台指期依剩餘淨 β 調整。多方與其他空單不變。
- 成本：回補照 fv5 單邊 0.29625%、台指期 0.005%；借券費算到回補日。
- 指標：日報酬 1% CVaR、最大回撤、最差月報酬、偏態、年化淨報酬、Sharpe，分兩段與全期。
- 通過標準：兩段的 1% CVaR 與最大回撤都相對 fv5 改善 ≥ 10%；全期年化淨報酬損失 ≤ 0.20 個百分點；全期 Sharpe ≥ fv5 − 0.05。三項都要成立。
- 只報告：觸發次數、占空方權重比例、被停損個股從回補日到原定平倉日的相對報酬（續漲或反轉）、fv5x 版本、改用 +15% 與 +30% 門檻的結果（不用於判定）。
- 資料窺探：fv5 整體回撤（−6.9%）已知；空方個股的持有期路徑與觸發情形未看過。處置股與 1 日反轉的結果方向相反，所以不用它們設定門檻；20% 為事前選定（約為空方個股 3 個月報酬的 1 個標準差）。
- 未通過即停止，不改門檻或回補時點重測；若通過，只另立前瞻規格與 fv5 平行記錄。

## 與已測點子的關係

- 股東會與除權息前的融券強制回補：高融券股在最後回補日前的價格壓力、其後反轉，以及對 fv5 空方腿的影響（card:以 I058 修訂版取代（已測，未通過），research/ideas/I050-margin-short-forced-covering.md）：命中 軋空, short squeeze
- fv5 空方腿避開融券回補買壓：新空單若在 10 個交易日內遇到停券窗，延到最後回補日收盤再建倉（訊號與名單不變，只改建倉時點）（card:已測：未通過（只在 2023 年後有效），research/ideas/I059-fv5-short-defer-stop-window.md）：命中 fv5, 空方腿
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 外資台指期／台指選擇權淨部位擇時（failed，docs/fut_inst_timing_report.md）：命中 台指期
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 fv5
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- 12-1 動能、持續性動能、frog-in-the-pan（failed，docs/revmom_persist_report.md）：命中 momentum
- MAX／漲停濾網（彩券型股票）（failed，docs/max_rec_robust_report.md）：命中 漲停
- 外資台指期／台指選擇權淨部位：大盤擇時（台指期執行）（card:已測：未通過，research/ideas/I013-foreign-futures-options-positions-timing.md）：命中 台指期
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:已測：未通過，research/ideas/I054-fv5-entry-execution-price.md）：命中 fv5
- fv5 空方腿改以融券為主、借券補足：借券費與強制回補成本的取捨（訊號與名單不變）（card:已測：未通過（保守情境 +0.41%），research/ideas/I056-fv5-short-leg-margin-vs-sbl.md）：命中 空方腿
- 現金股利發放日的再投資買壓（Hartzmark–Solomon 台股版）：大額發放日的加權指數報酬較高，以台指期執行（card:已測：未通過，research/ideas/I060-dividend-payment-reinvestment-pressure.md）：命中 台指期
- fv5 家族的稅後績效與除息日建倉規則：個人投資人股利所得稅與二代健保補充保費下，多方新倉延到除息後是否改善稅後報酬（card:已測：R1 未通過（稅後績效已報告），research/ideas/I061-fv5-after-tax-exdiv-entry.md）：命中 fv5
- 補充：與 I050／I058／I059（融券強制回補的可預期日期買壓）不同：本卡不預測日期，而是對已實現的急漲做停損。與 I034（依組合波動調整總曝險，未做）不同：本卡只動個股空單，不改總曝險。與 MAX／漲停濾網（建倉前排除彩券型股票，未通過）不同：本卡在持有期間處理。與處置股做多（事後發現、驗證未過）不同：本卡不做多急漲股，只回補空單。

研究點子，非投資建議。
