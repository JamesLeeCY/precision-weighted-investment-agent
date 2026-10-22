# I043 中小型股多因子合成：SUE ＋ 利潤率驚奇 MS ＋ 淨發行 −NSI ＋ 資產成長 −AG（事前固定權重，第 1001–1500 名確認）

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過（階段 1 過、階段 2 t 2.8） | B | 橫斷面 IC＋Fama-MacBeth（新樣本確認）→ 可交易建構（依 I042 門檻）→ 前瞻 | free | 約 2,565（第 501–1000 名約 10 次：TaiwanStockFinancialStatements 缺 8 檔；第 1001–1500 名 511 檔 × 5 個資料集 ≈ 2,555 次：MonthRevenue、FinancialStatements、Shareholding、DividendResult、SplitPrice；價格與資產負債表已快取；免費每小時 600 次，約 4.5 小時，與 I044 共用） | 2026-10-22 |

## 假設

在第 501–1000 名與從未使用過的第 1001–1500 名中，合成分數 C = 0.5 × SUE 百分位 + (1/6) × (MS + (−NSI) + (−AG) 百分位) 高的股票，之後第 +2 ~ +61 日的產業內報酬較高；而且扣掉 SUE 後的非 SUE 子合成 X =（MS、−NSI、−AG 百分位平均）在控制 SUE、市值、帳面市值比與動能後仍有正向預測力。

## 機制（為什麼會有超額報酬）

四個成分各自代表不同的反應不足或錯誤定價：SUE 是對月營收資訊的反應不足；MS 是對季報利潤率（營收以外）資訊的反應不足；淨發行與資產成長是公司在股價偏高時發行、擴張（市場時機與過度投資），投資人對其後續報酬下降反應不足。文獻顯示這類錯誤定價集中在小型、套利成本高的股票（Fama 與 French 2008；Hou、Xue 與 Zhang 2020），合成可以分散單一訊號的雜訊（Stambaugh 與 Yuan 的錯誤定價因子即為多個異常的平均排名）。本專案的經驗與此一致：MS、−NSI、−AG 在前 500 名不成立、在第 501–1000 名顯著，且與 SUE 幾乎不相關。

## 出處

- Fama 與 French（2008）Dissecting Anomalies，Journal of Finance 63(4)，https://ideas.repec.org/a/bla/jfinan/v63y2008i4p1653-1678.html（同儕審查）：淨發行在各規模組都存在；資產成長效果只出現在微型與小型股、大型股沒有（依摘要）。
- Hou、Xue 與 Zhang（2020）Replicating Anomalies，Review of Financial Studies 33(5)，https://doi.org/10.1093/rfs/hhy131（同儕審查）：用 NYSE 分界與市值加權壓低微型股影響後，452 個異常中 65% 的 |t| < 1.96；差異主要來自微型股。
- Stambaugh 與 Yuan，Mispricing Factors，NBER 工作論文 w21533（後刊於 Review of Financial Studies），https://www.nber.org/papers/w21533：以 11 個異常分兩群、平均排名建構錯誤定價因子；投資人情緒主要預測其放空腿（依摘要）。
- Harvey、Liu 與 Zhu（2016）…and the Cross-Section of Expected Returns，Review of Financial Studies 29(1)，https://doi.org/10.1093/rfs/hhv059（同儕審查）：在大量因子被測試後，新因子應採更高門檻（約 t > 3）；本卡用來設定第 501–1000 名內的增量門檻。
- Novy-Marx 與 Velikov（2016）A Taxonomy of Anomalies and Their Trading Costs，Review of Financial Studies，https://www.nber.org/papers/w20721（同儕審查）：交易成本讓所有異常的報酬與顯著性下降，作者把此連到資料窺探；緩衝換倉最能降低成本。
- 本專案（同一資料、事後觀察，非獨立證據）：docs/margin_surprise_report.md（MS 第 501–1000 名 60 日 IC +0.061，t 5.6）；docs/nonfin_esue_issuance_report.md（−NSI 第 501–1000 名 60 日 IC +0.035，t 3.2）；docs/asset_growth_report.md（−AG 第 501–1000 名 60 日 IC +0.046，t 4.0，但 2023 年後 +0.022，t 1.5；單獨多空年化 −5.5%）；docs/smallcap_invvol_report.md（SUE 第 501–1000 名 20 日 IC +0.050，t 6.1）。

