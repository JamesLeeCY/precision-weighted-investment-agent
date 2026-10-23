# I053 fv5 家族前瞻的輔助判定：以機制指標（增量 IC、日頻波動比）加非劣性檢定，縮短判定時間（不取代已登錄規則）

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：輔助判定規則已登錄（2026-10-24） | A | 前瞻決策程序（事前登錄，輔助判定）＋回測檢定力校準 | free | 約 0（回測資料皆已快取；live 部分重用 fv5／fv5s／fv5v／fv5x 前瞻每月已抓的價格與借券資料） | 2026-10-23 |

## 假設

fv5 家族各修改的『機制指標』在 live 期間比組合報酬差更快達到顯著：fv5s 的 S1 產業內增量 IC 約 12–40 個月可達單尾 t > 2、fv5v／fv5x 的日頻報酬變異數比（規格 ÷ fv5）約 6 個月內即可判定 < 1；而把每段報酬差改成日頻報酬差，平均差的 t 值不會提高（同一日曆期間下兩者等價）。

## 機制（為什麼會有超額報酬）

統計原理，不是超額報酬來源：平均報酬的估計精度只取決於日曆期間長度與波動，提高抽樣頻率無法改善（Merton 1980）；變異數則可用高頻資料精確估計。fv5v 的改善本質是降波動，可用日頻資料快速確認；fv5s 的改善來自 S1 訊號，橫斷面 IC 每期平均 500 檔，雜訊遠小於組合報酬差。fv5e 只涉及約 37 檔金融股，機制指標檢定力仍低，只報告。把『機制已確認』與『報酬未明顯變差（非劣性）』分開檢定，可在 76–302 段之前提供有依據的輔助判斷。

## 出處

- （同儕審查）Merton（1980）On estimating the expected return on the market: An exploratory investigation，Journal of Financial Economics 8(4)，https://nber.org/papers/w0444：平均報酬的標準誤隨日曆期間而非抽樣頻率下降；變異數可用高頻資料精確估計（依摘要與二手摘要）
- （期刊文章）Ledoit 與 Wolf（2011）Robust performance hypothesis testing with the variance，Wilmott Magazine（工作論文版 https://ideas.repec.org/p/zur/iewwpx/516.html）：報酬厚尾與序列相關時，以 studentized 時間序列 bootstrap 檢定兩策略的變異數比，F 檢定不可靠
- （同儕審查）Ledoit 與 Wolf（2008）Robust performance hypothesis testing with the Sharpe ratio，Journal of Empirical Finance 15(5)，https://ideas.repec.org/p/zur/iewwpx/320.html：Sharpe 差的穩健檢定（作為對照報告）
- （本專案）docs/fv5_family_voladj.md：波動調整後每段報酬差達 50% 檢定力需 fv5x 76、fv5e 105、fv5s 131、fv5v 302 個月度段
- （本專案）docs/ts_rank_report.md：S1 60 日產業內 IC 全期 t 5.3，控制 SUE 等後 t 3.0（2019-03 ~ 2026-04，約 86 個月）

## 台股適用性

