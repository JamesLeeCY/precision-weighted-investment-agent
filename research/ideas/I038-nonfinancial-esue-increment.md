# I038 非金融按月自結公司的盈餘驚奇：同月 ESUE 相對 SUE 的增量

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過 | C | 事件研究（合併迴歸） | free | 約 0（自結數值、月營收、價格皆已快取） | 2026-10-21 |

## 假設

對每月同時公告營收與自結損益的非金融公司，同月 ESUE 中無法由 SUE 解釋的部分（利潤率驚奇的月頻版本）高者，第 +2 ~ +21 日報酬高於低者。

## 機制（為什麼會有超額報酬）

非金融公司的月營收已被市場高度關注，同時公告的自結盈餘包含成本面資訊；若投資人只盯營收，利潤率部分會反應不足。與 I037（季報利潤率驚奇）同一機制，但時點即時（每月公告），不受季報法定期限延遲的問題。

## 出處

- 本專案 docs/self_earnings_report.md（I015）：同月 ESUE 前 − 後三分之一第 +2 ~ +21 日 +1.07%（t 2.7）/ +1.34%（t 3.7），控制營收 SUE 後全期 t 2.3；樣本以金融業為主。
- Ertimur、Livnat 與 Martikainen（2003）Review of Accounting Studies，https://doi.org/10.1023/a:1024409311267：同儕審查；營收與費用驚奇的市場反應不同（依摘要轉述）。
- 本次實測（data_cache/events/self_earnings_values.csv，已快取）：自結公告 97.8% 在 13:30 以後發布；非金融公司在當年前 500 名中每年只有 11–15 家（2019 15 家、2023 14 家、2026 11 家），按月公告較完整者約 12 家（如中鋼、豐泰、慧洋-KY、中租-KY、潤泰新、美利達等），2019–2026/04 約 1,100 個公司月。

## 台股適用性

制度可行（公開資訊觀測站自願性每月自結），資料已在快取、0 次新請求。最大問題是公司太少：每月只有約 12–15 家，無法做產業內分組，只能用合併的事件迴歸；結果容易被少數公司（中鋼、中租）主導，而且難以變成可交易組合。

## 所需資料

- data_cache/events/self_earnings_values.csv：自結當月與累計稅前／稅後盈餘
- FinMind TaiwanStockMonthRevenue：同月 SUE
- 已快取的價格

## 檢定計畫（看結果前固定）

- 樣本：2019-01 ~ 2026-04 當年前 1000 名中按月公告自結損益的非金融公司（不含金融保險、證券、租賃以外的金融業；中租-KY 依產業分類為其他，納入但另報告排除後結果）。
- 訊號：ESUE 沿用 I015 定義；R = ESUE 對同月 SUE 的合併迴歸殘差（以 2019–2022 估計係數後固定，套用到 2023 年後，避免前視）。
- 報酬：自結公告日次一交易日為 +1，+1 收盤進場，第 +2 ~ +21 日市場調整報酬；公司固定效果迴歸 CAR 對 R，標準誤以公司與月份雙向群聚。
- 通過標準（事前固定）：R 係數兩段同號為正、全期 t > 2；排除單一最大權重公司後仍同號。只當研究紀錄，即使通過也不建可交易組合（公司數不足），只考慮加入 forward/se 的前瞻觀察。
- 事件數門檻：每段至少 400 個公司月，不足即停止。

## 與已測點子的關係

- 每月自結損益驚奇：金控、銀行與少數公司按月公告的自結稅後盈餘（card:已測：通過（可交易性弱），research/ideas/I015-monthly-self-reported-earnings-surprise.md）：命中 自結損益, 自結盈餘, 月自結, 每月自結, monthly earnings, self-reported earnings
- 每月自結損益驚奇（金控、銀行與少數按月公告公司）（candidate，docs/self_earnings_report.md）：命中 自結損益, 自結盈餘, self-reported earnings, monthly earnings
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 自結盈餘, 自結損益, SUE
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 自結盈餘, esue
- 金融股自結盈餘驚奇的低換手多空（緩衝換倉）（card:已測：未通過，research/ideas/I017-financial-esue-low-turnover-ls.md）：命中 自結盈餘, 自結損益
- 營收已知下的利潤率驚奇：季報營業利益率相對月營收隱含水準的驚奇（card:待確認，research/ideas/I037-operating-margin-surprise-given-revenue.md）：命中 利潤率驚奇, margin surprise
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 金融股自結盈餘驚奇低換手多空（緩衝換倉）（failed，docs/fin_esue_followup_report.md）：命中 自結盈餘
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 小型股版月營收驚奇（第 501–1000 名）（failed，docs/smallcap_invvol_report.md）：命中 sue
- 年度盈餘驚奇改用實際董事會決議日（failed，docs/earnings_board_date_report.md）：命中 盈餘驚奇
- 季報盈餘驚奇（failed，docs/revenue_surprise_plus_report.md）：命中 盈餘驚奇
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 補充：I015 已涵蓋全部按月公告公司並控制 SUE；本卡只把非金融部分切出來看利潤率增量。I017／I018 只處理金融股。因公司數太少，列 C 只做紀錄，建議等 I037 有結果再決定。

研究點子，非投資建議。
