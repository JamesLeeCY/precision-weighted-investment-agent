# I067 月營收驚奇在產業庫存循環下的條件效果：產業存貨相對營收處於自身高檔時，SUE 漂移是否較強

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | C | 橫斷面 IC（Fama-MacBeth 交互項，條件效果） | free | 約 0（前 500 名季度資產負債表、月營收、產業分類已快取）；第 1001–1500 名的 TaiwanStockBalanceSheet 多數已快取（快取約 2,159 檔），缺者至多約 50 | 2026-10-25 |

## 假設

在市值前 500 名中，當所屬產業的存貨對營收比相對該產業自身過去 12 季處於前 1/3（庫存高檔）時，產業內 SUE 對之後 60 個交易日報酬的斜率較高：SUE × 高庫存狀態的交互項 Fama-MacBeth 全期 t ≥ 2.58、兩段同號，並在第 1001–1500 名同號且 t ≥ 2.0。

## 機制（為什麼會有超額報酬）

庫存高檔代表產業處在去化期，投資人可能錨定在下行循環，對個別公司的正向營收驚奇（率先去化完成、拉貨回補）反應較慢；負向驚奇在去化期則較符合預期，反應較快。這是行為面的推論，沒有直接的文獻支持；反向機制同樣合理（去化期的營收可能來自降價出清，品質較差、較不持續）。所以本卡列為 C，只在使用者想測試產業循環條件時做，且只有一個事前固定的交互項。

## 出處

- （本專案）docs/revenue_quality_report.md：個股層級的『應收＋存貨成長超過營收成長』濾網在前 500 名 t 1.4、未通過（本卡改用產業層級、時間序列相對自身歷史的狀態）
- （本專案）docs/sue_attention_industry_report.md：產業層級營收驚奇輪動未通過；docs/fx_shock_report.md：匯率衝擊延遲反應 IC ≈ 0（說明產業與總經條件類的點子在本專案多數失敗）
- （同儕審查）Jegadeesh、Livnat（2006）Revenue surprises and stock returns，Journal of Accounting and Economics，https://ideas.repec.org/a/eee/jaecon/v41y2006i1-2p147-171.html：營收驚奇的漂移與分析師緩慢調整有關（依工作論文摘要；未直接涉及庫存循環）
- 未找到以產業庫存循環為條件的營收或盈餘漂移研究；本卡的機制屬推論，證據等級最低

## 台股適用性

台股電子、塑化、鋼鐵、紡織等產業有明顯庫存循環，月營收又是最即時的需求資訊，所以若有條件效果，台股是合適的檢驗場。限制：季報存貨要等法定期限後才可用（Q1 5/15、Q2 8/14、Q3 11/14、Q4 3/31），狀態最多落後約 4 個半月；營建業存貨主要是土地與在建工程、金融業無存貨，需排除。

## 所需資料

- FinMind TaiwanStockBalanceSheet（已快取）：季底存貨
- FinMind TaiwanStockMonthRevenue（已快取）：季營收（3 個月加總）與 SUE
- 產業分類（既有 fv5 產業定義）、config/universe_mcap_membership.csv 與 _1500.csv

## 檢定計畫（看結果前固定）

- 樣本：前 500 名，2019-03 ~ 2026-04 每月營收換倉月；排除營建、金融保險與存貨占總資產 < 5% 的公司；產業需至少 5 家有存貨資料；確認樣本第 1001–1500 名；2026-05 以後不用。
- 狀態：產業存貨對營收比 = 產業內公司季底存貨加總 ÷ 同季營收加總，只用法定期限已過的最新一季；與該產業前 12 季（不含當季）比較，取百分位；前 1/3 為高庫存 H = 1。
- 主檢定：每月迴歸 60 日產業調整報酬（產業內百分位）於 SUE、H、SUE × H、營收創新高、log 市值；Fama-MacBeth、Newey-West 落後 3。通過：交互項全期 t ≥ 2.58（本批 Holm 最嚴門檻）、兩段同號且各自 t ≥ 1.5、第 1001–1500 名同號且 t ≥ 2.0。
- 可交易版本（只在主檢定通過時做）：fv5 分數改為 SUE 百分位 ×（1 ＋ 0.5 × H 標準化值）的單一事前規則，與 fv5 比較；通過需兩段 Sharpe 都 ≥ fv5 且全期 ≥ 1.74。
- 只報告：低庫存狀態（後 1/3）的交互項、多方與空方腿分開的交互效果。
- 資料窺探：SUE 在各產業、各年度的 IC 已在多份報告中看過（部分產業表現已知），但從未以庫存狀態分組；狀態門檻（前 1/3、12 季）事前固定，不做網格。
- 未通過即停止；不改狀態定義、回看季數或改用匯率、景氣燈號等其他狀態重測（那會變成多重比較）。

## 與已測點子的關係

- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 月營收驚奇, sue, 營收驚奇
- 營收品質濾網（應收＋存貨成長超過營收成長）（failed，docs/revenue_quality_report.md）：命中 存貨, inventory
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue, 月營收驚奇
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE, 月營收驚奇
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 月營收驚奇, sue
- 財報 Agent（營收、毛利、存貨、應收）（partial，forward/REPORT.md）：命中 inventory
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- 月營收驚奇 × 低法人關注：注意力低的股票漂移較強（條件分組與加權）（card:已測：未通過，research/ideas/I004-sue-x-low-attention.md）：命中 conditional drift
- 月營收驚奇的連續性：延續同號連串的驚奇漂移較強、中斷連串的驚奇漂移較弱（card:已測：未通過（接近），research/ideas/I021-revenue-surprise-streak.md）：命中 conditional drift
- 月營收變動原因說明（備註）：併購、一次性認列造成的營收驚奇漂移較弱（card:已測：訊號成立、可交易未通過，research/ideas/I025-revenue-remark-transitory-sue.md）：命中 conditional drift
- 營收品質濾網：應收帳款與存貨成長超過營收成長的高 SUE 股漂移較弱（card:已測：未通過，research/ideas/I028-receivable-inventory-quality-sue.md）：命中 存貨
- 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）（card:已測：未通過（階段 1 過、階段 2 t 2.8），research/ideas/I043-smallcap-multifactor-composite.md）：命中 sue
- 融券強制回補的價格壓力（I050 修訂版）：以官方停券日為事件日，在未看過的第 501–1500 名確認，處理 I056 附帶發現的資料窺探（card:已測：未通過（P2 t 1.3；I059 啟動條件成立），research/ideas/I058-forced-covering-oos-501-1500.md）：命中 第 1001–1500 名
- 補充：與 I028 營收品質濾網（個股存貨與應收成長，未通過）不同：本卡用產業層級、相對自身歷史的庫存狀態當條件，而不是個股的營收品質。與 I005 產業層級營收驚奇（產業輪動，未通過）不同：本卡不交易產業，只問產業狀態是否改變產業內 SUE 的斜率。與 I019 匯率衝擊不同：不使用匯率。

研究點子，非投資建議。
