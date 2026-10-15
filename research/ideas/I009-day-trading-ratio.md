# I009 當沖比（散戶短線投機與注意力）：當沖成交占比高或突然升高的股票之後報酬較差

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 橫斷面 IC（leg_probe 腿格式）＋等權多空（可借條件 D）＋與 SUE 合成 | free | FinMind TaiwanStockDayTrading 每檔一次可取 2014-01 至今全歷史：前 500 名約 776 次、第 501–1000 名約 1,000 次（不重複股票數，需以成員檔確認），合計約 1,800 次（免費每小時 600 次，約 3 小時，可分批）；價格、市值、借券、月營收前 500 名已快取，第 501–1000 名若 I007 已抓則約 0，否則月營收約 580 次 | 2026-10-15 |

## 假設

在市值前 500 名中，過去 20 個交易日平均當沖比（當沖成交股數 ÷ 總成交股數）較高的股票，經產業內標準化並對產業與 log 市值取殘差後，之後 20 個交易日的產業內報酬排名較低（主腿 dt20 = −當沖比，產業內 IC > 0）；次要腿：當沖比相對自身過去 120 日突然升高（dtjump = −(20 日平均 − 120 日平均)）之後同樣較差。

## 機制（為什麼會有超額報酬）

行為偏誤＋套利限制：當沖客絕大多數是散戶，且在台灣的帳戶資料裡整體是虧損的（Barber, Lee, Liu & Odean 2009/2014；Barber 等 2020），他們偏好注意力集中、波動大的股票（Barber & Odean 2008 的注意力驅動買進）。當沖集中代表短線投機需求與注意力推高的價格，之後回落（與 Robinhood 擁擠買進後報酬偏差、彩券型股票過度定價同一族的機制）。台股特有：2017-04-28 當沖證交稅由 0.3% 減半為 0.15%（之後多次延長），當沖比由全市場約一成多上升到 2021 年單日超過五成，訊號的變異在 2019 年後更大。反方：(1) 當沖本身當日平倉，不留下淨部位，價格壓力可能在日內就消化，不一定延續到 20 日；(2) 當沖比與周轉率、異常成交量、波動、MAX 高度相關，而這些在本專案前 300／500 名都已失敗，當沖比可能只是它們的代理；(3) 當沖量大也可能是流動性好、資訊多的股票。

## 出處

- （同儕審查，台灣）Barber, Lee, Liu & Odean（2009）Just How Much Do Individual Investors Lose by Trading?，Review of Financial Studies，https://doi.org/10.1093/rfs/hhn046：用台灣證交所全市場帳戶資料，散戶的交易整體虧損，損失規模可觀（只核對書目與常見引述，未讀全文數字）
- （同儕審查，台灣）Barber, Lee, Liu & Odean（2014）The cross-section of speculator skill: Evidence from day trading，Journal of Financial Markets，https://doi.org/10.1016/j.finmar.2013.05.006（IDEAS：https://ideas.repec.org/a/eee/finmar/v18y2014icp1-24.html）：1992–2006 台灣當沖客中，能在扣費後穩定賺錢的不到 1%；前一年績效最好的 500 人扣費前每日約 61 bps（搜尋摘要所述）。這是『交易者』層級的證據，不是『股票』層級的報酬可預測性
- （同儕審查，台灣）Barber, Lee, Liu, Odean & Zhang（2020）Learning, Fast or Slow，Review of Asset Pricing Studies，https://doi.org/10.1093/rapstu/raz006：摘要指出台灣當沖客整體績效為負、74% 的當沖量來自有虧損紀錄的人、97% 未來可能虧損——支持『當沖量主要來自不具資訊的投機者』
- （同儕審查）Barber & Odean（2008）All That Glitters: The Effect of Attention and News on the Buying Behavior of Individual and Institutional Investors，Review of Financial Studies，https://doi.org/10.1093/rfs/hhm079：散戶是吸引注意力股票（新聞、異常成交量、極端報酬）的淨買方（只核對書目）
- （同儕審查）Barber, Huang, Odean & Schwarz（2022）Attention-Induced Trading and Returns: Evidence from Robinhood Users，Journal of Finance，https://doi.org/10.1111/jofi.13183：散戶擁擠買進的股票之後報酬為負（只讀到二手摘要，未確認數字）
- （工作論文）Bali, Hirshleifer, Peng & Tang（2021）Attention, Social Interaction, and Investor Attraction to Lottery Stocks，NBER w29543，https://www.nber.org/papers/w29543：散戶主導的股票中，彩券效應隨注意力與社群互動增強
- （工作論文／學位論文，台灣）當沖降稅研究：政大學位論文（2022）以 340 檔 2016–2018 差異中差異，降稅提高當沖量值、波動上升，https://thesis.lib.nccu.edu.tw/detail/d6b5977b5822f40753519b1a130b93a5/；會計評論相關研究（30 檔最活躍股票）https://nccur.lib.nccu.edu.tw/handle/140.119/132544；Chicago Booth Review 報導 Chen & Lin 的帳戶研究，降稅後當沖帳戶交易量約 +30%、中小帳戶報酬變差，https://www.chicagobooth.edu/review/high-price-cheaper-stock-trades（皆只讀摘要或報導）
- （本專案，反方證據）docs/leg_pool_report.md：abvol60（異常成交量）與 amihud20 在前 300 名多空 Sharpe 分別 −1.51 / −0.78 與 −1.24 / −0.63；docs/max_rec_robust_report.md：−MAX 產業內 20 日 IC +0.024（t 1.3）/ −0.007（t −0.4），做多排除 MAX 前 20% 使 SUE 變差
- （新聞，只當背景）中央社 2021-05-20 全市場當沖比首度破 50%，https://www.cna.com.tw/news/afe/202105200394.aspx；證交所稱 2021 年 1–4 月約 33.85%，https://www.cna.com.tw/news/afe/202105110316.aspx
- （論壇）PTT Stock『當沖』相關文章大量為新聞與個人心得（例：https://www.ptt.cc/bbs/Stock/M.1780654361.A.8F7.html 每日當沖戶數新高），只說明散戶參與度，不是報酬證據
- 文獻缺口：WebSearch 與 OpenAlex 都沒找到『個股當沖比預測橫斷面報酬』的同儕審查研究；本卡的股票層級假設是由上述交易者層級證據推論而來

