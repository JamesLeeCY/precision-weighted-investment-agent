# 台股特有 alpha／異常現象：文獻研究

| | |
|---|---|
| 日期 | 2026-10-12 |
| 方法 | 網路文獻研究（學術期刊、台灣期刊、碩士論文、業者文章）；只做研究，沒有回測 |
| 可信度 | 很多台灣證據來自**碩士論文**（未經同儕審查），逐項標出；「僅搜尋摘要」表示原文頁面未能開啟核對 |

## 整體判斷

- 台灣特有、證據最紮實的有三類：**月營收**、**法人與信用交易的籌碼**、**彩券型股票（漲停觸及率／MAX）**。
- 指數成分股調整的證據也不錯，但屬於事件型、次數少。
- 時序異常（假日、除息）多為市場層級且在衰減，不適合產業中性的橫斷面策略。
- 成本門檻：20 日持有、每期全換手時，每月多空價差需超過約 0.6% 才有淨利 → 低換手或事件驅動的訊號較有利。

## 建議測試順序

| 排序 | 策略 | 主要證據 | 與本專案的關係 | 資料（FinMind） |
|---|---|---|---|---|
| 1 | **月營收未預期成分（SUE 式），以公告日計時** | 顧廣平 2010、2016（管理學報）：未預期營收最高 20% − 最低 20%，持有 1–12 個月顯著，25–36 個月反轉；陳柔君等 2022（管理學報）：未預期月營收、季營收、季盈餘各自獨立解釋報酬 | 目前財報 Agent 用的是營收 YoY 與加速度；改成「(本月 − 去年同月) ÷ 過去 YoY 變動的標準差」、進場對齊每月 10 日公告後 | MonthRevenue（免費） |
| 2 | **投信淨買超（依股本或成交量標準化），持有 6–15 日** | 邱崇宇 2025（政大碩論，2015–2025）：前一日投信淨買超 Top5、持有 11 日扣成本後勝大盤，持有 < 5 日被成本吃掉；Hung, Lu & Lee 2024：基金集體買進後延續、集體賣出後反轉 → 只用買方 | 投信偏好中小型股，前百大可能變弱；要改成產業內 z 分數 | InstitutionalInvestorsBuySell（逐檔免費） |
| 3 | **空方資訊：融券流量、借券賣出、券資比（月頻）** | Lin, Ho & Ko 2023（Pacific-Basin Finance Journal）：融券流量顯著預測負報酬；Ting, Lu & Chou 2018（經濟論文）：散戶融資買進後報酬為負；陳姿羽 2020（淡江碩論）：低券資比報酬較高，多頭期不顯著 | 月頻、低換手，符合 20 日持有 | MarginPurchaseShortSale、SecuritiesLending（逐檔免費） |
| 4 | **彩券型股票迴避：漲停觸及率／MAX／低波動** | Wang & Lien 2022（RQFA）、2023（NAJEF）：漲停觸及率高後續報酬低；Lin 等 2017（PBFJ） | 效果以小型股為主，前百大較適合當負向濾網 | Price（免費，自算 ±10% 漲跌停） |
| 5 | 外資持股比率變化／持續淨買超 | 證據偏舊偏弱（多在 2014 年前）；Huang 等 2021（J. Financial Markets）：外資下單失衡的波動度預測月報酬 | 外資偏好大型股，最符合本專案股票池 | 法人買賣、Shareholding（逐檔免費） |
| 6 | 指數成分股調整（MSCI、0050、高股息 ETF） | Shu, Yeh & Huang 2004：MSCI 新增股公告窗口 +3.9%、生效日反轉；潘輝煌 2022、吳怡儒 2016（碩論）：生效前後反轉 | 事件少；成分股名單需自建；高股息 ETF 2023 年後的衝擊只有新聞、沒有研究 | 需自建 |
| 7 | 品質、獲利能力、資產成長、應計 | 台灣證據溫和（多為碩論）；國際複製研究中毛利率獲利能力是少數存活的因子 | 可併入現有財報合成分數，換手低 | 財報三表（免費） |

**不建議優先**：節前／農曆年效應（逐年遞減、市場層級）、除息（2018 稅改後無顯著變化）、注意股／處置股
（只有公告後 3 日、處置資料付費）、當沖強度（沒有橫斷面證據）、董監質押（只有崩跌風險研究）、庫藏股（結論矛盾）。

## 風險與注意

- 月營收：前百大電子股的事件研究（周子安 2016，碩論）發現公告前 5 日已有異常報酬，可吃到的 drift 可能變小；
  Lu & Xin 2024 顯示月營收稀釋了季報的資訊量；2019 年後是否衰減，沒有找到文獻。
- 投信：季底作帳只有業者文章，沒有學術證據，且有「結帳股」反轉，不建議單獨使用。
- 文獻大多沒有扣交易成本；本專案需以扣成本、產業中性、2019–2022 樣本外的標準重新檢驗。

## FinMind 資料取得（官方文件逐項核對，建議實測確認）

- 免費：Price、PER、DayTrading、TotalReturnIndex、MonthRevenue、財報三表、Dividend、DividendResult、Delisting。
- **逐檔查詢免費、依日期一次抓全市場須付費**：MarginPurchaseShortSale、InstitutionalInvestorsBuySell、Shareholding、SecuritiesLending
  （本專案的總經／籌碼 Agent 已逐檔使用其中幾項，與此一致）。
