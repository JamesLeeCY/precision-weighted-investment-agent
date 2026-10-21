# I041 PTT 股版討論量暴增（相對自身歷史）：散戶注意力代理，Google 搜尋熱度為穩健性

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過 | C | 橫斷面 IC（產業內 20／60 日）＋平均報酬分組（處理右偏）＋SUE 交互項＋與 fv5 合成 | free（公開網站，非 FinMind） | FinMind 約 0（價格、月營收、成交量、當沖比皆已快取）；PTT 網頁約 9,600 頁（index215 ~ 2026-04 底約 index9800，全部索引頁一次取得所有股票的標題），每頁間隔 3 秒、實測含重試約 3.5 秒，約 9–10 小時，可分夜背景執行；Google Trends（選做穩健性）每檔 2 次請求，前 500 名約 1,550 次、第 501–1000 名約 1,220 次，間隔 6 秒約 2.5 + 2 小時，但 429 風險未知，需可中斷續抓 | 2026-10-21 |

## 假設

在市值前 500 名中，過去 20 個交易日 PTT Stock 板標題提及次數在自身過去 250 個交易日的百分位排名越高（討論量暴增），之後 20 個交易日的產業內報酬越差；次要：同月 SUE 相同時，公告前討論量暴增的股票，SUE 之後的漂移較弱（SUE × 討論暴增交互項為負）。

## 機制（為什麼會有超額報酬）

行為偏誤：散戶在注意力集中時淨買進（Barber 與 Odean 2008），短期把價格推高、之後回落（Da、Engelberg、Gao 2011 的搜尋量先漲後反轉）。PTT Stock 板是台灣散戶最大的公開討論區，標題提及量直接量的是『被討論』而不是『被交易』，和本專案失敗的異常成交量、當沖比（都是交易結果）在構造上不同。用相對自身歷史的排名，是為了去掉台積電、航運、AI 股長期被大量討論的水準差，只留下『這檔股票現在異常熱門』。交互項的理由：若驚奇在公告前已被大量討論，公告時的資訊較少是新的，漂移應較弱。

## 出處

- Da、Engelberg 與 Gao（2011）In Search of Attention，Journal of Finance，https://doi.org/10.1111/j.1540-6261.2011.01679.x：同儕審查；Russell 3000、2004–2008，Google 搜尋量（SVI）上升預測之後 2 週價格較高、一年內反轉，且主要反映散戶注意力（依摘要）。
- Barber 與 Odean（2008）All That Glitters，Review of Financial Studies，https://doi.org/10.1093/rfs/hhm079：同儕審查；散戶是吸引注意力股票的淨買方（只核對書目）。
- Leung 與 Ton（2015）The Impact of Internet Stock Message Boards on Cross-Sectional Returns of Small-Capitalization Stocks，Journal of Banking & Finance 55，https://doi.org/10.1016/j.jbankfin.2015.01.009（摘要：https://researchers.mq.edu.au/en/publications/the-impact-of-internet-stock-message-boards-on-cross-sectional-re/）：同儕審查；澳洲 HotCopper 250 萬則訊息，討論量與情緒只和小型股同期報酬有關、大型股沒有效果，看多小型股之後表現較好且未反轉（依摘要）——方向與本卡的反轉假設相反，是反方證據。
- Antweiler 與 Frank（2004）Is All That Talk Just Noise? The Information Content of Internet Stock Message Boards，Journal of Finance，https://doi.org/10.1111/j.1540-6261.2004.00662.x（工作稿：https://wernerantweiler.ca/public/returns.pdf）：同儕審查；討論版訊息量可預測波動與成交量，對報酬的預測在經濟上很小（只核對書目與常見引述，未讀全文數字）。
- 何怡滿與陳雯琪（2019）投資人關注度對台灣50指數成分股之股票報酬與公司績效的影響，國立屏東大學學報：管理類 第 2 期，https://lawdata.com.tw/tw/detail.aspx?no=380733：同儕審查（台灣，校刊）；日 SVI 與當日報酬正相關，月 SVI 與月報酬無顯著關係（依摘要）。
- 政大碩士論文（2016）PTT 股版文章與推文預測個股與大盤，https://nccur.lib.nccu.edu.tw/handle/140.119/98565：學位論文；個股推文數對數日後報酬的預測方向不一致，作者沒有找到一致結果（依搜尋摘要）。
- 本專案 docs/daytrading_report.md（I009）：當沖比排序有預測力（產業內 20 日 IC +0.037 / +0.012，驗證 +0.062、t 3.5），但等權多空 −0.79 / −1.11，高當沖股報酬右偏；docs/leg_pool_report.md：異常成交量 abvol60 超額 Sharpe −1.51 / −0.78；docs/sue_attention_industry_report.md（I004）：2023 年後 SUE 在法人關注度高的股票反而更有效。

