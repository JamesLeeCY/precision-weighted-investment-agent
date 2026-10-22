# I051 fv5 家族的合併規格與前瞻採用規則：三項修改同時使用（fv5e＋fv5s＋fv5v）的交互作用，以及多重比較下的事前決策程序

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：fv5x 回測通過（已另立前瞻）；採用規則改為波動調整後報酬差 | B | 濾網或加權（fv5 建構比較）＋前瞻決策程序（事前登錄） | free | 約 0（fv5、fv5e、fv5s、fv5v 回測所需資料皆已快取；前瞻紀錄在 forward/） | 2026-10-22 |

## 假設

把 fv5e（金融股用自結盈餘驚奇）、fv5s（0.25 權重借券餘額 ts_rank）、fv5v（腿內逆標準差權重）三項修改同時套用的 fv5x，在 2019–2026/04 回測中全期 Sharpe 高於任何單一修改（fv5s 1.78 為最高），且兩段都不低於 fv5；同時，以 fv5 家族回測的期間差異標準差估計，24 個前瞻期數不足以分辨 fv5 與任何一個修改版（檢定力 < 50%）。

## 機制（為什麼會有超額報酬）

三項修改作用在不同地方（金融股的訊號來源、全體分數加入借券資訊、腿內權重），預期大致可加總；但 fv5s 的改善集中在 2023 年後、fv5v 的改善集中在 2019–2022，兩者合併可能讓兩段都較穩。另一方面，目前有 4 個平行前瞻規格各自與 fv5 兩兩比較，沒有多重比較校正；每段報酬差的雜訊大，24 期很可能只是在追雜訊（本專案已算過財報 Agent 需約 73 期才達 t = 2）。事前寫死採用規則，可避免看到前瞻結果後挑最好的。

## 出處

- （本專案）docs/fin_esue_followup_report.md、docs/ts_rank_report.md、docs/smallcap_invvol_report.md：fv5e 全期 1.68、fv5s 1.78、fv5v 1.83（2023 年後略低於 fv5）vs fv5 1.64；三者都是看過結果後的修改
- （本專案）docs/forward_validation.md：fv5e、fv5s、fv5v 的前瞻檢定都是『24 期時與 fv5 的平均差 > 0 且本身 t > 2』，沒有多重比較校正
- （同儕審查）DeMiguel、Garlappi 與 Uppal（2009）Optimal versus naive diversification: How inefficient is the 1/N portfolio strategy?，Review of Financial Studies 22(5)，經 https://doi.org/10.1287/mnsc.2016.2497 之摘要轉引：估計誤差下，最適化組合難以勝過等權（作為資金在各規格間等分的依據）
- （工作論文）Ledoit 與 Wolf（2008）Robust performance hypothesis testing with the Sharpe ratio，Journal of Empirical Finance 15(5)，https://ideas.repec.org/p/zur/iewwpx/320.html：報酬厚尾或有時間序列相依時，用 studentized 時間序列 bootstrap 比較兩個 Sharpe（依摘要）

## 台股適用性

純組合層級與決策程序，不涉及新訊號；用既有回測與前瞻紀錄即可。主要限制：三項修改都是在看過前 500 名回測後才定的，fv5x 的回測數字必然含選擇偏誤，所以回測只用來檢查交互作用（是否互相抵消），採用與否只能看 2026-05 以後的前瞻。

## 所需資料

- 既有程式：analysis/fv5_fin_esue.py（fv5e）、analysis/ts_rank_validate.py（fv5s 合成）、analysis/fv5_invvol.py（fv5v）
- 前瞻紀錄：forward/fv5、fv5e、fv5s、fv5v 的 periods.csv、segments.csv（只用於事後依本卡規則判定，不用於回測）
- 自結損益序列 data_cache/events/self_earnings_series.csv（已快取）

## 檢定計畫（看結果前固定）

