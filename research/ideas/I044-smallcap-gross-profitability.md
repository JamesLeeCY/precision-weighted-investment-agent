# I044 中小型股的獲利能力因子：毛利÷總資產（GP/A）高的第 501–1000 名股票之後報酬較高

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過 | A | 橫斷面 IC（季頻訊號、月頻評估）＋ Fama-MacBeth；通過後作為 I043 合成第二版的候選 | free | 約 520（第 501–1000 名 TaiwanStockFinancialStatements 缺 8 檔；第 1001–1500 名 FinancialStatements 511 檔，與 I043 共用，若 I043 已抓則為 0；資產負債表全部已快取） | 2026-10-22 |

## 假設

在第 501–1000 名中，近四季毛利 ÷ 平均總資產（GP/A）的產業內排名高的股票，之後第 +2 ~ +61 日報酬高於排名低者，且在控制 SUE、MS、−NSI、−AG、市值、帳面市值比與動能後仍成立；第 1001–1500 名同號。

## 機制（為什麼會有超額報酬）

毛利相對資產的水準代表持續的經濟獲利能力，投資人傾向以帳面上的盈餘或估值判斷、低估高毛利公司未來現金流（Novy-Marx 2013 稱為價值的另一面）。小型股中『垃圾股』（獲利差、風險高、受散戶追捧）比例高，控制品質後小型股溢酬才穩定（Asness 等 2018），代表在中小型股內部用獲利能力區分好壞特別有用。這是水準訊號，與 MS（利潤率的驚奇、變動）不同；季頻更新、換手低，成本負擔小。

## 出處

- Novy-Marx（2013）The other side of value: The gross profitability premium，Journal of Financial Economics，https://doi.org/10.1016/j.jfineco.2013.01.003（同儕審查）：毛利÷總資產對報酬的預測力與帳面市值比相當（本次未讀到摘要內文，依其常被引用的結論轉述，檢定前應補讀）。
- Asness、Frazzini、Israel、Moskowitz 與 Pedersen（2018）Size matters, if you control your junk，Journal of Financial Economics，https://doi.org/10.1016/j.jfineco.2018.05.006（同儕審查）：控制品質（獲利、成長、安全、配息）後，小型股溢酬穩定、不集中在微型股，涵蓋 24 個國際市場（依摘要）。
- Fama 與 French（2008）Dissecting Anomalies，Journal of Finance，https://ideas.repec.org/a/bla/jfinan/v63y2008i4p1653-1678.html（同儕審查）：高獲利伴隨較高異常報酬，但低獲利者沒有明顯偏低（依摘要），提示效果可能主要在做多端。
- 中央大學碩士論文（Fama-French 五因子於台股，1990/07–2020/12，排除金融），https://etd.lib.ncu.edu.tw/thesis/detail/e61ce5f5dbba4c3fac583330c3c986e5（學位論文，依搜尋摘要）：加入獲利因子 RMW 對解釋報酬最有幫助；投資因子方向與美國相反。
- Novy-Marx 與 Velikov（2016），https://www.nber.org/papers/w20721（同儕審查）：獲利能力類策略換手低、容量大。

## 台股適用性

有台灣學位論文支持獲利因子有定價能力，但沒有找到同儕審查的台灣 GP/A 實證，也沒有中小型股分組的證據。台股季報只能用法定期限；總資產與毛利已在快取。風險：(1) 本專案『產業內相對估值』失敗，獲利能力與估值負相關，可能一起失效；(2) 2023 年後由 AI／半導體高成長股主導，高 GP/A 股未必受惠；(3) 本卡的主樣本是第 501–1000 名（獲利能力在任何名次組都還沒看過結果），所以不是事後挑選，但仍要求第 1001–1500 名同號。

## 所需資料

- FinMind TaiwanStockFinancialStatements：Revenue、GrossProfit、OperatingIncome（近四季加總）
- FinMind TaiwanStockBalanceSheet（已快取）：TotalAssets（平均總資產）、Equity
- FinMind TaiwanStockPrice（已快取）：報酬、市值
- 既有程式：analysis/margin_surprise.py（MS）、analysis/net_issuance.py（NSI）、analysis/asset_growth.py（AG）作為控制變數

## 檢定計畫（看結果前固定）

- 樣本：主樣本第 501–1000 名非金融股；確認第 1001–1500 名；前 500 名只報告。2019-07 ~ 2026-04 每月月營收換倉日評估；兩段 2019-07–2022 / 2023–2026/04；2026-05 以後不用。
- 訊號：GP/A = 法定期限已過的最近四季毛利合計 ÷（期初與期末總資產平均）；總資產 ≤ 0 或缺四季者剔除；每期 1%／99% 截尾。次要（只報告）：營業利益近四季 ÷ 總資產（OP/A）。產業內百分位。
- 評估：產業內 Spearman IC（GP/A 對第 +2 ~ +61 日報酬；20 日只報告），Newey-West 落後 3；每月 Fama-MacBeth：60 日報酬 = GP/A + SUE + MS + (−NSI) + (−AG) + log 市值 + 帳面市值比 + 12-1 月報酬 + 產業固定效果（各變數為百分位 − 0.5）。
- 分組描述（只報告）：產業內五分位等權平均 60 日報酬，看效果是否主要在做多端（Fama 與 French 2008 的提示）。
- 通過標準（事前固定）：(1) 主樣本 60 日 IC 兩段皆 > 0、全期 t > 2；(2) Fama-MacBeth 控制後 GP/A 係數全期 t > 2；(3) 第 1001–1500 名 60 日 IC 同號且 t > 1.65。三者皆成立才算通過。
- 通過後：不直接改 I043 已凍結的 v1 權重；另立『I043 v2 = v1 + GP/A』只在 2026-05 以後的前瞻資料比較（因為 GP/A 的挑選用到了第 501–1000 名的結果）。可交易成本：單邊 0.29625% + I042 額外滑價，依 I042 建構。
- 未通過即停止，不換成 ROE、OP/BE 等其他定義重測。

## 與已測點子的關係

- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 小型股, small cap, 501-1000, sue
- 小型股版月營收驚奇：第 501–1000 名獨立多空，以及前 1000 名廣度版本（card:已測：階段一未通過（接近），research/ideas/I030-smallcap-sue-501-1000.md）：命中 小型股, 中小型股, 第 501–1000 名, small cap
- 中小型股（市值第 501–1000 名）執行面前置檢查：容量、滑價、漲跌停、借券與避險工具（card:待確認，research/ideas/I042-smallcap-execution-precheck.md）：命中 中小型股, 小型股, small cap, 501-1000
- 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）（card:待確認，research/ideas/I043-smallcap-multifactor-composite.md）：命中 中小型股, small cap, 501-1000, sue
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 12-1 動能、持續性動能、frog-in-the-pan（failed，docs/revmom_persist_report.md）：命中 動能
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 補充：與 I037 MS（利潤率『變動』的驚奇）差別：本卡是獲利『水準』。與財報 Agent（電子股 100 檔綜合分數，partial）差別：本卡是單一、事前定義的學術因子，樣本是中小型股。與『產業內相對估值』（failed）不同族，但兩者相關，要在 Fama-MacBeth 控制帳面市值比。

研究點子，非投資建議。