## 台股適用性

快速實測（2026-10-21，只看資料、不看報酬）：(1) PTT Stock 板網頁索引可回溯：目前最新為 index10464；2019-01-01 約在 index215，之後到現在約 10,250 頁（每頁 20 篇）；早期頁數稀少（index1 為 2006 年），2019 年起連續。月文章數：2019-06 約 1,440 篇（74 頁），2024-06 約 2,560 篇（130 頁）；類別以［新聞］最多（約 41–50%），其次為［情報］［請益］［標的］。(2) 標題能對到前 1000 名股名或代號的比例：2019 年約 31%、2022 年約 33%、2025 年約 33%（每年隨機 6 頁、120 篇）；整月實測（標題提及，每檔每篇算 1 次）：2019-06 前 1–100 名有 ≥1 篇者 57%、≥3 篇 27%、≥10 篇 4%，第 101–500 名 ≥1 篇 21%、≥3 篇 4%，第 501–1000 名 ≥1 篇 6%；2024-06 分別為前 100 名 75% / 36% / 7%、第 101–500 名 40% / 6% / 1%、第 501–1000 名 20% / 2%。提及高度集中（2024-06 台積電 123 篇，第二名鴻海 29 篇）；股名歧義實例：2019-06 的『三星』（三星科技 5007）有 16 篇，多數應是指韓國三星，需事前排除名單。(3) 抓取時連線偶爾被重置（兩次執行共約 330 次請求中 2 次），需自動重試；實測含重試平均約 3.5 秒一頁。結論：PTT 對前 100 大與熱門族群有足夠的月度計數，但第 101–500 名大多數月份是 0–2 篇（中位數 0），ts_rank 在多數小型股會被 0 主宰，所以主檢定把『過去 250 日提及數 < 12』的股票設缺值，並報告有效樣本數。Google Trends：pytrends 已於 2025-04 封存，但直接呼叫 trends.google.com 的 explore＋multiline 兩個端點可用（台積電、神基、聯茂、3005 各 2 次請求、間隔 6 秒，未遇到 429）；2018-01 ~ 2026-04 一次回傳 100 個月的月度值，中型股也沒有 0 值；限制是只有月頻（超過 5 年的區間）、每個關鍵字值是相對自身最大值的 0–100（ts_rank 不受縮放影響，所以可用）、抽樣誤差與 Google 未公告的速率限制、股名歧義（例如統一、大同、台塑與南亞科等）。

## 所需資料

- PTT Stock 板 https://www.ptt.cc/bbs/Stock/index{N}.html：標題、推文數、文章 ID 內含的 Unix 時間戳（精確到秒，可做點時正確）
- 股名對照：config/universe_mcap_membership.csv 的 stock_name（當年）＋四碼代號；代號 2000–2030 與年份衝突，只用股名比對
- Google Trends explore／widgetdata/multiline（選做）：geo=TW、2018-01 ~ 2026-04 月度
- 已快取：價格（報酬、周轉率、MAX）、當沖比 dt20（I009）、月營收 SUE

## 檢定計畫（看結果前固定）

