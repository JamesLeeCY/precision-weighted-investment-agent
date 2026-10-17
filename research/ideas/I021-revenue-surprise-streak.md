# I021 月營收驚奇的連續性：延續同號連串的驚奇漂移較強、中斷連串的驚奇漂移較弱

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 待確認 | B | 濾網或加權（SUE 條件分組） | free（已快取） | 約 0（前 500 名月營收、價格已快取；第 501–1000 名若月營收未快取約 0–580 次） | 2026-10-17 |

## 假設

同樣是 SUE 位於產業內前 30% 的股票，若本月是連續第 3 個月以上 SUE > 0（延續連串），之後 20 與 60 個交易日的報酬高於本月 SUE 由負轉正（中斷負向連串）者；SUE 後 30% 的股票方向相反。

## 機制（為什麼會有超額報酬）

賭徒謬誤（gambler's fallacy）：投資人看到連續幾次好消息後，傾向認為『該反轉了』，因此對延續連串的新驚奇反應不足，漂移較強；連串中斷時投資人本來就預期反轉，反應較完整。Loh & Warachka（2012）在美國季盈餘發現連串可解釋約一半的盈餘公告後漂移。台灣月營收每年 12 次，連串比季盈餘更常見、更容易被散戶看到（媒體常報導『連 N 月成長』），檢定力也比季資料高。

## 出處

- Loh & Warachka（2012）Streaks in Earnings Surprises and the Cross-Section of Stock Returns，Management Science 58(7):1305–1321，https://ideas.repec.org/a/inm/ormnsc/v58y2012i7p1305-1321.html：最近一次驚奇延續同號連串時，盈餘公告後漂移強且顯著；連串中斷後漂移可忽略；連串約解釋一半的漂移，控制驚奇大小與自我相關後仍成立（摘要）【同儕審查】
- Rabin（2002）Inference by Believers in the Law of Small Numbers，Quarterly Journal of Economics（Loh & Warachka 摘要引用的理論來源，本次未讀）【同儕審查，未讀】
- 本專案 docs/revenue_surprise_report.md、docs/revmom_persist_report.md：SUE 有效；年增率加速與 SUE 相關約 0.5、合成反而稀釋；營收創新高單獨有效但合成增量不穩健【本專案實證】

## 台股適用性

沒有找到台灣月營收連串的實證。台股月營收的優點是頻率高、每檔每年 12 次，所以連串與中斷的樣本數充足。風險：連串長度與 SUE、營收創新高、年增率加速高度相關，可能只是 SUE 的另一種寫法（同族變體），本卡用『同一 SUE 分組內比較延續 vs 中斷』來隔離連串本身的資訊；若條件差異不顯著就停止，不再做合成。

## 所需資料

- FinMind TaiwanStockMonthRevenue（已快取）：SUE 與連串長度
- FinMind TaiwanStockPrice＋除權息還原（已快取）：報酬
- fv5 的建構程式（analysis/ls_turnover.py、forward 規格）：合成版本比較

## 檢定計畫（看結果前固定）

- 樣本：前 500 名成員，2019-01 ~ 2026-04 的每月營收公告（SUE 計算沿用本專案定義，需要 24 個月歷史）；分兩段 2019–2022 / 2023–2026/04；驗證樣本第 501–1000 名；2026-05 以後不使用。
- 連串定義（事前固定）：streak = 本月往回數、SUE 同號（SUE > 0 或 < 0）的連續月數，含本月，上限 6；『延續』= streak ≥ 3；『中斷』= 本月與上月 SUE 異號，且上月之前已有 ≥ 2 個月與上月同號（即本月打斷一個長度 ≥ 2 的連串）。
- 進場與持有：沿用 SUE 慣例，營收公告期限的次一個交易日收盤進場，持有 20 與 60 個交易日。
- 主檢定：每月在產業內把 SUE 分三組；在 SUE 前 30% 組內，延續組 − 中斷組的 20 日報酬差（等權），依月份群集標準誤；SUE 後 30% 組做同樣比較（預期延續組更差）；報告兩段與全期。
- 迴歸：r_i,m+1 = a + b1·SUE + b2·streak（帶符號）+ b3·SUE×I(延續) + 產業固定效果，Fama-MacBeth，報告 b2、b3。同時報告 streak 與 SUE、營收創新高的平均橫斷面相關。
- 可交易版本：fv5 規格（前 500 名、等權多空、借券條件 D、每 3 個月換倉三份錯開、台指期對沖，成本單邊 0.29625%＋借券費）中，把排序分數改為 SUE 排名與帶符號 streak 排名各半，與 fv5 原版比較；事前只測這一個權重，不調參。
- 通過標準：(1) SUE 前 30% 組的延續 − 中斷兩段皆 > 0、全期 t > 2（後 30% 組同號方向作為輔證）；(2) 迴歸中 b2 或 b3 控制 SUE 後全期 t > 2 且兩段同號；(3) 驗證樣本方向相同；(4) 合成版扣成本後兩段 Sharpe 都不低於 fv5 原版。只有 (1)(2) 成立才做 (4)。

## 與已測點子的關係

- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 月營收驚奇, sue, 營收驚奇
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE, 月營收驚奇, earnings surprise
- 年度盈餘驚奇改用實際董事會決議日（failed，docs/earnings_board_date_report.md）：命中 earnings surprise
- 季報盈餘驚奇（failed，docs/revenue_surprise_plus_report.md）：命中 earnings surprise
- 月營收驚奇 × 低法人關注：注意力低的股票漂移較強（條件分組與加權）（card:已測：未通過，research/ideas/I004-sue-x-low-attention.md）：命中 conditional drift
- 每月自結損益驚奇：金控、銀行與少數公司按月公告的自結稅後盈餘（card:已測：通過（可交易性弱），research/ideas/I015-monthly-self-reported-earnings-surprise.md）：命中 earnings surprise
- 補充：與月營收驚奇 SUE（有效）屬同一資訊來源，只有在能增加不同資訊時才值得做：本卡檢定的是『連串是否改變投資人對同一大小驚奇的反應』，而不是另一個營收成長指標。與年增率加速、3 個月年增率（部分有效，合成稀釋）的差別：那些是營收水準的變化率；本卡是驚奇符號的時間序列型態。若主檢定不通過，代表連串資訊已被 SUE 吸收，應停止。

研究點子，非投資建議。