## 台股適用性

台股月營收制度讓 SUE 在大小型股都有效；MS、−NSI、−AG 只在中小型股有效，符合國際文獻『異常集中在小型股』的型態。限制：(1) 這三個成分是看過第 501–1000 名結果後才挑出來的，第 501–1000 名不能再當獨立證據，必須用新樣本（第 1001–1500 名）或前瞻資料確認；(2) 第 1001–1500 名的成交值中位數每年只有約 170 萬–790 萬元，只能做統計確認、不能交易；(3) 可交易版本依 I042 的結果決定建構；(4) 季報訊號（MS、AG）只能用法定期限（Q1 5/15、Q2 8/14、Q3 11/14、Q4 3/31），中小型股多半接近期限才公告，延遲問題比大型股小。

## 所需資料

- config/universe_mcap_membership.csv 擴充到第 1500 名：用 data/universe_mcap.build_membership(top_n=1500) 只讀快取重建（2026-10-22 已試算：0 次請求、前 1000 名排名與現有檔案完全一致；第 1001–1500 名 8 年聯集 511 檔）；存為新檔，不覆蓋原檔
- FinMind TaiwanStockMonthRevenue：SUE
- FinMind TaiwanStockFinancialStatements：MS（營業利益率變動扣季營收年增率）
- FinMind TaiwanStockBalanceSheet（已快取 1001–1500 名 511/511）：AG（總資產年增率）
- FinMind TaiwanStockShareholding、TaiwanStockDividendResult、TaiwanStockSplitPrice：NSI（依 analysis/net_issuance.py 的配股調整）
- FinMind TaiwanStockPrice（已快取）：報酬、市值、動能
- I042 的借券、滑價、避險結果（可交易階段）

## 檢定計畫（看結果前固定）

- 資料窺探的處理（事前寫明）：MS、−NSI、−AG 是看過第 501–1000 名結果後挑的，所以 (a) 權重不最佳化：SUE（在前 500 名事前已驗證）占 0.5，其餘三個平分 0.5；(b) 主要確認在從未使用的第 1001–1500 名；(c) 第 501–1000 名只當開發樣本，增量要求 t > 3（Harvey 等 2016）；(d) 通過後凍結規格，2026-05 以後的前瞻記錄才是最終判準；(e) 不加入其他成分（I028 營收品質是交互作用結果、I040 借券 ts_rank 只報告），不調整定義、視窗與權重。
- 樣本：開發樣本第 501–1000 名、確認樣本第 1001–1500 名（無存活偏誤，每年初依市值排名）；2019-07 ~ 2026-04 每月的月營收換倉日（公告期限次一交易日 +0、+1 收盤進場）；報酬視窗須在 2026-05 前結束；兩段 2019-07–2022 / 2023–2026/04。前 500 名只報告。
- 訊號（全部沿用既有程式的定義）：SUE 同 fv5；MS 同 I037（法定期限已過的最新一季，非金融）；NSI 同 I029（12 個月對數股數變化，扣配股與分割）；AG 同 I020（總資產年增率，法定期限後可用）。每個成分在同一名次組內、產業內轉成百分位；缺值以 0.5 計；金融保險業只用 SUE 與 NSI。C = 0.5·SUE + (1/6)·(MS + (−NSI) + (−AG))；X = (MS + (−NSI) + (−AG)) / 3。
- 階段 1（確認，第 1001–1500 名）：(1) C 的產業內 Spearman IC（對第 +2 ~ +61 日報酬），Newey-West（落後 3）；(2) 每月 Fama-MacBeth：60 日報酬 = SUE 百分位 + X + log 市值 + 帳面市值比 + 12-1 月報酬 + 產業固定效果。通過：X 的係數兩段皆 > 0 且全期 t > 2；C 的 60 日 IC 兩段皆 > 0、全期 t > 2。
- 階段 2（開發樣本增量，第 501–1000 名）：每月 IC(C) − IC(SUE) 的平均，Newey-West 全期 t > 3 且兩段皆 > 0。
- 階段 3（可交易，第 501–1000 名，階段 1、2 與 I042 的 L 門檻都通過才做）：依 I042 決定 T1（產業內前／後 1/3 多空、條件 D、台指期補 β）或 T2／T3（只做多 + 中型期貨或台指期避險）；三份錯開、每 3 個換倉日換倉；成本 = 單邊 0.29625% + I042 的單邊額外滑價估計 + 借券費；資金 5,000 萬與 I042 找到的最大 K；參與率上限 10%（超過部分縮小權重、剩餘現金不投入）。對照：同建構只用 SUE。
- 階段 3 通過標準：Sharpe 兩段皆 > 0.5、全期 ≥ 1.0，且兩段都高於同建構的 SUE 單獨版本；與 fv5 的日報酬相關 < 0.5；fv5 與本策略資金各半的組合全期 Sharpe 高於 fv5 單獨（1.64）。任一不成立即停止，不另找建構。
- 前瞻：通過後以 git commit 凍結規格（另立 forward 規格，與 fv5 平行），2026-11 起記錄，24 個 live 期數時依事前規則比較。
- 只報告：等權四成分版本；加入 I040 借券 ts_rank 的版本；第 501–750 名與第 751–1000 名；上市與上櫃分列；20 日視窗；前 500 名。

