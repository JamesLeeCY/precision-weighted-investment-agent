# I004 月營收驚奇 × 低法人關注：注意力低的股票漂移較強（條件分組與加權）

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過 | A | 濾網或加權（SUE 條件分組／交互作用） | free | 前 300／500：約 0（價格、外資持股、三大法人、月營收皆已快取，已逐鍵確認 776/776 檔）；第 501–1000 名驗證：約 1,750（約 582 檔缺月營收、外資持股、三大法人各 1 次） | 2026-10-15 |

## 假設

在同產業、同市值水準下，法人關注度低（外資持股比例低、三大法人成交占比低）的股票，月營收驚奇（SUE）之後 20–60 個交易日的產業內 IC 高於法人關注度高的股票；把 fv3 多空的權重往低關注股傾斜，扣成本後的 Sharpe 兩段都高於 fv3。

## 機制（為什麼會有超額報酬）

行為偏誤（有限注意力、資訊逐步擴散）：投資人處理資訊的容量有限，沒有被法人追蹤的股票，公告後的價格調整較慢，漂移比例較大（Hong-Stein 逐步擴散模型；DellaVigna-Pollet、Hirshleifer 等的注意力實證）。台股散戶比重高、月營收資訊量大且同日集中公告，低關注股的反應不足可能更明顯。制度面的輔助解釋：低法人持股股票的可借量較低、放空較貴，套利修正較慢（Prado 等 2016）。

## 出處

- （同儕審查）DellaVigna & Pollet（2009）Investor Inattention and Friday Earnings Announcements，Journal of Finance，https://doi.org/10.1111/j.1540-6261.2009.01447.x：週五公告（注意力較低）的立即反應少約 15%、延遲反應多約 70%（相對其他日公告）
- （同儕審查）Hirshleifer, Lim & Teoh（2009）Driven to Distraction: Extraneous Events and Underreaction to Earnings News，Journal of Finance，https://doi.org/10.1111/j.1540-6261.2009.01501.x：同日其他公司公告越多，立即反應越弱、公告後漂移越強
- （同儕審查）Hong, Lim & Stein（2000）Bad News Travels Slowly: Size, Analyst Coverage, and the Profitability of Momentum Strategies，Journal of Finance，https://doi.org/10.1111/0022-1082.00206：控制市值後，分析師覆蓋低的股票動能較強，壞消息擴散較慢
- （同儕審查）Porras Prado, Saffi & Sturgess（2016）Ownership Structure, Limits to Arbitrage, and Stock Returns: Evidence from Equity Lending Markets，Review of Financial Studies，https://doi.org/10.1093/rfs/hhw058：法人持股低且集中的股票可借量低、盈餘公告後漂移較大
- （同儕審查）Retail Attention, Institutional Attention（2022），Journal of Financial and Quantitative Analysis，https://doi.org/10.1017/s0022109022000734：散戶持股高的股票，在總經新聞分散注意力時漂移明顯增加
- （同儕審查，台灣）Yu-Hsiu Lin & Min Han Wu（2021）Response to Unexpected Earnings and the 52-Week-High Anchoring，Journal of Economics and Management 17(1)，https://jem.fcu.edu.tw/assets/jem/past_issues/vol.17_no.1/PDF/vol.17_no.1_01.pdf：台股季盈餘漂移在外資持股高時減弱（只讀到摘要，樣本期間與幅度未確認）
- （同儕審查）Post-Earnings Announcement Drift and Ownership Structure in the Modern Japanese Stock Market（2023），The Japanese Accounting Review，https://doi.org/10.11640/tjar.13.2023.01：以理性不注意模型檢驗日本 PEAD 與持股結構的關係（摘要未給數字）
- （部落格摘要）Alpha Architect（2013）Pay attention to Friday earnings announcements，https://alphaarchitect.com/pay-attention-to-friday-earnings-announcements/：上述 DellaVigna-Pollet 的實務摘要

## 台股適用性

台灣有一篇同儕審查實證（Lin & Wu 2021）指出外資持股高會削弱季盈餘漂移，方向與假設一致，但那是季報而非月營收，且只讀到摘要。月營收在 10 日前集中公告，台股散戶交易占比高，低關注機制有空間。限制：(1) 台股沒有免費的分析師覆蓋資料（FinMind 無、scout.py data 查無），以法人持股與法人成交占比替代；法說會次數可從公開資訊觀測站整理，但屬 manual，v1 不用。(2) 低關注股多為小型股，SUE 分數已對 log 市值中性化，但『關注度』本身與市值高度相關，必須先對市值取殘差，否則只是在測市值交互作用。(3) 低關注股可借量較低，做空端可能大量被條件 D 剔除，傾斜後放空端的覆蓋率要先報告。(4) 歷史逐家公告日不可得（create_time 只有 2026 年），所以 Hirshleifer 式的『同日公告家數』分心檢定無法做，不列入。

## 所需資料