- 付費：PriceAdj、PriceLimit、Suspended、MarketValue、HoldingSharesPer（股權分散表）、DispositionSecuritiesPeriod、TradingDailyReport（分點）。

## 來源

月營收
- Lu & Xin 2024, TIJA: https://ideas.repec.org/a/wsi/tijaxx/v59y2024i01ns1094406024500021.html
- 陳柔君、劉炎瑞、蕭朝興 2022，管理學報：https://lawdata.com.tw/tw/detail.aspx?no=484826
- 顧廣平 2010：https://lawdata.com.tw/tw/detail.aspx?no=246130
- 顧廣平 2016：https://lawdata.com.tw/tw/detail.aspx?no=309423
- 周子安 2016（碩論）：https://www.airitilibrary.com/Publication/Index/U0023-1303201714243478
- 蔡彥卿 2001（台大）：https://scholars.lib.ntu.edu.tw/entities/publication/a2b10d01-ce5f-4866-9ea9-fbbbc99f7e5e

法人籌碼
- 邱崇宇 2025（政大碩論）：https://ah.lib.nccu.edu.tw/item?item_id=178117
- 台大碩論，外資與投信 2001–2014（僅搜尋摘要）：https://tdr.lib.ntu.edu.tw/handle/123456789/19442
- Hung, Lu & Lee 2024：https://ideas.repec.org/h/wsi/wschap/9789811269943_0023.html
- Huang 等 2021, JFM：https://ideas.repec.org/a/eee/finmar/v52y2021ics138641812030015x.html
- 外資羊群 2012, RQFA（僅搜尋摘要）：https://ideas.repec.org/a/kap/rqfnac/v39y2012i2p189-208.html
- Barber, Lee, Liu & Odean 2009, RFS：https://ideas.repec.org/a/oup/rfinst/v22y2009i2p609-632.html
- CMoney 投信作帳（業者文章）：https://www.cmoney.tw/notes/note-detail.aspx?nid=11966

信用交易與放空
- Lin, Ho & Ko 2023, PBFJ：https://ideas.repec.org/a/eee/pacfin/v77y2023ics0927538x22001111.html
- Ting, Lu & Chou 2018：https://pure.lib.cgu.edu.tw/en/publications/margin-trading-differences-of-opinion-and-stock-returns/
- 陳姿羽 2020（淡江碩論）：https://etds.lib.tku.edu.tw/ETDS/Home/Detail/U0002-2806202013545200

彩券型與低波動
- Wang & Lien 2022, RQFA：https://ideas.repec.org/a/kap/rqfnac/v59y2022i2d10.1007_s11156-022-01051-1.html
- Wang & Lien 2023, NAJEF：https://ideas.repec.org/a/eee/ecofin/v67y2023ics106294082300027x.html
- Lin 等 2017, PBFJ：https://ideas.repec.org/a/eee/pacfin/v41y2017icp26-45.html
- 低波動異常碩論（僅搜尋摘要）：https://thesis.lib.nccu.edu.tw/detail/ecbbb1d19b283c677ab4ed946692b359/

指數成分股調整
- Shu, Yeh & Huang 2004, RPBFMP：https://ideas.repec.org/a/wsi/rpbfmp/v07y2004i04ns021909150400024x.html
- 潘輝煌 2022（淡江碩論）：https://www.airitilibrary.com/Article/Detail/U0002-0406202223570500
- 吳怡儒 2016（政大碩論，僅搜尋摘要）：https://thesis.lib.nccu.edu.tw/detail/242010965f40227907b19fb719d703f4/
- 高股息 ETF 換股（新聞）：https://www.cw.com.tw/article/5130307

時序、事件與基本面
- Yang & Lee 2016, Cogent：https://ideas.repec.org/a/taf/oaefxx/v4y2016i1p1177153.html
- 除息與 2018 稅改（台大碩論，僅搜尋摘要）：https://tdr.lib.ntu.edu.tw/handle/123456789/60894
- 注意股與處置股（台大碩論，僅搜尋摘要）：https://tdr.lib.ntu.edu.tw/handle/123456789/84175
- 庫藏股（僅搜尋摘要）：https://ijoi-online.org/index.php/back-issues-11-20/17-vol-12-num-2-october-2019/182-an-empirical-study-of-share-repurchase-evidence-from-taiwan-stock-market
- 董監質押與崩跌風險（僅搜尋摘要）：https://tdr.lib.ntu.edu.tw/handle/123456789/20769
- 資產成長（僅搜尋摘要）：https://tdr.lib.ntu.edu.tw/handle/123456789/43350
- 應計（僅搜尋摘要）：https://lawdata.com.tw/tw/detail.aspx?no=246052

FinMind
- https://finmind.github.io/tutor/TaiwanMarket/Chip/
- https://finmind.github.io/tutor/TaiwanMarket/Technical/
- https://finmind.github.io/tutor/TaiwanMarket/Fundamental/

未能核實：節前效應 1971–2011 研究的刊物與作者（頁面 404）；交大 CMR 29(1) PDF 無法解析。