## 台股適用性

台股特有、資料完整：證交所與櫃買每天公布每檔股票的當沖成交股數與買賣金額，這在美股沒有公開對應資料，所以文獻只能用帳戶資料研究當沖客，本卡可以直接用股票層級的當沖比。制度變化：2014-01-06 開放現股當沖（先買後賣），之後開放先賣後買；2017-04-28 當沖證交稅減半為 0.15%，並一再延長；處置股、全額交割股不能當沖（處置期間當沖比會掉到接近 0，必須處理），證交所會對部分股票『暫停現股賣出後現款買進當沖』（FinMind 欄位 BuyAfterSale：'Y'／'＊'）。當沖比在 2021 年的全市場熱潮中大幅上升，所以要用產業內排名與自身歷史比較，不能用絕對水準。漲跌停 ±10%：當沖比高的股票常伴隨漲停，第 +1 日漲停買不到的比例要報告（但本訊號是做空高當沖比、做多低當沖比，主要影響空方）。

## 所需資料

- FinMind TaiwanStockDayTrading（本次查證：免費、逐檔查詢可用；不帶 data_id 的全市場單日查詢回 HTTP 400『Your level is free』）：欄位 stock_id、date、BuyAfterSale（暫停先賣後買註記，'Y' 或 '＊'）、Volume（當沖成交股數）、BuyAmount、SellAmount（當沖買進／賣出金額，元）。起點：2330、8069 皆為 2014-01-06，6187 為 2015-06-01（上櫃日），每年約 240–247 列；6187 在 2024 年只有 150 列，表示有缺日（可能是處置或暫停，需檢查）
- 查證：2330 在 2024-03-15 的 FinMind Volume = 7,858,000 股，與證交所 TWTB4U 完全相同；同日總成交 80,580,846 股，當沖比約 9.8%（2024-03-11 ~ 15 為 9.8%–24.8%）
- 證交所『當日沖銷交易標的及成交量值』（免費 JSON）：https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U?date=YYYYMMDD&selectType=All&response=json ，每天一次請求可取全部上市標的（2024-03-15 共 1,067 列，含 ETF）與全市場統計（當沖股數占比 17.49%）；2014-01-06 起有資料（當日全市場占比 0.36%）。只有上市，上櫃需另查櫃買中心；整段 2014–2026 約 3,000 次，比 FinMind 逐檔貴，只當備援與抽查
- FinMind TaiwanStockPrice（已快取）：Trading_Volume、Trading_money 作分母；還原含息報酬、β（leg_probe.load_stock）
- data_cache/events/disposition.csv（已有）：處置期間標記，處置期間當沖比設為缺值
- config/universe_mcap_membership.csv：前 500／第 501–1000 名、產業
- FinMind TaiwanStockSecuritiesLending、TaiwanDailyShortSaleBalances（已快取）：可借條件 D 與借券費；TaiwanFuturesDaily：台指期對沖

## 檢定計畫（看結果前固定）

