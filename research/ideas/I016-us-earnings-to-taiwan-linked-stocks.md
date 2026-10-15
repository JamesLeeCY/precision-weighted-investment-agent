# I016 美股大型科技公司財報反應對台股連結股的延遲傳遞（客戶／同業財報 → 台灣供應鏈）

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 事件研究（依財報方向調整正負號的高連結 − 低連結，兩組相減）＋配對控制 | free（FinMind 美股價格已試抓確認；SEC EDGAR 已實測；Apple 名單為官方 PDF）；manual（Apple 名單公司名對應台股代號，約 40–60 家） | FinMind 約 9（AAPL、AMD、AVGO、QCOM、INTC、MU、TXN、LRCX、CSCO；NVDA、MSFT、AMZN、GOOGL、META、AMAT、SPY 已快取）；SEC EDGAR 約 15–30（15 家 submissions JSON，必要時加舊檔）；Apple 名單 PDF 約 8（含網頁封存）；台股前 500 名 0；第 501–1000 名驗證若已快取則 0 | 2026-10-16 |

## 假設

美國大型科技公司財報公告後的異常報酬（相對 SPY）為正（負）時，與該公司事前報酬連結度高的台股，在台股第 +2 ~ +21 個交易日的異常報酬，高於（低於）同產業中連結度低的台股；即「依財報反應方向調整正負號後的高連結 − 低連結」差額為正。

## 機制（為什麼會有超額報酬）

有限注意力與跨市場資訊擴散：Cohen & Frazzini（2008）發現客戶的股價消息要過一段時間才反映到供應商；Pandit、Wasley、Zach（2011）發現供應商在客戶財報公告時有股價反應；Albuquerque、Ramadorai、Watugala（2015）發現跨國的客戶國報酬可預測供應國公司報酬。台股投資人對美國單一公司財報細節（指引、資本支出、庫存）的消化可能較慢，且台股開盤時只看得到盤後價格，完整的正式交易反應要到台股下一個交易日開盤前才知道。

## 出處

- Cohen & Frazzini (2008) Economic Links and Predictable Returns, Journal of Finance 63:1977–2011（經 Madsen 2017 摘要引用確認期刊卷頁）：客戶報酬可預測供應商報酬（本次未讀全文，不引用數字）【同儕審查】
- Pandit, Wasley & Zach (2011) Information Externalities along the Supply Chain: The Economic Determinants of Suppliers' Stock Price Reaction to Their Customers' Earnings Announcements, Contemporary Accounting Research, https://doi.org/10.1111/j.1911-3846.2011.01092.x：以供應商在客戶季報公告時的股價反應衡量資訊外溢，並分析其經濟決定因素（摘要）【同儕審查】
- Madsen (2017) Anticipated Earnings Announcements and the Customer-Supplier Anomaly, Journal of Accounting Research, https://doi.org/10.1111/1475-679x.12158：客戶報酬只在供應商自己財報公告前預測供應商報酬，公告後不再預測，顯示注意力在公告前才轉向客戶資訊（摘要）【同儕審查】
- Albuquerque, Ramadorai & Watugala (2015) Trade Credit and Cross-country Predictable Firm Returns, Journal of Financial Economics, https://www.financialresearch.gov/staff-discussion-papers/2014/11/06/trade-credit-and-cross-country-predictable-firm-returns：43 國 1993–2009，客戶國報酬可預測供應國中與其貿易信用連結深的公司報酬，海外銷售比重高者更明顯（摘要）【同儕審查；工作論文版本見網址】
- Hsu（2021）臺師大碩士論文（以 Apple 2014–2018 前 200 大供應商名單中的台灣公司為樣本，VAR 模型）：考慮時差後 Apple 股價與台灣供應商組合報酬正相關，https://etds.lib.ntnu.edu.tw/thesis/detail/062602b7917107ce8b6e1251f9df5173（只讀到搜尋摘要）【學位論文】
- SEC EDGAR submissions API，https://data.sec.gov/submissions/CIK0001045810.json（本次以 NVIDIA 實測）：8-K 有 items 欄位（2.02 = 營運結果）與 acceptanceDateTime（UTC，精確到秒），例如 2026-08-27T00:21:19Z（美東 8/26 20:21，台北 8/27 08:21，台股開盤前）【官方網站，實測】
- Apple Supplier List（官方 PDF，例如 FY2023 https://s203.q4cdn.com/367071867/files/doc_downloads/2024/04/Apple-Supplier-List.pdf、FY2021 https://www.apple.com/au/supplier-responsibility/pdf/Apple-Supplier-List.pdf）：Apple 每年公布占直接採購支出 98% 的供應商；2019、2020 年版本本次未找到原檔，需用網頁封存補【官方網站】

## 台股適用性

台股電子業高度依賴美國客戶，是這類效果最可能出現的市場之一；但也正因為大家都知道，台股開盤時通常已大幅反映美股盤後價格（本專案庫藏股、可轉債等事件都是「隔日開盤即反映」）。時差：美股盤後公告（美東 16:00–16:30）＝台北清晨 04:00–05:30，台股當天開盤只看到盤後價格；美股正式交易的反應要到台北次日清晨才知道。所以本卡的台股第 0 日 = 公告後第一個台股交易日，訊號（美股正式交易日的異常報酬）在台股第 +1 日開盤前已知，第 +1 日收盤進場，視窗 [+2, +21]，與本專案慣例一致。對應關係不用人工挑選的名單：主檢定用事前 250 日報酬估計的連結度（每次事件只用當時資料，涵蓋當時前 500 名全部成員，無存活偏誤）；次要檢定用 Apple 每年官方公布的供應商名單（時點明確）。

