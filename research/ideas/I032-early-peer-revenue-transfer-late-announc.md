# I032 先公告同業的營收驚奇對後公告者的預測：資訊移轉是反應不足還是過度反應

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過 | B | 事件研究（每月窗口）＋Fama-MacBeth | free | 約 0（月營收、create_time、價格皆已快取；第 501–1000 名 create_time 已確認 499 檔有 2026-05 起的值）；選做：子產業分類已有 config/subindustry_pit.csv | 2026-10-20 |

## 假設

同產業『習慣在每月 7 日前公告』的公司營收驚奇平均（PeerSUE），可預測『習慣在 9 日後公告』的同業自己的 SUE；並且 (a) 擴散版：PeerSUE 高的後公告者，在自身公告窗口（第 8 日收盤 → 公告期限次一交易日收盤）報酬較高；或 (b) 過度反應版（Thomas 與 Zhang 2008）：後公告者在同業公告期間的跟漲幅度越大，自身公告窗口報酬越低。

## 機制（為什麼會有超額報酬）

同產業公司的月營收有共同的需求成分，先公告者的資訊可用來預測後公告者。若投資人注意力有限，後公告者的價格在自身公告前只部分反映同業消息（反應不足，Ramnath 2002 一類）；若投資人過度外推同業消息，後公告者在同業公告時漲過頭，自身公告時回吐（Thomas 與 Zhang 2008）。台股的特點是月營收公告集中在每月 1–10 日、各公司的公告日相當固定，所以每個月都有一個可預先知道『誰先誰後』的窗口，事件數遠多於季報。

## 出處

- Thomas & Zhang（2008）Overreaction to Intra-Industry Information Transfers?，Journal of Accounting Research 46(4):909–940，https://ideas.repec.org/a/bla/joares/v46y2008i4p909-940.html：後公告者對先公告者盈餘的股價反應，與後公告者自身公告時的反應負相關，市場高估了外溢（摘要）【同儕審查】
- Industry classification and the efficiency of intra-industry information transfers（2014）American Journal of Business，https://doi.org/10.1108/ajb-03-2013-0014：以 GICS 重做 Thomas 與 Zhang，指出近年交易活躍後這個過度反應異常消失（摘要與二手摘要）【同儕審查】
- On the efficiency of intra-industry information transfers: The dilution of the overreaction anomaly（2015）Journal of Banking & Finance，https://doi.org/10.1016/j.jbankfin.2015.08.013：同一異常的稀釋（只讀到題目）【同儕審查，未讀摘要】
- On the Use of Intra-Industry Information to Improve Earnings Forecasts（1999）Journal of Business Finance & Accounting，https://doi.org/10.1111/1468-5957.00292：同業較早的盈餘揭露可改善時間序列預測，但較能預測暫時性成分（摘要）【同儕審查】
- Information transfers in Nordic stock exchanges（2010）Aalto University 碩士論文，https://openalex.org/W2595397081：研究市場能否用先公告者資訊估計後公告者盈餘（摘要，未讀結論）【學位論文】
- 本專案 docs/sue_event_entry_report.md：月營收公告後的漂移大部分集中在公告當下一兩天；習慣日 + 1 日進場扣成本前 +2.1%／年【本專案實證】

## 台股適用性

沒有找到台股月營收的同業資訊移轉實證。最大限制是歷史公告日：FinMind 月營收 create_time 只有 2026-05 起才等於實際公告日，所以只能用各公司 2026-05 ~ 10 的公告習慣代表歷史（與 sue_event_entry 的做法相同，當時估計習慣日 + 1 日的前視比例約 2–3%）。快速實測（2026 年成員、2026-05 ~ 10 共 6 個月）：前 500 名中，6 個月全部在 7 日以前公告者 71 檔、全部在 9 日以後公告者 139 檔；有 ≥ 2 檔先公告同業的產業內，後公告者 66 檔（10 個產業）。第 501–1000 名：先公告 47 檔、後公告 138 檔，可配對的後公告者 63 檔。若歷史習慣穩定，每月約 60 個後公告事件，2019–2026/04 約 5,000 個公司月。可交易性：窗口只有 2–4 個交易日，現股來回成本約 0.6%；只有效果很大或改用股票期貨（I031）才可能交易。

