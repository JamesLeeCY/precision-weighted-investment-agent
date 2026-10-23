# I057 fv5 家族的影子前瞻：在市值第 501–1000 名平行記錄同一組修改，作為獨立樣本的輔助判定（統計版，不交易）

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 前瞻決策程序（事前登錄，輔助判定）＋回測相關性與檢定力校準 | free | 回測約 0（第 501–1000 名月營收、價格、借券餘額已快取）；live 每月約 1,500–2,000 次（約 500 檔 × 月營收、價格、借券賣出餘額各 1 次，逐檔；免費每小時 600 次，約 3 小時，可排在每月 11 日後夜間背景執行）；選做第 1001–1500 名再加約 1,500 次／月，回測另需約 1,000 次（TaiwanDailyShortSaleBalances、SecuritiesLending 未快取） | 2026-10-23 |

## 假設

fv5 家族各修改（S1 合成、逆標準差權重、金融股 ESUE）相對 fv5 的波動調整後每段報酬差，在第 501–1000 名影子組合與前 500 名的相關係數低（回測 < 0.5），因此兩個股票池合併檢定（逆變異數加權）達 50% 檢定力所需的 live 月數，比只用前 500 名少至少 30%。

## 機制（為什麼會有超額報酬）

統計原理，不是超額報酬來源：同一期間內不同股票池的報酬差有部分獨立的雜訊；若修改的效果來自共同機制（例如 S1 反映放空資訊、逆波動權重降低特異風險），在兩個池子都應出現，合併兩個近似獨立的估計可提高精度。全球因子研究也用多市場的新資料檢驗同一因子，證據會隨獨立樣本增加而變強。代價：中小型股不能實際交易（I042：額外滑價 0.46%、借券覆蓋 34%–49%），影子組合只記錄扣成本前或簡化成本的統計版，不能直接當成可交易績效。

## 出處

- （同儕審查）Jensen、Kelly 與 Pedersen（2023）Is there a replication crisis in finance?，Journal of Finance 78(5)，https://www.nber.org/papers/w28432：以貝氏模型合併多個市場的證據，多數因子在 93 國的新資料中仍成立（依摘要）
- （本專案）docs/ts_rank_report.md：S1 在第 501–1000 名 IC +0.031（t 2.4）；docs/smallcap_invvol_report.md：逆波動權重的比較（含中小型股）
- （本專案）docs/smallcap_execution_report.md（I042）：第 501–1000 名額外滑價約 0.46%、借券覆蓋 34%–49%，只適合統計檢定
- （本專案）docs/fv5_family_voladj.md：前 500 名達 50% 檢定力需 76–302 段

## 台股適用性

中小型股的 SUE 效果與大型股相當（smallcap_sue 報告），所以影子組合有意義；但借券條件 D 在中小型股多數不成立，影子版必須改成『不限制可借、扣固定成本』的統計版，與前 500 名的 fv5 不完全對應。S1 與逆波動權重部分是在看過第 501–1000 名回測後才定的（S1 的驗證樣本就是 501–1000），所以回測期間的影子結果不獨立；只有 2026-05 以後的 live 影子資料是新的。第 1001–1500 名（config/universe_mcap_membership_1500.csv）可作為第三個池子，但借券資料未快取，列為選做。

## 所需資料

- config/universe_mcap_membership.csv：第 501–1000 名逐年成員（無存活偏誤）
- FinMind TaiwanStockMonthRevenue、TaiwanStockPrice、TaiwanStockSplitPrice（第 501–1000 名已快取至 2026-04）
- FinMind TaiwanDailyShortSaleBalances（前 1000 名已快取）：S1
- data_cache/events/self_earnings_series.csv：中小型金融股的 ESUE（多數中小型金融股不按月自結，E 修改可能只涵蓋很少股票）

## 檢定計畫（看結果前固定）