## 與已測點子的關係

- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 小型股, small cap, 501-1000, sue
- 小型股版月營收驚奇：第 501–1000 名獨立多空，以及前 1000 名廣度版本（card:已測：階段一未通過（接近），research/ideas/I030-smallcap-sue-501-1000.md）：命中 小型股, 中小型股, 第 501–1000 名, small cap
- 中小型股（市值第 501–1000 名）執行面前置檢查：容量、滑價、漲跌停、借券與避險工具（card:待確認，research/ideas/I042-smallcap-execution-precheck.md）：命中 中小型股, 小型股, small cap, 501-1000
- 淨發行股數（股本膨脹）：過去 12 個月經配股調整後股數增加多的股票之後報酬較低（card:待確認，research/ideas/I029-net-share-issuance.md）：命中 淨發行, net share issuance, share issuance
- 資產成長（投資）異常（failed，docs/asset_growth_report.md）：命中 資產成長, asset growth
- 資產成長（投資）異常：總資產年增率高的股票之後報酬較低（card:已測：未通過，research/ideas/I020-asset-growth.md）：命中 資產成長, asset growth
- 營收已知下的利潤率驚奇：季報營業利益率相對月營收隱含水準的驚奇（card:待確認，research/ideas/I037-operating-margin-surprise-given-revenue.md）：命中 利潤率驚奇, margin surprise
- 非金融按月自結公司的盈餘驚奇：同月 ESUE 相對 SUE 的增量（card:待確認，research/ideas/I038-nonfinancial-esue-increment.md）：命中 利潤率驚奇, margin surprise
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 權重
- 融資餘額比、外資持股比例的 ts_rank（failed，docs/ts_rank_report.md）：命中 margin
- 12-1 動能、持續性動能、frog-in-the-pan（failed，docs/revmom_persist_report.md）：命中 動能
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 補充：直接建立在 I030（小型股 SUE）、I037（MS）、I029（NSI）、I020（AG）之上；這些卡在前 500 名都判為未通過，本卡不是重測它們，而是把『中小型股有效』這個事後觀察拿到新樣本確認，並給出可交易建構。與 I020（2/3 SUE + 1/3 −AG 合成，前 500 名全期 1.50）差別：樣本改為中小型股、成分改為四個、確認在新樣本。優先度依請求數（> 1,000）為 B，但它是本批的主要目標，建議在 I042 之後第一個做。

研究點子，非投資建議。