## 所需資料

- FinMind USStockPrice（免費，本次試抓 AVGO 2010-01 起與 2026-10 皆可取得；欄位含 Open、Close、Adj_Close）：美股日報酬與 SPY 基準
- SEC EDGAR data.sec.gov/submissions/CIK##########.json：8-K Item 2.02 的申報日期與 acceptanceDateTime，用來判斷盤前或盤後公告（SEC 要求請求標頭帶聯絡資訊，需由使用者提供，不自動填入）
- Apple Supplier List（FY2018 ~ FY2023 等各年度 PDF）：次要檢定的客戶—供應商對應
- 台股含息價格、產業、市值成員、SUE（已快取）：連結度估計、配對控制與 CAR

## 檢定計畫（看結果前固定）

- 美股公司（事前固定 15 家，依 2018 年底已是大型公司的條件挑選，不看 2019 年後表現）：AAPL、MSFT、AMZN、GOOGL、META、NVDA、AMD、AVGO、QCOM、INTC、MU、TXN、AMAT、LRCX、CSCO。財報事件為 8-K Item 2.02，2019-01 ~ 2026-04，約 15 × 4 × 7.3 ≈ 440 次。分兩段 2019–2022、2023–2026/04。
- 財報反應 EAR：美股公司相對 SPY 的異常報酬，取公告後第一個美股正式交易日（盤後公告）或公告當日（盤前公告）的收盤對前一日收盤；以 acceptanceDateTime 判斷。
- 台股時點：第 0 日 = 公告時間之後第一個開盤的台股交易日；第 +1 日開盤前 EAR 已知；第 +1 日收盤進場；主視窗 CAR[+2,+21]（相對加權指數）。另外描述性報告第 0、+1 日的反應幅度，判斷資訊在開盤是否已反映。
- 連結度（主檢定）：對每個事件，用公告前第 271 ~ 第 21 個台股交易日共 250 日，以台股 i 的殘差報酬（減加權指數）對美股公司 c 前一個美股交易日的殘差報酬（減 SPY）迴歸，連結度 = 斜率的 t 值。只用當時市值前 500 名成員；在每個產業（成員 ≥ 6 檔者）內分三組。
- 主統計量：每個事件 D = sign(EAR) ×（高連結組平均 CAR − 低連結組平均 CAR）。兩組都在同產業、同一天，共同的「一般股票落後加權指數」會互相抵消。以事件所在週群集計算標準誤（同週多家公告視為相關）。
- 輔助檢定：(a) 個股層級迴歸 CAR[+2,+21] = a + b·(EAR × 連結度 t 值) + c·EAR + d·連結度 + SUE 與事件前 60 日報酬控制，依週群集；(b) 只取 |EAR| 高於該公司過去 8 次中位數的事件；(c) 次要：Apple 財報事件（約 29 次），Apple 官方名單上的台灣供應商（以名單公布日後才使用）對 corp_event_study.matched 配對股的差額，乘上 sign(EAR)；只報告方向，不列入通過標準。
- 驗證樣本：市值第 501–1000 名，同樣方法。
- 可交易版本：每個事件在第 +1 日收盤，EAR > 0 時做多高連結、放空低連結（EAR < 0 時相反），持有 20 日；單邊成本 0.29625% × 兩腿進出＋借券費（analysis/borrow_capacity.py 條件）；日曆時間組合計算 Sharpe。損益兩平約需 D > 1.2%（每腿買進加賣出約 0.59%，兩腿合計約 1.19%），另加借券費。
- 通過標準：(1) D 的平均在兩段皆 > 0、全期 t > 2；(2) 迴歸中 EAR × 連結度係數全期 t > 2；(3) 驗證樣本方向相同；(4) 可交易版本扣成本後兩段 Sharpe > 0。若第 0、+1 日的反應已占 [0,+21] 總反應的大部分且 (1) 不成立，判定為「開盤即反映」。
- 預估請求：FinMind 約 9 次；SEC EDGAR 約 15–30 次；Apple PDF 約 8 次；其餘已快取。

## 與已測點子的關係

- 產業領先落後、供應鏈（failed，docs/effective_signals.md）：命中 供應鏈, lead-lag, economic links
- 財報 Agent（營收、毛利、存貨、應收）（partial，forward/REPORT.md）：命中 財報
- 補充：與已失敗的「供應鏈 Agent」不同：那是 2026 年人工挑選 5 家被動元件公司與手調權重的知識圖譜，看的是價格與營收水準，IC 來自取樣起點的挑選偏誤；本卡用事件（美股財報）＋事前報酬估計的連結度，涵蓋當時前 500 名全部成員，連結名單不需要事後知識。與已失敗的「產業領先落後」不同：那是台股內大型股過去 5 日報酬對追隨股的預測，經檢查只是短期反轉；本卡是跨市場、以具體資訊事件（財報）為觸發，並用兩組相減排除產業共同走勢。主要風險：台股開盤可能已完全反映（先驗不高），以及 15 家公司財報集中在每季同幾週，獨立觀察數比事件數少很多。

研究點子，非投資建議。
