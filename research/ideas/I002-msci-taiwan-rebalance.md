# I002 MSCI 季度調整：台股標準指數納入／刪除的公告到生效效果

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：勉強通過（候選） | B | 事件研究 | free | FinMind 約 0（價格、外資持股已快取）；證交所網站約 40 次（8 年列表＋約 31 篇新聞稿內文） | 2026-10-14 |

## 假設

MSCI 季度調整公告後，台股被納入 MSCI 標準指數的股票從公告日 +1 到生效日（2／5／8／11 月最後交易日）收盤有正的異常報酬，刪除股為負，生效後 1–20 日部分反轉。

## 機制（為什麼會有超額報酬）

追蹤 MSCI 新興市場／全球指數的被動外資必須在生效日收盤調整持股，屬價格不敏感的大額流量；台股為 MSCI 新興市場最大權重市場之一，流量相對個股成交量可觀。外資持股比例上限與交割限制也會放大短期壓力。

## 出處

- （同儕審查）Stock Return Response to Changes in MSCI Standard and Small Cap Index Composition for Turkey（2023），Journal of Yaşar University，https://doi.org/10.19168/jyasar.1151230：以事件研究分析 MSCI 標準與小型指數在公告日與生效日的價格效果（摘要未給數字）
- （同儕審查）Reaksi Pasar pada Peristiwa Rebalancing Indeks MSCI di Negara ASEAN-5（2023），https://doi.org/10.33603/jka.v7i1.7217：2017–2021 東協五國，納入股公告後有異常報酬與成交量增加
- （同儕審查）Market Reaction of the Indonesian Banking Sector to the Announcement of MSCI Index Rebalancing Suspension（2026），https://doi.org/10.47747/ijbme.v7i2.3457：反例，印尼銀行股對暫停調整公告無顯著反應
- （官方新聞稿）證交所新聞列表 API（https://www.twse.com.tw/rwd/zh/news/newsList?response=json&startDate=YYYY0101&endDate=YYYY1231）：每季發布『MSCI 指數臺股權重調整結果』，2019 年起每季都有
- （論壇／新聞，只當假設來源）PTT〈台股｜MSCI季調生效　台積電尾盤急拉〉https://www.ptt.cc/bbs/Stock/M.1653975928.A.12D.html ；〈MSCI季調受惠股出列 先進光漲停〉https://www.ptt.cc/bbs/Stock/M.1691727361.A.FD6.html

## 台股適用性

沒有找到台股 MSCI 調整的學術實證（lit 只找到土耳其、東協、印尼）。台股每季標準指數增刪通常 0–6 檔，8 年約 30 次調整、估 60–120 個事件，樣本不大。外資持股資料（TaiwanStockShareholding，已快取）可用來確認生效日外資持股是否真的變化。生效日收盤常見尾盤大量，收盤進出可能有額外衝擊成本。

## 所需資料

- 證交所新聞稿：每季 MSCI 臺股權重調整結果（納入、刪除、生效日），2019 年起，需解析新聞稿內文（zhId 對應內文頁，格式未驗證）
- FinMind TaiwanStockPrice（已快取）：日報酬
- FinMind TaiwanStockShareholding（已快取）：外資持股比例，驗證生效日的流量方向
- MSCI 小型指數的增刪也在新聞稿中，可作為延伸樣本（較小型股、衝擊相對更大）

## 檢定計畫（看結果前固定）

- 樣本：2019-02 至 2026-02 的 29 次季度調整，台股標準指數納入與刪除；小型指數另列；分 2019–2022 與 2023–2026/04 兩段；2026-05 以後不用
- 事件日：公告日（台灣時間清晨公布，當日即可交易，進場用公告日收盤）；生效日＝調整月最後交易日收盤
- 視窗：W0 公告前 −20 → −1（檢查是否已被搶先）；W2 公告日收盤 → 生效日收盤；W3 生效日 +1 → +20
- 異常報酬：相對市值前 300 檔等權報酬，另做同產業配對；t 用事件日曆分群
- 成本：來回約 0.6%；刪除股放空需可借量
- 檢查：公告日漲停的事件另列；生效日外資持股變化方向是否與預期一致
- 通過標準：納入股 W2 淨 CAR 在兩段皆 > 0 且 t > 2（若事件數 < 30 則要求合併 t > 2.5 且兩段同號）；W3 反轉 < −1% 且 t > 2 則記為反轉規則

## 與已測點子的關係

- 臺灣50（0050）季度換股：用市值排名事前預測納入／刪除（card:待確認，research/ideas/I001-tw50-rebalance-predicted.md）：命中 成分股調整, 指數納入, index inclusion, price pressure
- 月營收依公告日提早進場（failed，docs/sue_event_entry_report.md）：命中 公告日
- 投信買超、外資持股變化（failed，docs/leg_pool_report.md）：命中 外資
- 1 個月反轉、5 日反轉、殘差反轉（failed，docs/reversal_signals_report.md）：命中 反轉
- 補充：與已測的『投信買超、外資持股變化』不同：此處是公告的制度性流量事件，不是持股變化訊號；可與臺灣50卡共用同一套事件研究程式。

研究點子，非投資建議。

## 結果（2026-10-15）

已測：勉強通過（候選），見 [docs/index_rebalance_report.md](../../docs/index_rebalance_report.md)。
