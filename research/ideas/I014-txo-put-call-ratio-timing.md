# I014 台指選擇權 Put/Call 比（成交量與未平倉）：逆向情緒擇時

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | C | 擇時（台指期執行）＋預測迴歸 | free（已快取，0 次請求） | 約 0（FinMind 0 次；期交所 pcRatio 驗證約 2 次） | 2026-10-16 |

## 假設

台指選擇權 Put/Call 比（未平倉或成交量）相對過去一年偏高（市場恐慌、避險需求高）時，加權指數之後 20 日報酬較高；依此調整淨曝險的規則，在樣本外（2016 ~ 2026/04 與逐年滾動前進）勝過同平均曝險的固定比例，且在控制台指 VIX 後仍有預測力。

## 機制（為什麼會有超額報酬）

情緒與避險需求：Put/Call 比高代表投資人大量買進賣權避險或看空，逆向觀點認為此時悲觀已反映在價格中。反方向的解讀是資訊交易（Pan & Poteshman 2006）：看空者用賣權交易，高 Put/Call 比之後報酬較低。但 Pan & Poteshman 指出預測力來自非公開的資訊成分，公開可見的部分弱；本卡只能用公開的全市場 Put/Call 比，所以機制模糊，事前同時列出兩個方向，並以兩個方向都計入多重比較。

## 出處

- Pan & Poteshman (2006) The Information in Option Volume for Future Stock Prices, Review of Financial Studies 19(3):871–908, https://ideas.repec.org/a/oup/rfinst/v19y2006i3p871-908.html：以「買方新倉」成交量算個股 Put/Call 比，低比值股次日風險調整後報酬高約 0.4%、次週高 1% 以上（低 vs 高組）；預測力來自非公開資訊（摘要）【同儕審查】
- Chiu, Lee & Wang (2014) Have Domestic Institutional Investors Become as Market Savvy as Foreign Investors? Evidence from the Taiwan Options Market, Journal of Derivatives 21(4), https://doi.org/10.3905/jod.2014.21.4.063：依交易人身分的台指選擇權 Put/Call 比，近期本國法人的比值對每日加權指數報酬有預測力（摘要）【同儕審查】
- 期交所 臺指選擇權 Put/Call Ratios 統計表，https://www.taifex.com.tw/cht/3/pcRatio：每日公布全市場賣權／買權成交量與未平倉量及比率，週契約與月契約合併計算【官方網站】
- 本專案 docs/vix_timing_report.md：台指 VIX 的恐慌加碼（A1）扣成本前相對同平均持股約 −0.8%／年（t −1.0），擇時資訊接近 0【內部研究】

## 台股適用性

台指選擇權是全球成交最活躍的指數選擇權之一，散戶比重高（Chiu 等 2014 提到約一半口數），情緒指標在台灣可能比美國更明顯。週選擇權 2012-11 才上市，會改變成交量結構，所以主訊號用只含月契約的未平倉比，週契約版本只作參考。

## 所需資料

- FinMind TaiwanOptionDaily TXO（已快取，2007-01-02 ~ 2026-10-14，約 470 萬列，含各履約價的成交量、未平倉、一般與盤後時段）：自算每日 Put/Call 比
- 期交所 pcRatio（https://www.taifex.com.tw/cht/3/pcRatio）：取最近一個月的官方 Put/Call 比，驗證自算值（週＋月合併版本）
- 自算台指 VIX（analysis/txo_vix.py，已有）：作為控制變數
- 0050 含息價、TX 近月（已快取）：沿用 analysis/timing_futures.py 的期貨執行架構

## 檢定計畫（看結果前固定）

- 樣本：2008-01 ~ 2026-04（前一年暖機）；樣本內 2008–2015、樣本外 2016 ~ 2026/04；另做逐年滾動前進（2012 起）。2026-05 以後保留。
- 資料處理：只用一般交易時段（trading_session = position）；主訊號只含月契約（contract_date 為 6 位數）；先比對 2026-09/10 的自算週＋月合併值與期交所官方值，平均絕對差需 < 2 個百分點才進行回測。
- 訊號（事前固定）：P = 月契約賣權未平倉 ÷ 買權未平倉，取 5 日平均，再換成過去 250 日的百分位。副訊號：成交量版本（同樣處理）。
- 規則（只看訊號、一次固定）：逆向版 e = 100%（百分位 ≥ 80%）、60%（≤ 20%）、其餘 80%；順向版（資訊交易解讀）把 100% 與 60% 對調。第 t 日收盤後計算，第 t+1 日一般時段開盤以台指期調整。
- 預測迴歸：加權指數含息報酬（未來 5、20 日）對 P 迴歸，Newey-West（落後 20 期），控制自算 VIX 與過去 20 日報酬。
- 滾動前進：候選 {未平倉, 成交量} × {逆向, 順向} × {5, 20 日平均} = 8 種，每年 1 月用之前資料選 Sharpe 最高者持有一年。
- 對照與成本：同平均曝險的固定比例（期貨，只付轉倉）；期貨部位變動 × 單邊 0.005%，每月轉倉 2 × 放空部位 × 0.005%。
- 通過標準：(1) 主規則（未平倉、逆向、5 日平均）在樣本外 2016 ~ 2026/04 相對同平均曝險固定比例的年化差 > 0 且 t > 2；(2) 樣本內也 > 0；(3) 滾動前進樣本外 > 固定比例；(4) 預測迴歸控制 VIX 後，P 的係數在兩段同號、全期 t > 2。
- 預估請求：FinMind 0 次（全部已快取）；期交所約 2 次。

## 與已測點子的關係

- 均線擇時（0050）（failed，docs/timing_oos_report.md）：命中 擇時, market timing
- 外資台指期／台指選擇權淨部位：大盤擇時（台指期執行）（card:待確認，research/ideas/I013-foreign-futures-options-positions-timing.md）：命中 TXO, market timing
- 1 個月反轉、5 日反轉、殘差反轉（failed，docs/reversal_signals_report.md）：命中 contrarian
- 新聞情緒（含內文）（failed，docs/effective_signals.md）：命中 情緒
- 台指 VIX 擇時與波動率管理（failed，docs/vix_timing_report.md）：命中 vix
- 補充：與已失敗的台指 VIX 擇時同屬選擇權衍生的情緒指標，VIX 扣成本前的擇時資訊就接近 0；Pan & Poteshman 也指出公開可見的 Put/Call 比資訊弱，所以機制與先驗都不佳，列為 C。唯一的優點是資料全部已快取、可做 2008 起的真樣本外，若使用者想用很低成本補上「選擇權籌碼」這一塊，可以順便跑。

研究點子，非投資建議。
