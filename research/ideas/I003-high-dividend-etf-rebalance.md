# I003 高股息 ETF 換股（0056／00878／00919 等）公告後的價格壓力與生效後反轉

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 事件研究 | free（TIP 公告）＋manual（0056、00878 異動與 ETF 規模） | 約 0（價格已快取）；TIP 公告 PDF 約 100–200 次網站請求 | 2026-10-14 |

## 假設

大型高股息 ETF 公告換股後，預估被動買進金額相對該股 20 日平均成交金額越大的納入股，從公告日 +1 到生效日的異常報酬越高；生效後 1–20 日異常報酬為負（刪除股則相反）。

## 機制（為什麼會有超額報酬）

2023 年後高股息 ETF 規模暴增（新聞報導 00878 超過 6 千億元、00919 超過 4 千億元），其標的多為中型股，換股需求可達數日成交量；選股依殖利率等公開規則、公告到生效有固定間隔，造成可預期且對價格不敏感的資金流。流動性提供者先買後賣給 ETF，生效後價格回落。

## 出處

- （同儕審查，外國市場）Reaksi Pasar pada Peristiwa Rebalancing Indeks MSCI di Negara ASEAN-5（2023），Jurnal Kajian Akuntansi，https://doi.org/10.33603/jka.v7i1.7217：MSCI 調整公告後，被納入股有異常報酬、成交量增加，刪除股相反
- （同儕審查）Price and Volume Effects Associated with Index Additions: Evidence from the Indian Stock Market（2011），https://doi.org/10.5296/ajfa.v2i2.469：Nifty 納入有正且持久的異常報酬，作者認為不支持純價格壓力解釋（反例，需要檢定反轉是否存在）
- （工作論文）Who Trades Index Rebalancings? Evidence on Benchmarking and International Portfolio Flows（2026），SSRN，https://doi.org/10.2139/ssrn.7565249：只讀到標題
- （官方公告）臺灣指數公司技術公告 API，https://backend.taiwanindex.com.tw/api/downloads/technical_notices：00919 追蹤的 TIP Customized Taiwan Select High Dividend Index 自 2022-12 起 13 則審核結果，另有十多個 TIP 高股息指數的審核 PDF（列出 Inclusions／Exclusions）
- （新聞）自由時報：長榮被踢出高股息指數、月底前恐有賣壓，https://ec.ltn.com.tw/article/breakingnews/4321693
- （論壇，只當假設來源）PTT〈00919逾4164億規模換股！8進8出〉https://www.ptt.cc/bbs/Stock/M.1765877404.A.A95.html 、〈00878成分股調整生效！3進3出〉https://www.ptt.cc/bbs/Stock/M.1748935243.A.FE4.html

## 台股適用性

現象本身是台股特有（高股息 ETF 散戶資金規模全球少見），沒有找到學術實證。有效樣本多在 2023 年後，2019–2022 段事件少且 ETF 規模小，兩段驗證可能做不到，需改用『依資金衝擊大小分組』做內部驗證。0056 依 FTSE TWSE 高股息規則（6／12 月），00878 依 MSCI 規則（5／11 月），00919 依 TIP 規則（5／12 月），日期各自不同；同一檔股票可能同時被多檔 ETF 納入或刪除，需加總淨流量。

## 所需資料

- TIP 技術公告 API＋PDF（免費）：00919 與其他 TIP 高股息指數的納入／刪除；PDF 需文字擷取（目前 .venv 沒有 pypdf，要另裝或用其他方式）
- 0056、00878 的歷史異動：新聞與 PTT 每季整理文，手動估 3–4 小時
- 各 ETF 公告前規模：投信官網或 TWSE ETF 資料（未驗證歷史可得性），用來估『預估買進金額＝規模 × 新權重』
- FinMind TaiwanStockPrice（已快取）：成交金額，算資金衝擊＝預估買進金額 ÷ 20 日平均成交金額

## 檢定計畫（看結果前固定）

- 樣本：2021-01 至 2026-04 的 0056、00878、00919 審核（加上規模 ≥ 500 億元的其他 TIP 高股息 ETF 為延伸樣本）；2026-05 以後不用
- 事件：公告日（盤後公告則以 +1 日為第一個可交易日）；同股同期多檔 ETF 的流量相加，淨買進為納入事件、淨賣出為刪除事件
- 訊號：資金衝擊＝預估淨流量 ÷ 公告前 20 日平均成交金額；依中位數分高／低兩組
- 視窗：W2 公告日 +1 收盤 → 生效日收盤；W3 生效日 +1 → +20
- 異常報酬：相對同產業等權報酬；t 用事件日曆分群
- 成本：來回約 0.6%；刪除事件放空需可借量，否則只檢定做多納入與『生效後不追高』的濾網用途
- 通過標準：高衝擊組 W2 淨 CAR > 0 且 t > 2，且高衝擊組 − 低衝擊組 > 0；W3 若 < −1% 且 t > 2，記為反轉規則。只有一段樣本時，另以 0056（較早期）與 00878／00919（較晚）分開確認方向一致

## 與已測點子的關係

- 臺灣50（0050）季度換股：用市值排名事前預測納入／刪除（card:待確認，research/ideas/I001-tw50-rebalance-predicted.md）：命中 成分股調整, 換股, price pressure
- MSCI 季度調整：台股標準指數納入／刪除的公告到生效效果（card:待確認，research/ideas/I002-msci-taiwan-rebalance.md）：命中 成分股調整, price pressure
- 月營收依公告日提早進場（failed，docs/sue_event_entry_report.md）：命中 公告日
- 1 個月反轉、5 日反轉、殘差反轉（failed，docs/reversal_signals_report.md）：命中 反轉
- 補充：與已測的『除息後偏弱（高殖利率）』都涉及高殖利率股，但機制不同（換股資金流 vs 除息）；檢定時應排除換股生效日與除息日重疊的事件，或控制殖利率。

研究點子，非投資建議。