- 樣本：fv5 回測（2019-03 ~ 2026-04，市值前 500 名，三份錯開、條件 D、台指期對沖、單邊 0.29625% + 借券費）；兩段 2019–2022 / 2023–2026/04；2026-05 以後不用於回測。
- fv5x 定義（事前固定，不調參）：金融股分數依 fv5e 規則替換 → 全體分數 = 0.75 × 該分數產業內百分位 + 0.25 × S1 產業內百分位（同 fv5s）→ 名單與借券條件同 fv5 → 腿內逆標準差權重（同 fv5v，含重查條件 D）。另報告 4 個兩兩組合與『資金四等分給 fv5、fv5e、fv5s、fv5v』的等分組合。
- 回測判定（只決定是否另立 fv5x 前瞻，不取代任何規格）：(1) fv5x 全期 Sharpe > 1.78（目前最高的單一修改 fv5s），(2) 兩段都不低於 fv5（1.45 / 1.87），(3) 三項修改的邊際貢獻（fv5x 減去拿掉某一項）都 ≥ 0。全部成立才另立 fv5x 平行前瞻。
- 檢定力分析（事前固定）：用回測的每段報酬差（各規格 − fv5）的平均與標準差，計算 24、48、72 期時單尾 t > 2 的檢定力；報告『達 80% 檢定力所需期數』。
- 前瞻採用規則（本卡登錄後即生效，取代各規格原本的兩兩規則）：24 個 live 期數時，對每個平行規格 k 計算每段淨報酬差 d_k = k − fv5 的單尾 t（Newey-West 落後 1）；對全部平行規格做 Holm 校正，家族顯著水準 10%；只有通過校正、且規格本身 t > 2 者才可取代 fv5；多個通過時選 d_k 平均最大者。另報告 Ledoit–Wolf bootstrap 的 Sharpe 差信賴區間（只報告）。若檢定力分析顯示 24 期檢定力 < 50%，則 24 期只做警訊檢查（d_k 平均 < 0 且 t < −1 者停止記錄），正式判定延到檢定力達 50% 的期數。
- 未通過回測判定時，不另立 fv5x；前瞻採用規則仍照常適用於既有的 fv5e、fv5s、fv5v。

## 與已測點子的關係

- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5, 自結盈餘, 金融股
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 自結盈餘, 金融股, fv5
- 金融股自結盈餘驚奇低換手多空（緩衝換倉）（failed，docs/fin_esue_followup_report.md）：命中 自結盈餘, 金融股
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 權重, fv5
- 借券賣出餘額比相對自身歷史（ts_rank）——與 SUE 合成（effective，docs/ts_rank_report.md）：命中 ts_rank, 借券
- 金融股自結盈餘驚奇的低換手多空（緩衝換倉）（card:已測：未通過，research/ideas/I017-financial-esue-low-turnover-ls.md）：命中 自結盈餘, 金融股
- 借券賣出餘額比、借券費率、增量、需求量（partial，docs/lending_legs_report.md）：命中 借券
- 每月自結損益驚奇（金控、銀行與少數按月公告公司）（candidate，docs/self_earnings_report.md）：命中 自結盈餘
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- 融資餘額比、外資持股比例的 ts_rank（failed，docs/ts_rank_report.md）：命中 ts_rank
- 年度盈餘驚奇改用實際董事會決議日（failed，docs/earnings_board_date_report.md）：命中 盈餘驚奇
- 季報盈餘驚奇（failed，docs/revenue_surprise_plus_report.md）：命中 盈餘驚奇
- 產業內相對估值（failed，docs/effective_signals.md）：命中 pe ratio
- 每月自結損益驚奇：金控、銀行與少數公司按月公告的自結稅後盈餘（card:已測：通過（可交易性弱），research/ideas/I015-monthly-self-reported-earnings-surprise.md）：命中 自結盈餘
- 非金融按月自結公司的盈餘驚奇：同月 ESUE 相對 SUE 的增量（card:待確認，research/ideas/I038-nonfinancial-esue-increment.md）：命中 自結盈餘
- 相對自身歷史的時間序列排名（ts_rank）：借券賣出餘額比、融資餘額比、外資持股比例（card:已測：S1 通過（S2、S3 未通過），research/ideas/I040-ts-rank-own-history-chip-fields.md）：命中 ts_rank
- PTT 股版討論量暴增（相對自身歷史）：散戶注意力代理，Google 搜尋熱度為穩健性（card:待確認，research/ideas/I041-ptt-discussion-surge-attention.md）：命中 ts_rank
- 中小型股（市值第 501–1000 名）執行面前置檢查：容量、滑價、漲跌停、借券與避險工具（card:待確認，research/ideas/I042-smallcap-execution-precheck.md）：命中 借券
- 補充：不是新訊號，而是把 I018（fv5e）、I040 S1（fv5s）、I033 W2（fv5v）合併並為四個平行前瞻規格補上事前的多重比較與檢定力規則。回測部分有選擇偏誤，所以通過門檻設為『不低於最好的單一修改』而非僅高於 fv5。需使用者確認是否同意以本卡規則取代各規格原本登錄的兩兩比較（改變已登錄的評估方式應在任何 live 期數出現前完成）。

研究點子，非投資建議。