- 樣本：第 501–1000 名；回測 2019-03 ~ 2026-04 只用來估計相關性與檢定力；live 為 2026-05 起（回填 2026-05 ~ 10 的段與 live 段分開報告）。
- 影子規格（事前固定）：fv5-sh（產業內 SUE 前／後 1/3 等權多空，三份錯開、每 3 個換倉日換倉、台指期對沖 β），不限制可借、借券費一律以 2%／年計、交易成本單邊 0.29625% + 0.46%（I042 估計的額外滑價）；fv5s-sh、fv5v-sh、fv5x-sh 依同一修改規則（S1 權重 0.25、逆標準差權重、ESUE 替換）建構。
- 回測校準：計算前 500 名與影子的波動調整後每段差 d_k 的相關係數 r_k、各自平均與標準差；合併估計 = 兩池 d_k 平均的逆變異數加權（考慮 r_k 的共變異），計算 24、48、72 段時單尾 t > 2 的檢定力，以回測效果 100% 與 50% 兩種假設各報一次。
- 前提條件（不成立就不登錄影子前瞻）：(1) 影子回測中各修改的 d_k 平均與前 500 名同號；(2) 合併後達 50% 檢定力所需段數比只用前 500 名少至少 30%；(3) r_k < 0.5。
- live 輔助判定：合併估計的單尾 t > 2，且前 500 名自身的 d_k 平均 > 0（只要求同號），標記為『跨池支持』，提交使用者決定；不取代 I051 與 forward_validation.md 已登錄的正式規則。
- 多重檢定：四個修改（e、s、v、x）的合併 t 做 Holm 校正，家族單尾 10%；fv5e 的影子若涵蓋金融股 < 10 檔，只報告不判定。
- 資料窺探：S1 已用第 501–1000 名回測驗證過，逆波動權重也看過中小型股結果，回測期間的影子不是獨立樣本，只用於校準；判定只用 live 段。
- 通過標準（本卡本身）：前提條件全部成立，才建議另立影子前瞻並每月執行；否則只保留回測校準表。

## 與已測點子的關係

- 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）（card:已測：未通過（階段 1 過、階段 2 t 2.8），research/ideas/I043-smallcap-multifactor-composite.md）：命中 合成, 中小型股, 501-1000, sue
- fv5 家族前瞻的輔助判定：以機制指標（增量 IC、日頻波動比）加非劣性檢定，縮短判定時間（不取代已登錄規則）（card:待確認，research/ideas/I053-fv5-family-mechanism-endpoints-power.md）：命中 檢定力, statistical power, fv5 家族, forward validation
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5, 金融股, esue
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 小型股, 501-1000, sue
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 逆變異數, 權重, fv5
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 金融股, fv5, SUE
- 小型股版月營收驚奇：第 501–1000 名獨立多空，以及前 1000 名廣度版本（card:已測：階段一未通過（接近），research/ideas/I030-smallcap-sue-501-1000.md）：命中 小型股, 中小型股, 第 501–1000 名
- 中小型股（市值第 501–1000 名）執行面前置檢查：容量、滑價、漲跌停、借券與避險工具（card:已測：L2、S 未過（只做統計檢定），research/ideas/I042-smallcap-execution-precheck.md）：命中 中小型股, 小型股, 501-1000
- 中小型股的獲利能力因子：毛利÷總資產（GP/A）高的第 501–1000 名股票之後報酬較高（card:已測：未通過，research/ideas/I044-smallcap-gross-profitability.md）：命中 中小型股, 501-1000
- 投信季底作帳與季初反轉：中小型股投信重倉股在季底最後幾日上漲、下一季初回落（card:待確認，research/ideas/I045-sitc-quarter-end-window-dressing.md）：命中 中小型股, 501-1000
- 中小型股私募增資公告：董事會決議私募後的長期報酬（與淨發行 NSI 的增量）（card:待確認，research/ideas/I046-smallcap-private-placement.md）：命中 中小型股, 501-1000
- 中小型股庫藏股買回：第 501–1000 名董事會決議買回後的延遲反應（card:待確認，research/ideas/I047-smallcap-buyback-drift.md）：命中 中小型股, 501-1000
- fv5 家族的合併規格與前瞻採用規則：三項修改同時使用（fv5e＋fv5s＋fv5v）的交互作用，以及多重比較下的事前決策程序（card:已測：fv5x 回測通過（已另立前瞻）；採用規則改為波動調整後報酬差，research/ideas/I051-fv5-family-combined-spec-decision-rule.md）：命中 fv5 家族, 檢定力
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 金融股自結盈餘驚奇低換手多空（緩衝換倉）（failed，docs/fin_esue_followup_report.md）：命中 金融股
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- 金融股自結盈餘驚奇的低換手多空（緩衝換倉）（card:已測：未通過，research/ideas/I017-financial-esue-low-turnover-ls.md）：命中 金融股
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- fv5 腿內波動調整權重：以逆變異數權重取代等權（card:已測：未通過（W2 接近），research/ideas/I033-fv5-inverse-volatility-leg-weights.md）：命中 逆變異數
- 非金融按月自結公司的盈餘驚奇：同月 ESUE 相對 SUE 的增量（card:已測：未通過，research/ideas/I038-nonfinancial-esue-increment.md）：命中 ESUE
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:待確認，research/ideas/I054-fv5-entry-execution-price.md）：命中 fv5
- 補充：與 I053（機制指標）互補：I053 在同一股票池內換更精確的指標，本卡增加獨立樣本。與 I030／I043（中小型股訊號本身）不同，本卡不測新訊號，只用中小型股輔助判定 fv5 家族的修改。評為 B 是因為 live 每月需約 1,500–2,000 次請求，且前提條件（相關性低）不確定。

研究點子，非投資建議。
