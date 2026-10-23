# I054 fv5 換倉日的成交價格：當日收盤 vs 隔日開盤 vs 隔日均價近似 vs 三日分批（訊號不變，只改執行）

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過 | A | 執行面比較（fv5 建構不變，只改成交價格） | free | 約 0（前 500 名 TaiwanStockPrice 含開高低收已快取 2019–2026/04；台指期 TaiwanFuturesDaily 已快取） | 2026-10-23 |

## 假設

fv5 換倉日（公告期限次一交易日）的收盤價對多方腿偏高、對空方腿偏低（收盤集合競價的同向買賣壓力），因此改在隔日開盤或分批成交，每次換倉的執行價差（相對當日收盤）在兩段期間都為正，扣成本後年化淨報酬提高至少 0.3%。

## 機制（為什麼會有超額報酬）

制度與流動性：月營收公告期限後第一個交易日，大量依營收資訊調倉的買賣集中在收盤集合競價（台股 13:25–13:30），可能形成暫時的價格壓力，隔夜部分回復。美股證據顯示收盤價常偏離收盤時的買賣報價中點，且偏離在收盤後與隔夜回復。反方向的風險是 SUE 漂移本身：延後一天進場會少賺一天的漂移（本專案已知依公告日提早進場扣成本前多 +2.1%／年），兩者孰大需實證。

## 出處

- （工作論文，將刊於 Journal of Financial Markets）Bogousslavsky 與 Muravyev（2023）Who trades at the close? Implications for price discovery and liquidity，https://aeaweb.org/conference/2021/preliminary/paper/H9T4hef7：美股收盤價常偏離收盤報價中點，偏離約一半在收盤後很快回復、其餘在隔夜回復（依摘要）
- （同儕審查）Lou、Polk 與 Skouras（2019）A tug of war: Overnight versus intraday expected returns，Journal of Financial Economics 134(1)，https://doi.org/10.1016/j.jfineco.2019.03.011：不同類型投資人偏好在開盤或盤中交易，造成隔夜與盤中報酬的系統性差異（作為開盤 vs 收盤成交價差的背景）
- （本專案）docs/sue_event_entry_report.md：依公告習慣日提早進場，前 500 名扣成本前 +2.1%／年（t 5.1）、扣成本後 −0.8%；docs/effective_signals.md：SUE 延後進場 1–10 日仍有效
- （本專案）docs/effective_signals.md 失敗清單：隔夜／盤中報酬拆解作為選股訊號無效（本卡不是訊號，而是同一名單的成交時點）

## 台股適用性

台股開盤與收盤都用集合競價（開盤 08:30–09:00 撮合、收盤 13:25–13:30），開盤價與收盤價都是可實際成交的價格；隔日均價近似 (O+H+L+C)/4 需拆單或券商演算法單，對個人投資人只能近似，列為樂觀上限。漲跌停：隔日開盤即漲停的多方股票買不到，需照實處理（順延或放棄）。台指期 08:45 開盤，與現股開盤時間差 15 分鐘，避險腿用台指期開盤價近似。沒有台灣的收盤價格壓力實證，需自行檢定。

## 所需資料

- FinMind TaiwanStockPrice（已快取）：open、max、min、close、成交量
- FinMind TaiwanStockSplitPrice、DividendResult（已快取）：還原與除息處理
- FinMind TaiwanFuturesDaily TX（已快取）：避險腿開盤與結算價
- fv5 回測名單與權重：analysis/ls_turnover.py、analysis/borrow_capacity.py 的建構（只讀取）

## 檢定計畫（看結果前固定）

