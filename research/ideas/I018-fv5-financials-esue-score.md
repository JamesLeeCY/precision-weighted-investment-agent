# I018 fv5 的金融股改用自結盈餘驚奇排序

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：通過（改善小） | B | 組合建構修改（fv5 比較） | free（已快取） | 約 0 | 2026-10-16 |

## 假設

fv5（月營收驚奇 SUE 多空，前 500 名）對金融股也用營收 SUE，但金融業的月營收沒有實質意義。把金融股的排序分數改成自結盈餘驚奇（ESUE），其他股票不變，fv5 兩段 Sharpe 不降、全期提高。

## 機制（為什麼會有超額報酬）

I015 發現金融股內部 ESUE 前 − 後 +1.06%（t 4.9），且控制營收 SUE 後仍顯著；金融股營收（利息、手續費、投資收益混合）年差的雜訊大，SUE 排序接近隨機。用較有資訊的分數替換，等於提高 fv5 中金融股部位的選股準確度，而不增加換手（仍是每 3 個月換倉）。

## 出處

- 本專案 docs/self_earnings_report.md（I015：金融股內部 +1.06%，t 4.9；fv5 做多濾網版只影響 1.4% 權重、Sharpe 幾乎不變）【本專案回測】
- 本專案 docs/top500_report.md（fv5：前 500 名 SUE 等權多空 1.45 / 1.87）【本專案回測】
- Jegadeesh & Livnat (2006) Post-Earnings-Announcement Drift: The Role of Revenue Surprises, Financial Analysts Journal 62(2), https://doi.org/10.2469/faj.v62.n2.4081：營收驚奇的資訊在不同產業差異大【同儕審查】

## 台股適用性

前 500 名中約 20 家金融股按月公告自結盈餘，占股票池約 4%，對整體 fv5 影響有限但可能改善金融股部位的報酬；其他按月公告自結數的非金融公司（約 17 家）維持用 SUE，避免同時改兩件事。

## 所需資料

- data_cache/events/self_earnings_series.csv（I015 解析，已有）
- fv5 建構所需資料（已快取）

## 檢定計畫（看結果前固定）

- 注意：事後設計、同一段資料；通過後需先前瞻記錄（與 fv5 平行）才能取代 fv5。
- 建構：fv5 完全相同（前 500 名、SUE 等權多空、每 3 個月三份錯開、不含緩衝、借券條件 D、台指期對沖）；唯一差異是換倉日當天，金融股（產業「金融保險」「金融業」）若在過去 45 個交易日內有 ESUE，用 ESUE 在全股票池 SUE 分布中的同分位數值取代其 SUE 分數（先把 ESUE 轉成金融股內百分位，再對應到當日全池 SUE 的同百分位）；沒有 ESUE 的金融股維持 SUE。
- 比較基準：fv5 建構（1.45 / 1.87，全期 1.64）。
- 通過：兩段 Sharpe 都不低於基準 − 0.02，且全期 Sharpe 高於基準；另報告金融股部位單獨的報酬貢獻。
- 只報告：金融股直接排除在 fv5 之外的版本（檢查改善是來自 ESUE 的資訊，還是只是移除 SUE 的雜訊）。

## 與已測點子的關係

- 金融股自結盈餘驚奇的低換手多空（緩衝換倉）（card:待確認，research/ideas/I017-financial-esue-low-turnover-ls.md）：命中 自結盈餘, 自結損益, 金融股, 金控
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 月營收驚奇, sue, 營收驚奇
- 每月自結損益驚奇：金控、銀行與少數公司按月公告的自結稅後盈餘（card:已測：通過（可交易性弱），research/ideas/I015-monthly-self-reported-earnings-surprise.md）：命中 自結損益, 自結盈餘, earnings surprise
- 每月自結損益驚奇（金控、銀行與少數按月公告公司）（candidate，docs/self_earnings_report.md）：命中 自結損益, 自結盈餘
- 年度盈餘驚奇改用實際董事會決議日（failed，docs/earnings_board_date_report.md）：命中 盈餘驚奇, earnings surprise
- 季報盈餘驚奇（failed，docs/revenue_surprise_plus_report.md）：命中 盈餘驚奇, earnings surprise
- 補充：與 I015 (4b) 的差別：(4b) 只在做多名單排除 ESUE 後三分之一（影響 1.4% 權重）；本卡改的是金融股的排序分數本身，同時影響做多與放空端。


## 結果（2026-10-16）

通過：1.51 / 1.88（全期 1.68）vs fv5 基準 1.45 / 1.87（1.64）；金融股部位年化貢獻 +0.42% → +0.62%。改善小，且事後設計，需與 fv5 平行前瞻記錄後才能取代。見 [docs/fin_esue_followup_report.md](../../docs/fin_esue_followup_report.md)。

研究點子，非投資建議。
