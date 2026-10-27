# I069 fv5 腿內依 EAR 加權（SUE 與公告期報酬同向加碼、反向減碼）：名單不變只調權重，以第 501–1000 名選規則、第 1001–1500 名確認

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 濾網或加權（fv5 腿內權重，與 fv5 建構配對比較）＋三階段跨樣本規則選擇 | free | 約 0（前 1500 名月營收、還原價、產業分類已在 I063 使用；前 500 名借券與台指期已快取） | 2026-10-27 |

## 假設

在 SUE 產業內前（後）1/3 的股票中，EAR 愈高（低）者之後 60 日產業調整報酬愈高（低）；因此 fv5 名單不變、只把多方腿中 EAR 同向（產業內前 1/3）的股票權重乘 1.5、反向（後 1/3）乘 0.5（空方腿對稱），兩段 Sharpe 都不低於 fv5（1.45 / 1.87）、全期至少 1.74。

## 機制（為什麼會有超額報酬）

Chen、Chen、Hsin、Lee（2014）發現營收（盈餘）動能的利潤取決於價格動能是否同向，市場低估多個訊號同向時的聯合含意；Jegadeesh 與 Livnat（2006, FAJ）也發現營收與盈餘驚奇同向時漂移較強。I063 的 0.75 SUE + 0.25 EAR 合成會把 SUE 極端但 EAR 反向的股票換成 SUE 中等的股票，可能丟掉 SUE 最強的漂移；腿內加權保留 fv5 名單，只在已入選的股票之間移動權重，名單換手幾乎不變。若 EAR 的增量只出現在某一腿（Hong、Lim、Stein 2000：壞消息擴散較慢、輸家的動能較強），規則只用在那一腿。

## 出處

- （同儕審查，作者為台灣學者，摘要）Chen、Chen、Hsin、Lee（2014）Does revenue momentum drive or ride earnings or price momentum?，Journal of Banking & Finance 38: 166–185，https://ir.lib.nycu.edu.tw:443/handle/11536/23670：基本面動能的利潤取決於價格動能是否同向；同向時市場低估聯合含意
- （同儕審查）Jegadeesh、Livnat（2006）Post-Earnings-Announcement Drift: The Role of Revenue Surprises，Financial Analysts Journal，https://rpc.cfainstitute.org/research/financial-analysts-journal/2006/post-earnings-announcement-drift-the-role-of-revenue-surprises：營收與盈餘驚奇同向時漂移較強（依摘要）
- （同儕審查）Hong、Lim、Stein（2000）Bad News Travels Slowly: Size, Analyst Coverage, and the Profitability of Momentum Strategies，Journal of Finance 55(1): 265–295，https://www.nber.org/papers/w6553：依摘要，分析師覆蓋低的效果在過去輸家遠強於贏家，負面消息擴散較慢
- （本專案）docs/revenue_ear.md：EAR 對 SUE 的殘差版本全期 t 5.6，與 SUE 幾乎無關；0.75/0.25 合成 1.37 / 1.90
- （本專案）docs/fv5_forward_power_execution_report.md（I054）：SUE 最極端 10% 的股票換倉後仍持續漂移，是 fv5 報酬的重要來源

## 台股適用性

月營收與 EAR 每月都有，fv5 名單與成交日不變，所以漲跌停、借券、成本的處理完全沿用 fv5。腿內加權只改各檔資金比例，換手增加有限（每份資金建倉時決定權重，持有期內不再調整）。單檔權重上限：空方權重 1.5 倍會增加單檔借券量，需確認 2 億資金下可借量（analysis/borrow_capacity.py 的條件）。沒有台股腿內同向加權的實證；Chen 等（2014）的樣本以美股為主（依摘要無法確認是否含台股）。

## 所需資料

- FinMind TaiwanStockPrice 還原價（已快取）：EAR 與 60 日報酬
- FinMind TaiwanStockMonthRevenue（已快取）：SUE
- FinMind TaiwanStockSecuritiesLending、TaiwanDailyShortSaleBalances（已快取）：借券條件 D、借券費、可借量
- config/universe_mcap_membership.csv、config/universe_mcap_membership_1500.csv
- analysis/revenue_ear.py、analysis/fv5_family.py、analysis/fv5_invvol.py（腿內權重的寫法）

## 檢定計畫（看結果前固定）