- 樣本：每年市值前 500 名（config/universe_mcap_membership.csv）為主樣本、第 501–1000 名為獨立驗證；兩段 2019–2022 / 2023–2026/04；2026-05 以後保留給前瞻。排除 ETF、全額交割股；處置期間（data_cache/events/disposition.csv 的處置起迄）與『當日無當沖資料』的股票日，當沖比設為缺值，不當成 0。
- 訊號（看結果前固定，只用 t−1 日以前資料）：每日當沖比 DTR = 當沖成交股數（TaiwanStockDayTrading.Volume）÷ 總成交股數（TaiwanStockPrice.Trading_Volume）；主腿 dt20 = −（過去 20 個交易日 DTR 平均，至少 15 天有值）；次要腿 dtjump = −（DTR 20 日平均 − DTR 120 日平均，至少 80 天）。只測這兩條腿，不另試其他視窗。
- 標準包裝（同 leg_probe.wrap／neutralize）：產業內 z 分數 → 20 日平均（dt20 本身已平均，仍照標準包裝）→ 換倉日對產業虛擬變數與 log 市值迴歸取殘差。換倉日 = 每月營收公告期限後的下一個交易日（data/revenue_signal.event_dates）。
- IC：每個換倉日的產業內 Spearman（訊號 vs 之後 20 個交易日報酬；另報告 60 日），兩段各自平均與 t 值（以換倉日為單位）。
- 增量檢定（區分已失敗的同族）：每個換倉日做 Fama-MacBeth 迴歸，之後 20 日報酬（產業內排名）對 dt20 排名，控制周轉率（20 日成交股數 ÷ 已發行股數）、abvol60、amihud20、MAX（21 日最大日報酬）、殘差波動 resvol60、過去 20 日報酬（短期反轉）、12-1 動能、log 市值、最新月營收 SUE；全部為年內／當期百分位 − 0.5。另報告 dt20 與上述變數及 SUE 分數的等級相關。
- 組合：leg_probe 標準多空——產業內前 1/3 等權做多、後 1/3 等權放空，產業權重 = 股票池產業權重，持有到下一個換倉日；放空只用可借條件 D 通過的股票（前 60 日有借券成交、需借股數 ≤ 借券賣出額度與 60 日成交量 × 0.1、費率 ≤ 5%；資金 1,000 萬與 2 億兩種，同 borrow_capacity.py），某產業沒有可放空股票時該產業兩邊都不做；剩餘 β 用台指期對沖。另報告 fv3 式建構（每 3 個換倉日換倉、三份錯開）。
- 成本：股票換手 × 單邊 0.29625%，台指期單邊 0.005%，借券費逐日扣（缺值以 5%／年計）；報告年換手。
- 與月營收驚奇 SUE 合成（通過 (1)–(3) 後才做）：每個換倉日 SUE 與 dt20 各取產業內 z 分數後平均（同 revmom_persist 的合成方式），放進 fv3（前 300 名）與 fv5（前 500 名）建構。採用標準：合成版兩段 Sharpe 皆高於 SUE 單獨（前 300 名 0.93 / 1.79、前 500 名 1.45 / 1.87），且合成相對 SUE 單獨的每日報酬差全期 t > 1；另報告當濾網版本（SUE 做多名單排除 dt20 最差 20%）——MAX 濾網曾因剔除 SUE 贏家而失敗，所以要報告被排除股票的 SUE 分布。
- 通過標準（事前固定，全部成立才算通過）：(1) 主樣本 dt20 的產業內 20 日 IC 兩段皆 > 0 且各自 t > 2；(2) Fama-MacBeth 控制周轉率、abvol、amihud、MAX、殘差波動、短期反轉、動能、市值、SUE 後，dt20 係數全期 t > 2 且兩段同號；(3) 第 501–1000 名驗證樣本全期 IC > 0 且 t > 2；(4) 主樣本多空（條件 D、2 億）扣成本與借券費後兩段 Sharpe 皆 > 0。(1)(3) 成立但 (2) 不成立＝『當沖比只是周轉率／彩券型的代理』記為 failed；(1)–(3) 成立但 (4) 不成立記為 partial，再看合成。次要腿 dtjump 只在 (1)–(3) 全部以 t > 3 成立時才視為獨立通過（多重檢定），否則只報告。
- 穩健性（只報告，不改判定）：(a) 2015–2018 的樣本（含 2017-04-28 降稅前後）當額外樣本外；(b) 改用金額版當沖比（(BuyAmount + SellAmount)/2 ÷ Trading_money）；(c) 分上市／上櫃；(d) 排除電子股；(e) 依全市場當沖比高低（月平均前後一半）分期看 IC；(f) 第 +1 日漲停／跌停比例。

## 與已測點子的關係

- MAX／漲停濾網（彩券型股票）（failed，docs/max_rec_robust_report.md）：命中 lottery
- 補充：dedup 命中 max_lottery（MAX／漲停濾網，failed）與 liquidity（Amihud、異常成交量，failed）。差異：MAX 與異常成交量是價格與總量的結果，當沖比是『誰在交易』的組成——同樣的成交量，若由當日平倉的散戶投機者貢獻，代表不具資訊的短線需求，這是台股獨有的公開資料；本卡用 Fama-MacBeth 明確控制周轉率、abvol、amihud、MAX、殘差波動，若控制後不顯著就判定為同族失敗。與 1 日短期反轉（partial，扣成本後虧損）的差異：本卡持有到下一個月營收換倉日（約 20 個交易日），換手接近 leg_probe 其他月頻腿。與處置股（failed）的關係：處置期間不能當沖，當沖比設為缺值；處置前常見當沖比急升，dtjump 可能與處置事件重疊，要報告排除處置前 20 日後的結果。

研究點子，非投資建議。