- FinMind TaiwanStockShareholding（已快取）：ForeignInvestmentSharesRatio 外資持股比例（水準，不是變化）、NumberOfSharesIssued
- FinMind TaiwanStockInstitutionalInvestorsBuySell（已快取）：五類法人買進＋賣出股數，計算 60 日法人成交占比 =Σ(買+賣)÷(2×成交股數)
- FinMind TaiwanStockPrice（已快取）：成交股數、成交金額、收盤價（市值、週轉率）
- FinMind TaiwanStockMonthRevenue（已快取）：SUE，與 fv3 相同（data/revenue_signal.revenue_surprise）
- config/universe_mcap_membership.csv：每年市值前 300／500／1000 名與 sector

## 檢定計畫（看結果前固定）

- 樣本：主樣本市值前 300 名（fv3 股票池）；次要前 500 名；換倉日為 leg_probe.prepare 的 schedule（每月營收公告期限後次一交易日，2019-01 至 2026-04，共約 88 期）；分 2019–2022 與 2023–2026/04 兩段；2026-05 以後不用。第 501–1000 名作獨立驗證為選做（需約 1,750 次請求，使用者同意後才抓）。
- SUE 分數：完全沿用 leg_probe.leg_scores(c, 'sue')（產業內 z 分數 → 對產業虛擬變數與 log 市值迴歸取殘差），不改定義。
- 關注度（換倉日 d，只用 d−1 以前資料）：主要 ATT = 兩項的產業內百分位平均：(a) 外資持股比例水準；(b) 前 60 個交易日三大法人成交占比。再把 ATT 對產業虛擬變數與 log 市值迴歸取殘差 → ATT_res（『同市值下的法人關注』，對應 Hong-Lim-Stein 的殘差覆蓋）。次要（只報告、不作通過依據）：(c) 前 60 日週轉率（成交金額 ÷ 市值）；(d) 原始市值（產業內三分位）。
- 與已失敗腿的區隔檢查：先報告 ATT_res 與 foreign_chg（20 日外資持股變化）、trust_buy（20 日投信淨買超）在換倉日的橫斷面 Spearman 相關；另把 ATT_res 單獨當一條腿跑 leg_probe 的標準包裝，報告其超額 Sharpe。通過與否只看交互作用，不看 ATT 主效果。
- 檢定一（IC 分組）：每期在每個產業內依 ATT_res 中位數分成低／高關注兩半；各半在產業內計算 SUE 分數與 fwd20、fwd40、fwd60 報酬的 Spearman IC（leg_probe.within_ic）；差額 = 低 − 高，對 88 期取平均，t 值用 Newey-West（fwd40、fwd60 為重疊視窗，lag = 1、2）。
- 檢定二（交互作用迴歸）：Fama-MacBeth，每期以產業內報酬百分位為應變數，自變數 SUE 分數、ATT_res、SUE × ATT_res（皆產業內標準化），加產業虛擬變數；看交互項係數（預期為負：關注越低、SUE 斜率越大）。
- 檢定三（可交易版本）：權重傾斜，產業內仍依 SUE 取前／後 1/3（用 ls_turnover.ew_ls_buffer：每 3 個月、三份錯開、緩衝 1/2、可借條件 D、資金 2 億），入選股的權重乘 (1 + 0.5 × ATT_low)，ATT_low ∈ [−1, 1] 為產業內低關注百分位線性轉換，產業內重新正規化使產業總權重不變；剩餘 β 以台指期對沖。對照組為同一程式的 fv3 建構（SUE 單獨）。只測這一個傾斜強度（0.5），不掃參數。
- 另報告：低／高關注兩半各自的 ew_long_short（borrow_capacity）超額 Sharpe、放空端可借覆蓋率（條件 D，以放空權重加權）、進場日漲停比例。
- 成本：股票單邊 0.29625%（換手兩邊皆扣）、借券費逐日扣（同 hedge_construction.lending_fees）、台指期單邊 0.005%。關注度變動慢，預期換手增加有限，需報告年換手相對 fv3 的差。
- 通過標準（全部成立）：(1) 主樣本前 300 名，fwd20 的 IC 差額（低 − 高）兩段皆 > 0，合併 t > 2；(2) 前 500 名同號；(3) 交互項係數兩段皆為負；(4) 傾斜版本扣成本後的多空 Sharpe 兩段都高於同股票池 fv3 建構，且放空端可借覆蓋率不低於 fv3 的 90%。若 (1)–(3) 成立但 (4) 不成立，記為 partial（解釋力有、可交易性不足）。

## 與已測點子的關係

- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 月營收驚奇, sue, 營收驚奇
- 投信買超、外資持股變化（failed，docs/leg_pool_report.md）：命中 外資, 三大法人
- 補充：與已失敗的『投信買超、外資持股變化』（leg_pool：foreign_chg、trust_buy 超額 Sharpe 為負）不同族：那兩條腿是 20 日『流量變化』單獨當選股訊號；這裡用的是『持股水準與法人交易參與度』，只當 SUE 斜率的條件變數，且先對市值與產業取殘差；通過與否只看交互作用。與 SUE 本身（effective）的關係：不改 SUE 定義與產業中性建構，只改變同一份名單內的權重，所以對 fv3 是增量檢定。已知風險：多重比較（本專案已測 30 多個訊號），所以只事先固定一個主關注度、一個傾斜強度。

研究點子，非投資建議。

## 結果（2026-10-15）

已測：未通過，見 [docs/sue_attention_industry_report.md](../../docs/sue_attention_industry_report.md)。