## 所需資料

- FinMind TaiwanStockMonthRevenue（已快取）：SUE 與 2026-05 起的 create_time（公告習慣日）
- FinMind TaiwanStockPrice（已快取）：窗口報酬
- config/universe_mcap_membership.csv、config/subindustry_pit.csv：產業與子產業

## 檢定計畫（看結果前固定）

- 樣本：前 500 名主樣本、第 501–1000 名驗證；2019-01 ~ 2026-04（營收月份）；兩段 2019–2022 / 2023–2026/04；2026-05 以後的報酬不使用（只用 2026-05 ~ 10 的公告日期來分類）。
- 分類（看結果前固定）：先公告者 = 2026-05 ~ 10 每次都在 7 日（含）以前公告；後公告者 = 每次都在 9 日（含）以後公告；其餘不用。依公司固定，不隨月份改變。
- 訊號：PeerSUE = 同產業先公告者 SUE 的平均（至少 2 檔，否則該月不用）；PeerReact = 後公告者在第 1 個交易日開盤到第 8 日收盤的報酬減加權指數報酬（同業公告期間的跟漲幅度）。
- (1) 基本面移轉：Fama-MacBeth，後公告者自身 SUE 對 PeerSUE（控制後公告者上月 SUE）；係數 > 0、全期 t > 2 才繼續。
- (2) 擴散檢定：後公告者自身公告窗口報酬（第 8 日收盤 → 公告期限次一交易日收盤，扣加權指數）對 PeerSUE 與 PeerReact 的 Fama-MacBeth，控制 log 市值、前 20 日報酬。
- 通過標準：(2) 中 PeerSUE 係數（擴散）或 PeerReact 係數（過度反應，預期為負）其中一個兩段同號、全期 t > 2，且驗證樣本同號；並且依係數形成的前後三分之一報酬差 > 0.6%（現股來回成本），否則只記錄、改由 I031 的期貨成本重新評估。
- 只報告：只用 2023–2026/04（較接近 2026 年公告習慣）的結果；改用子產業的結果；早公告者 SUE 對後公告者之後 20 日報酬（確認是否只是 I005 產業動能的重現）。

## 與已測點子的關係

- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue, 營收驚奇
- 月營收驚奇的連續性（延續 vs 中斷連串）（failed，docs/sue_streak_report.md）：命中 sue
- 工作日（交易日）調整的月營收驚奇（failed，docs/sue_workday_report.md）：命中 交易日
- 月營收依公告日提早進場（failed，docs/sue_event_entry_report.md）：命中 early announcer
- 美股大型科技公司財報反應對台股連結股的延遲傳遞（客戶／同業財報 → 台灣供應鏈）（card:已測：未通過，research/ideas/I016-us-earnings-to-taiwan-linked-stocks.md）：命中 information transfer
- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 SUE
- 工作日（交易日）調整的月營收驚奇：去除春節與連假造成的年增率雜訊（card:已測：未通過，research/ideas/I026-workday-adjusted-sue.md）：命中 sue
- 補充：與已測點子的差別：I005 產業層級營收驚奇是在所有公司都公告後，用整個產業的平均 SUE 做月度產業輪動；本卡只看 1–10 日之間『先公告 → 尚未公告』的窗口，預測對象是後公告者自身的營收與公告反應。sue_event_entry 用的是公司自己的 SUE；short_term_reversal 的領先落後用的是價格；I016 是跨市場的價格連結。這次可能不同的理由：本專案已確認漂移集中在公告當下（sue_event_entry），而這張卡正是試著在後公告者公告前，用已公開的同業營收預先站位。限制：歷史公告日只能用 2026 年習慣代表，且窗口短、成本高，所以列 B。


## 結果（2026-10-21）

未通過：(1) 後公告者 SUE 對 PeerSUE 係數 +0.716 / +0.113（全期 t 1.4），驗證樣本為負；PeerSUE 對窗口報酬無擴散（前後三分之一 +0.06%）；PeerReact 迴歸係數 t −8.6 但與前 20 日報酬共線，直接分組差只有 −0.09%。見 [docs/peer_transfer_report.md](../../docs/peer_transfer_report.md)。

研究點子，非投資建議。