- 樣本與時點：2019-03 ~ 2026-04 每月換倉日；兩段 2019–2022 / 2023–2026/04；2026-05 以後不用。EAR、SUE 定義與 I063、fv5 完全相同。
- 階段 1（選規則，只用第 501–1000 名）：每月在 SUE 產業內前 1/3 的股票中，以 60 日產業調整報酬百分位對 EAR 產業內百分位迴歸（控制 log 市值與上月公告後報酬 PRE），Fama-MacBeth、Newey-West 落後 3，得到多方斜率 b_L；SUE 後 1/3 中同樣得到空方斜率 b_S。規則：b_L 與 b_S 都 > 0 且 t ≥ 2.0 → R1（兩腿都加權）；只有 b_L → R2（只多方）；只有 b_S → R3（只空方）；都沒有 → 停止。
- 階段 2（確認，只用第 1001–1500 名）：階段 1 選中的斜率在第 1001–1500 名同號且 t ≥ 2.0；未過即停止。
- 階段 3（可交易，前 500 名，只做一次）：fv5 建構不變，選中的腿內權重為 EAR 同向前 1/3 乘 1.5、中間 1/3 乘 1.0、反向後 1/3 乘 0.5（EAR 1/3 以全產業切點計），再正規化使該腿總權重不變。通過：兩段 Sharpe 皆 ≥ fv5（1.45 / 1.87）、全期 ≥ 1.74（與 I063 H2 門檻相同）、年換手增加 ≤ 10%、2 億資金下空方加權後的可借比例不低於 fv5 的 95%。
- 多重檢定：本批 5 張卡；階段 1、2 各 t ≥ 2.0 的聯合機率約 0.05 × 0.05，加上階段 3 的經濟門檻，整體偽陽性遠低於 Holm 的 1%。
- 只報告：前 500 名的 b_L、b_S（不用於判定，因為 H2 的合成結果已看過）；fv5x 加同一規則的版本；權重 2.0／0.0（即排除反向股）的版本（不判定）。
- 資料窺探：前 500 名的 EAR 主效果與 0.75/0.25 合成已看過；任何樣本的 SUE 組內 EAR 斜率都沒有看過。第 501–1000 名在 I063 只看過主效果係數。規則由階段 1 機械決定、只有 3 個選項，不另做權重網格；未通過即停止。

## 與已測點子的關係

- 月營收公告期報酬（EAR）的獨立多空與 fv5 各半組合：EAR 是否提供 fv5 之外的報酬來源（I063 後續，以跨越檢定判定）（card:待確認，research/ideas/I068-ear-standalone-ls-fv5-blend.md）：命中 公告期報酬, EAR, I063 後續
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 權重, fv5
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5, SUE
- 融券強制回補的價格壓力（I050 修訂版）：以官方停券日為事件日，在未看過的第 501–1500 名確認，處理 I056 附帶發現的資料窺探（card:已測：未通過（P2 t 1.3；I059 啟動條件成立），research/ideas/I058-forced-covering-oos-501-1500.md）：命中 第 501–1000 名, 第 1001–1500 名
- fv5 空方腿避開融券回補買壓：新空單若在 10 個交易日內遇到停券窗，延到最後回補日收盤再建倉（訊號與名單不變，只改建倉時點）（card:已測：未通過（只在 2023 年後有效），research/ideas/I059-fv5-short-defer-stop-window.md）：命中 fv5, 空方腿
- 月營收公告期間的市場反應（公告期報酬）對 SUE 的增量：價格反應是否帶有營收數字以外的資訊（card:已測：H1 通過、H2 未通過（不另立前瞻），research/ideas/I063-revenue-announcement-window-return-ear.md）：命中 公告期報酬, EAR
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 營收創新高（÷ 前 24 個月最高）（effective，docs/revmom_persist_report.md）：命中 revenue momentum
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- 12-1 動能、持續性動能、frog-in-the-pan（failed，docs/revmom_persist_report.md）：命中 momentum
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 小型股版月營收驚奇：第 501–1000 名獨立多空，以及前 1000 名廣度版本（card:已測：階段一未通過（接近），research/ideas/I030-smallcap-sue-501-1000.md）：命中 第 501–1000 名
- 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）（card:已測：未通過（階段 1 過、階段 2 t 2.8），research/ideas/I043-smallcap-multifactor-composite.md）：命中 sue
- fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）（card:已測：未通過，research/ideas/I054-fv5-entry-execution-price.md）：命中 fv5
- fv5 空方腿改以融券為主、借券補足：借券費與強制回補成本的取捨（訊號與名單不變）（card:已測：未通過（保守情境 +0.41%），research/ideas/I056-fv5-short-leg-margin-vs-sbl.md）：命中 空方腿
- fv5 家族的稅後績效與除息日建倉規則：個人投資人股利所得稅與二代健保補充保費下，多方新倉延到除息後是否改善稅後報酬（card:已測：R1 未通過（稅後績效已報告），research/ideas/I061-fv5-after-tax-exdiv-entry.md）：命中 fv5
- fv5 多方腿改用股票期貨的稅後執行（I031 修訂版）：期交所現金股利權益數調整＋期貨交易所得停徵，避開股利稅與賣出證交稅（card:已測：未通過（轉倉成本大於節稅），research/ideas/I064-fv5-long-leg-ssf-after-tax.md）：命中 多方腿
- 補充：與 I063 H2（合成分數，會換名單）不同：本卡名單與 fv5 相同，只在腿內移動權重。與 I033／fv5v（逆波動權重）不同：權重依據是 EAR 而非波動。與已失敗的條件型交互（I004 低法人關注、I019 匯率、I067 庫存循環）不同：條件變數是同一次公告的價格反應，且有 I063 的跨名次組主效果證據。

研究點子，非投資建議。