純統計設計，不受台股制度影響；所需的每日權重已記錄在 forward/*/predictions.csv，日報酬可由權重與收盤價事後重建（不改前瞻紀錄）。粗估（假設 t 值隨月數平方根成長、live 效果等於回測）：S1 增量 IC 約 86 ×（2/3.0）² ≈ 38 個月、未控制版約 86 ×（2/5.3）² ≈ 12 個月達 t = 2；若 live 效果只有回測一半，月數變為 4 倍，需事前接受這個風險。

## 所需資料

- forward/fv5、fv5e、fv5s、fv5v、fv5x 的 predictions.csv（每檔權重、分數）與 segments.csv
- FinMind TaiwanStockPrice（已快取，前瞻每月更新）：重建日頻組合報酬
- FinMind TaiwanDailyShortSaleBalances（已快取）：S1 分數；data_cache/events/self_earnings_series.csv：金融股 ESUE
- 回測程式 analysis/fv5_family.py、analysis/fv5_family_voladj.py、analysis/ts_rank_validate.py（只讀取，計算檢定力）

## 檢定計畫（看結果前固定）

- 樣本：回測 2019-03 ~ 2026-04（前 500 名，只用來校準檢定力，不用來決定規格）；live 為 2026-05 起各前瞻規格紀錄，回填段與 live 段分開報告。
- D0 等價性檢查（先做）：在回測中把 fv5x − fv5 的每段差改為日頻差（同一期間加總），比較兩者平均差的 t 值（Newey-West，日頻落後 20 日）；預期差異 < 10%。若日頻 t 明顯較大，先查原因（多半是序列相關未處理），不得據此改規則。
- 機制指標 M_s（fv5s、fv5x 的 S 部分）：每個換倉日，前 500 名產業內 Fama-MacBeth 迴歸，60 日報酬百分位 ~ SUE 百分位 + S1 百分位，取 S1 係數；以月度序列計算單尾 t（Newey-West 落後 2，因 60 日視窗重疊）。
- 機制指標 M_v（fv5v、fv5x 的 V 部分）：日頻淨報酬的變異數比 ρ = Var(規格) ÷ Var(fv5)，用 Ledoit–Wolf（2011）時間序列 bootstrap（區塊長度 20 日、5,000 次）檢定 ln ρ < 0；回測 ρ 約 (3.5/4.5)² ≈ 0.60。
- 機制指標 M_e（fv5e）：金融股內 ESUE 與 SUE 的 60 日 IC 差，只報告（約 37 檔，檢定力低）。
- 非劣性 N_k：波動調整後每段報酬差 d_k（同 forward/compare_family.py 的定義與固定縮放係數）的 90% 單尾信賴下界 > −0.05%／段（約 −0.6%／年，事前固定的容忍幅度）。
- 檢定力校準：用回測估計 M_s、M_v、N_k 在 6、12、24、36 個月時的檢定力（以回測效果的 100% 與 50% 兩種假設各報一次），寫入報告後才開始計算 live 值。
- 輔助判定（不取代 I051 與 forward_validation.md 已登錄的規則）：規格 k 的機制指標通過（M_s、M_v 兩項做 Holm 校正，家族單尾 10%）且 N_k 通過，標記為『機制確認、報酬非劣』，提交使用者決定是否提前採用；正式規則照常計算。
- 警訊：live 12 個月以上時，任一機制指標 t < −1，標記為『機制失效』並建議停止該規格的記錄（由使用者決定）。
- 成本：沿用各規格既有成本模型（單邊 0.29625% + 借券費、台指期 0.005%），不另加。
- 通過標準（本卡本身）：D0 等價性成立，且檢定力校準顯示至少一個機制指標在 24 個月內檢定力 ≥ 50%（以回測效果 50% 的保守假設），才建議使用者登錄輔助規則；否則只保留 D0 的結論（提高頻率無助於平均差），不登錄。
- 資料窺探：S1 與逆標準差權重都是看過前 500 名回測後才定的，回測 IC 偏樂觀，所以檢定力用 50% 縮減情境；live 值是唯一判準。多重檢定：本卡只有兩個機制指標進入 Holm 校正，M_e 只報告。

## 與已測點子的關係

- fv5 家族的合併規格與前瞻採用規則：三項修改同時使用（fv5e＋fv5s＋fv5v）的交互作用，以及多重比較下的事前決策程序（card:已測：fv5x 回測通過（已另立前瞻）；採用規則改為波動調整後報酬差，research/ideas/I051-fv5-family-combined-spec-decision-rule.md）：命中 fv5 家族, 檢定力, fv5x
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 fv5
- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 fv5
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5
- 補充：延伸 I051：I051 的決策規則以組合報酬差為唯一指標，需 76–302 段。本卡不改已登錄規則，只新增事前固定的輔助指標；是否登錄需使用者在看到任何 live 機制指標之前決定。

研究點子，非投資建議。