- 樣本：市值前 500 名中『過去 250 日提及 ≥ 12 篇』的股票（依實測約為前 100–150 大，每期報告有效檔數；少於 60 檔的換倉日不計），2019-01 ~ 2026-04，兩段 2019–2022 / 2023–2026/04；驗證第 501–1000 名（預期有效樣本很少，只報告有效檔數與 IC）；2026-05 以後不使用。
- 計數：文章 ID 時間戳在 t−1 日 13:30 以前；標題（含 Re:）比對當年成員的股名（最長優先、不重複計算；四碼代號只在 2000–2030 以外使用；歧義股名如三星、統一、大同、台塑等的排除名單在抓完標題、看報酬前由人工固定），不含內文與推文；每篇對同一股票只算 1 次。主計數 N20 = 過去 20 個交易日提及篇數；ETF、大盤類標題不處理。
- 訊號：PTT_surge = −ts_rank(N20, 250 日)（ts_rank 定義同 I040，相等值取平均排名；過去 250 日提及總數 < 12 設缺值；有效值 < 120 日設缺值）。包裝：產業內 z → 對產業與 log 市值取殘差（N20 已是 20 日累積，不再做 20 日平均）。
- 時點：每月營收換倉日（88 次）；交互項用同月 SUE，討論量取公告期限前 20 個交易日。
- 主檢定 H1（反轉）：產業內 Spearman IC 對之後 20 日報酬（主）與 60 日報酬（輔），Newey-West t。
- 主檢定 H2（交互）：Fama-MacBeth 60 日報酬 = SUE + PTT_surge + SUE × PTT_surge + 控制；預期交互項 < 0。
- 多重檢定：H1、H2 兩個，用 Bonferroni，t 門檻 2.24（雙尾 5% ÷ 2）。
- 控制（H1 的 Fama-MacBeth）：dt20（當沖比）、20 日周轉率、abvol60、MAX、前 20 日報酬、12-1 動能、log 市值、SUE。PTT_surge 與 dt20、abvol60 的產業內相關若 |ρ| > 0.6，視為同族，直接停止（只當紀錄）。
- 右偏檢查（吸取 I009 教訓，事前寫入判準）：除了 IC，必須看五分位等權『平均』報酬差（最暴增 − 最冷）的 60 日值與 t，以及剔除每期報酬前 1% 極端值前後的差異。
- 通過標準（事前固定）：H1 需 20 日 IC 兩段皆 > 0、全期 t > 2.24，Fama-MacBeth 控制後全期 t > 2.24，且五分位平均報酬差兩段同號；H2 需交互項全期 t < −2.24、兩段同號。任一通過才做可交易檢查：fv5 分數改為 SUE 與 PTT_surge 的產業內百分位 0.75 / 0.25（H1），或 SUE 在討論暴增前 1/3 的股票權重減半（H2），兩段 Sharpe 都不低於 fv5（1.45 / 1.87）且全期高於 1.64。
- 成本：同 fv5（單邊 0.29625%、借券費、台指期對沖）；不測單獨多空當主判準（I009 已證明注意力類單獨多空被右偏打敗），單獨多空只報告。
- Google Trends 穩健性（只在 H1 或 H2 通過時才抓）：月度 SVI 的 12 個月 ts_rank 取代 PTT，關鍵字為股名，歧義名單在看報酬前由人工固定；只報告 IC 同號與否。
- 停止條件：H1、H2 都不過即登錄 failed，不再試其他視窗、情緒分類或推文數版本。

## 與已測點子的關係

- 相對自身歷史的時間序列排名（ts_rank）：借券賣出餘額比、融資餘額比、外資持股比例（card:待確認，research/ideas/I040-ts-rank-own-history-chip-fields.md）：命中 時間序列排名, ts_rank, 相對自身歷史
- 當沖比（dt20、dtjump）（failed，docs/daytrading_report.md）：命中 注意力, attention
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue
- 媒體報導法人財測的澄清公告後反轉（failed，docs/clarification_inst_report.md）：命中 media
- 法人公告前交易預告營收驚奇（failed，docs/clarification_inst_report.md）：命中 公告前
- 月營收驚奇 × 低法人關注（條件分組與加權）（failed，docs/sue_attention_industry_report.md）：命中 investor attention
- 月營收驚奇 × 低法人關注：注意力低的股票漂移較強（條件分組與加權）（card:已測：未通過，research/ideas/I004-sue-x-low-attention.md）：命中 investor attention
- 當沖比（散戶短線投機與注意力）：當沖成交占比高或突然升高的股票之後報酬較差（card:已測：未通過，research/ideas/I009-day-trading-ratio.md）：命中 散戶注意力
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 媒體報導法人財測的澄清公告：樂觀預估見報後的報酬反轉（card:已測：未通過，research/ideas/I035-media-forecast-clarification-reversal.md）：命中 investor attention
- 補充：先驗風險高：注意力類在本專案已失敗三次（異常成交量、當沖比、低法人關注），而且 I004 顯示 2023 年後 SUE 在高關注股反而更有效，與 H2 方向相反。可能不同之處只有兩點：(1) 量的是討論（意見）而非交易，事前要求與 dt20、abvol60 相關 < 0.6，否則視同同族停止；(2) 用相對自身歷史的暴增，而不是水準。若相關過高或 H1 不過，這張卡只當紀錄。另一個實際限制是 PTT 覆蓋集中在前 100 大與熱門族群，前 101–500 名多數月份計數很小，即使通過也可能只在大型股可用。

研究點子，非投資建議。
