# I036 法人公告前交易是否預告營收驚奇：未被預先交易的驚奇漂移較強

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過 | B | 濾網或加權（SUE 條件分組＋交互項），兩步檢定 | free | 前 500 名約 0（三大法人、價格、月營收已快取 776/776，已逐檔確認）；第 501–1000 名驗證約 582 次（TaiwanStockInstitutionalInvestorsBuySell 快取 29/611，每檔一次全期間，約 1 小時） | 2026-10-21 |

## 假設

月營收公告期限前（上月 21 日 ~ 本月 10 日）三大法人淨買超能預測本月 SUE；且在同樣高（低）SUE 的股票中，公告前法人沒有同向交易（未被預期）的，公告後第 +2 ~ +21 日的漂移比已被法人預先交易的更強。

## 機制（為什麼會有超額報酬）

資訊已部分反映：若法人（外資、投信）在公告前就依私有資訊或通路調查交易，驚奇的一部分在公告前已進入價格，之後可漂移的空間較小；反之，未被預先交易的驚奇代表市場真正不知道的資訊，反應不足較大。本卡把法人交易當作『市場對驚奇已知多少』的量尺，而不是當作獨立選股因子。

## 出處

- Baker、Litov、Wachter 與 Wurgler（2010）Can Mutual Fund Managers Pick Stocks? Evidence from Their Trades Prior to Earnings Announcements，JFQA，https://doi.org/10.1017/s0022109010000426：同儕審查；基金近期買進的股票在下一次盈餘公告時報酬顯著高於賣出的股票，選股能力集中在公告前的交易。
- 陳柔君、劉晏睿、蕭朝興（2022）台灣股市的未預期月營收：綜合分析，管理學報 39(4)，https://lawdata.com.tw/tw/detail.aspx?no=484826：同儕審查（台灣）；摘要指出三大法人在月營收公告前買進未預期營收最高的股票、賣出最低的股票。
- 淡江大學學位論文（2011）https://etds.lib.tku.edu.tw/ETDS/Home/Detail/U0002-1502201115340900：學位論文；依搜尋摘要，2008–2009 年臺灣50成分股三大法人在營收公告日與之後 1–2 日出現反向操作（本次未讀全文）。
- 本專案 docs/sue_attention_industry_report.md（I004）：法人持股或成交占比高低當條件，2023 年後高關注股 SUE 反而更有效；docs/leg_pool_report.md：投信買超、外資持股變化當選股因子失敗。

## 台股適用性

台灣獨有的每日三大法人個股買賣超是免費公開資料，且月營收公告期限固定，可以清楚切出『公告前』窗口；陳柔君等（2022）已有台灣證據顯示法人公告前交易方向與驚奇一致，所以第一步大概率成立，關鍵在第二步是否有增量。限制：歷史上沒有逐家公告日（FinMind create_time 2026-05 才有），公告前窗口只能用期限（10 日）截止，部分公司 1–9 日就已公告，窗口會混入公告後的反應；主檢定用『上月 21 日 ~ 本月 5 日』為保守窗口、『至 10 日』為次要。

## 所需資料

- FinMind TaiwanStockInstitutionalInvestorsBuySell：外資、投信、自營商每日買賣股數（2017-01 起已快取）
- FinMind TaiwanStockMonthRevenue：SUE（沿用 fv5 定義）
- FinMind TaiwanStockPrice＋股利還原：報酬；TaiwanStockShareholding 的已發行股數做標準化

## 檢定計畫（看結果前固定）

- 樣本：2019-01 ~ 2026-04 當年前 500 名非金融股（金融股另有 ESUE 規格）；驗證第 501–1000 名。
- 訊號：PreFlow = 窗口內（主：上月 21 日 ~ 本月 5 日；次要：上月 21 日 ~ 本月 10 日）外資＋投信淨買股數 ÷ 已發行股數，產業內百分位；另報告外資、投信分開的版本（只報告）。
- 第一步（基本面預測）：Fama-MacBeth，本月 SUE 對 PreFlow、上月 SUE、窗口前 20 日報酬、窗口內報酬、市值迴歸；PreFlow 係數兩段同號為正、全期 t > 2 才進入第二步。
- 第二步（報酬）：在 SUE 前 30% 組內比較 PreFlow 後三分之一（未預先買進）− 前三分之一（已預先買進）的第 +2 ~ +21 日報酬（以公告期限次一交易日為 +0、+1 收盤進場，與 fv5 一致）；SUE 後 30% 組做對稱比較並以帶符號差合併。Fama-MacBeth 交互項 SUE × PreFlow 預期為負。
- 成本與可交易：若第二步成立，做 fv5 修改版：做多名單排除 PreFlow 前三分之一、放空名單排除 PreFlow 後三分之一，各腿以其他高（低）SUE 股遞補，扣單邊 0.29625% 與借券費、台指期對沖，與 fv5 1.45 / 1.87（全期 1.64）比較。
- 通過標準（事前固定）：第一步如上；第二步帶符號差兩段同號、全期 t > 2，驗證樣本同號；可交易版兩段 Sharpe 都不低於 fv5 且全期 ≥ 1.70。任一不成立即停止。
- 預先說明方向風險：I004 發現高關注股 SUE 更有效，若第二步方向相反（已被預先交易者漂移更強）也依規定判為未通過，不改成反向規則。

## 與已測點子的關係

- 投信買超、外資持股變化（failed，docs/leg_pool_report.md）：命中 投信, 外資, 三大法人
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue, 營收驚奇
- 外資台指期／台指選擇權淨部位擇時（failed，docs/fut_inst_timing_report.md）：命中 外資, 三大法人
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue
- 月營收驚奇 × 低法人關注：注意力低的股票漂移較強（條件分組與加權）（card:已測：未通過，research/ideas/I004-sue-x-low-attention.md）：命中 SUE interaction
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE
- 月營收變動原因說明（備註）：併購、一次性認列造成的營收驚奇漂移較弱（card:已測：訊號成立、可交易未通過，research/ideas/I025-revenue-remark-transitory-sue.md）：命中 SUE interaction
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 營收品質濾網：應收帳款與存貨成長超過營收成長的高 SUE 股漂移較弱（card:已測：未通過，research/ideas/I028-receivable-inventory-quality-sue.md）：命中 SUE interaction
- 補充：與已失敗的籌碼因子（投信買超、外資持股變化當選股分數）不同：這裡第一步檢定的是法人交易能否預測基本面（下一個 SUE），第二步把它當作驚奇『已被知道多少』的條件，只修改 SUE 名單。與 I004（法人持股水準／成交占比當注意力）不同：I004 用的是水準，與驚奇方向無關；本卡用的是與驚奇同向或反向的交易。


## 結果（2026-10-21）

未通過：第一步本月 SUE 對公告前外資＋投信淨買超係數 −0.017 / −0.034（全期 t −0.8），依點子卡停止，未看報酬。見 [docs/clarification_inst_report.md](../../docs/clarification_inst_report.md)。

研究點子，非投資建議。