- 樣本：fv5 回測 2019-03 ~ 2026-04，前 500 名，名單、權重、借券條件 D、三份錯開、台指期對沖完全不變；兩段 2019–2022 / 2023–2026/04；2026-05 以後不用。
- 執行版本（事前固定，只有這四個）：P0 當日收盤（現行）；P1 隔日開盤；P2 隔日 (O+H+L+C)/4（VWAP 樂觀近似）；P3 當日收盤、隔日收盤、第三日收盤各 1/3。進場與出場（換倉賣出、回補）用同一版本；台指期避險同步（P1 用 TX 開盤，P2 用 TX (O+H+L+C)/4，P3 同樣分三日）。
- 漲跌停：該執行時點的價格等於漲停（買進）或跌停（賣出／放空）時，該筆順延到下一個可成交的同版本時點，最多 3 日，仍不成交則放棄並以現金計；報告各版本的順延與放棄比例。
- 主要指標：(1) 每次換倉、每條腿的執行價差 = 版本成交價 ÷ P0 價格 − 1（多方取負號、空方取正號，正值代表較有利），以換倉日為單位的配對差，報告兩段的平均與 t（Newey-West 落後 2）；(2) 扣成本後 fv5 的年化淨報酬、Sharpe、最大回撤。
- 成本：單邊 0.29625% + 借券費（同 fv5），各版本成本相同（不假設拆單降低滑價，避免偏向 P2、P3）。
- 通過標準：某版本相對 P0 的年化淨報酬差 ≥ +0.3%，兩段同號，且每次換倉的配對差全期單尾 t > 2；三個替代版本做 Holm 校正（家族 5%）。P2 即使通過，也只能在確認券商有可用的均價或拆單工具後採用。
- 附帶報告（不做判定）：多方腿與空方腿分開的執行價差；依 SUE 分數極端程度（前 10% vs 其餘）分組，檢查價格壓力是否集中在最極端的股票。
- 採用方式：若通過，另立平行前瞻規格（例如 fv5x 的執行變體）或由使用者決定直接修改執行說明；不改 fv5 已登錄的回測與前瞻計算。
- 資料窺探：本專案已看過『延後進場 1–10 日仍有效』與『依公告日提早進場』的結果，知道 SUE 對時點不敏感，屬部分已知資訊；但從未比較開盤、收盤與均價的成交差，四個版本事前固定，不再增加。

## 與已測點子的關係

- 用股票期貨執行 fv5（前置追蹤誤差檢查未過）（failed，docs/futures_exec_report.md）：命中 execution, fv5
- 高股息 ETF 換股（0056／00878／00919 等）公告後的價格壓力與生效後反轉（card:已測：未通過，research/ideas/I003-high-dividend-etf-rebalance.md）：命中 價格壓力, price pressure
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 fv5
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- fv5 腿內逆變異數／逆標準差權重（candidate，docs/smallcap_invvol_report.md）：命中 fv5
- 隔夜／盤中報酬拆解（failed，docs/reversal_signals_report.md）：命中 overnight return
- 臺灣50（0050）季度換股：用市值排名事前預測納入／刪除（card:已測：未通過，research/ideas/I001-tw50-rebalance-predicted.md）：命中 price pressure
- MSCI 季度調整：台股標準指數納入／刪除的公告到生效效果（card:已測：勉強通過（候選），research/ideas/I002-msci-taiwan-rebalance.md）：命中 price pressure
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 fv5
- 用股票期貨執行 fv5：以期交稅取代證交稅、以期貨空單取代借券（card:停止：追蹤誤差未過，research/ideas/I031-fv5-single-stock-futures-execution.md）：命中 implementation
- 中小型股（市值第 501–1000 名）執行面前置檢查：容量、滑價、漲跌停、借券與避險工具（card:已測：L2、S 未過（只做統計檢定），research/ideas/I042-smallcap-execution-precheck.md）：命中 執行
- 補充：與『月營收依公告日提早進場』（失敗）不同：那張卡改變進場日期與換手；本卡日期與名單都不變，只比較同一天前後的成交價格。與隔夜／盤中拆解（訊號，失敗）也不同，本卡不選股。

研究點子，非投資建議。
