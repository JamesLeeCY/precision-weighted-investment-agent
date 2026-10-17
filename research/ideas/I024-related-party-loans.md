# I024 關係人資金往來（其他應收款—關係人）：資金被關係人占用的公司之後報酬較低

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 停止：事件數不足 | C | 事件研究（配對控制） | free（已快取）；次要事件需 manual 分類 | FinMind 約 0（TaiwanStockBalanceSheet 已快取 2,154 檔）；選做的重大訊息門檻公告：公開資訊觀測站約 300 次（2019–2026 共 8 年 × 2 市場 × 每年約 16 頁 × 主旨檢索） | 2026-10-17 |

## 假設

合併資產負債表中『其他應收款—關係人』占總資產比率 ≥ 1%，或比去年同季增加 0.5 個百分點以上的非金融股，在財報法定期限後 60 個交易日的報酬低於同產業、市值與 SUE 相近、比率為 0 的配對股。

## 機制（為什麼會有超額報酬）

掏空（tunneling）：控制股東或集團透過公司間借款把資金移出上市公司，合併報表中對子公司的借款會互相抵銷，剩下的『其他應收款—關係人』多半是對未合併的關聯企業、母公司或其他關係人的資金融通，代表小股東權益可能被侵占、資金回收有風險；市場若對財報附註資訊反應不足，股價會延遲反映。

## 出處

- Jiang, Lee & Yue（2010）Tunneling through intercorporate loans: The China experience，Journal of Financial Economics 98(1):1–20，https://ideas.repec.org/a/eee/jfinec/v98y2010i1p1-20.html：1996–2006 年中國數百家上市公司的控制股東透過公司間借款移出大量資金；評估其經濟後果與審計師、法人、監理的角色（摘要；摘要未提到股價可預測性，本次未讀全文，不引用報酬數字）【同儕審查】
- Contemporary Accounting Research（2019）How Aggressive Tax Planning Facilitates the Diversion of Corporate Resources，https://doi.org/10.1111/1911-3846.12563：以中國上市公司揭露的公司間借款衡量掏空（摘要）【同儕審查】
- Tunneling through related-party loan guarantees: evidence from a quasi-experiment in China，Review of Quantitative Finance and Accounting 47(3)，https://ideas.repec.org/a/kap/rqfnac/v47y2016i3d10.1007_s11156-015-0523-3.html：關係人背書保證作為掏空管道（只看到標題）【同儕審查，未讀】

## 台股適用性

沒有找到台灣的直接實證，主要證據來自中國（控制股東掏空嚴重、治理環境不同）。本次在快取中抽查 567 檔有資產負債表的股票：2022 年以後曾出現非 0『其他應收款—關係人』的只有 144 檔，這 144 檔的最高占總資產比中位數 0.44%，超過 1% 的 34 檔、超過 5% 的 11 檔。也就是台股多數公司這個項目為 0 或很小，訊號只集中在少數公司，事件數可能不足以分兩段與驗證樣本檢定。台灣另有『資金貸與及背書保證處理準則』的門檻公告（重大訊息，2024 年上市公司約 1,600 則，多數是對子公司），可作為次要事件來源，但需要文字分類。

## 所需資料

- FinMind TaiwanStockBalanceSheet（已快取）：OtherReceivablesDueFromRelatedParties、AccountsReceivableDuefromRelatedPartiesNet、TotalAssets
- 公開資訊觀測站 ajax_t51sb10 主旨檢索（keyWord=背書保證／資金貸與，本次實測 2024 年上市 16 頁）：選做的事件來源
- FinMind TaiwanStockPrice、TaiwanStockMonthRevenue（已快取）：報酬、配對用 SUE

## 檢定計畫（看結果前固定）

- 樣本：前 500 名非金融成員，財報期別 2018Q4 ~ 2025Q4，事件日 = 法定期限的次一交易日（無實際公告日，保守）；兩段 2019–2022 / 2023–2026/04；驗證樣本第 501–1000 名；2026-05 以後不使用。
- 事件定義（事前固定）：高占用 = 其他應收款—關係人 ÷ 總資產 ≥ 1%；增加 = 比去年同季增加 ≥ 0.5 個百分點；同一公司連續多季符合時，只取第一次（之後 4 季內不重複計入）。
- 主檢定：corp_event_study.matched 配對控制（同事件日、同產業、市值三分位、SUE 三分位、事件前 60 日報酬三分位相同、且比率為 0 的股票），報告第 +2 ~ +61 日配對差額的平均、t 值（依事件月份群集）與事件數。
- 前置檢查（看報酬前）：先數每段的事件數；若主樣本任一段 < 40 個事件，改為只報告前 1000 名合併樣本的方向，不下通過結論。
- 通過標準：(1) 配對差額兩段皆 < 0、全期 t < −2；(2) 驗證樣本方向相同；(3) 作為 fv5 做多名單排除濾網時兩段 Sharpe 不降。

## 與已測點子的關係

- fv5 的金融股改用自結盈餘驚奇排序（card:已測：通過（改善小），research/ideas/I018-fv5-financials-esue-score.md）：命中 金融股, SUE
- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 sue
- 財報 Agent（營收、毛利、存貨、應收）（partial，forward/REPORT.md）：命中 財報
- 金融股自結盈餘驚奇低換手多空（緩衝換倉）（failed，docs/fin_esue_followup_report.md）：命中 金融股
- fv5 的金融股改用自結盈餘驚奇排序（candidate，docs/fin_esue_followup_report.md）：命中 金融股
- 年度盈餘驚奇改用實際董事會決議日：年報公告後的盈餘漂移（PEAD）（card:已測：未通過，research/ideas/I007-annual-earnings-surprise-actual-board-da.md）：命中 法定期限
- 季報盈餘驚奇改用實際公告日：公開資訊觀測站重大訊息的財報董事會日期（card:暫緩（I007 顯示 2023 後無可交易漂移），research/ideas/I008-quarterly-pead-actual-announcement-date.md）：命中 法定期限
- 金融股自結盈餘驚奇的低換手多空（緩衝換倉）（card:已測：未通過，research/ideas/I017-financial-esue-low-turnover-ls.md）：命中 金融股
- 補充：與已測點子無關鍵字重疊。與財報 Agent（部分有效，含應收帳款）的差別：財報 Agent 看營業應收的週轉，本卡看非營業的關係人資金占用。列為 C 的原因：台股大型股中這個項目多為 0，事件可能太少；證據來自治理環境不同的中國。資料成本為 0，可在測資產成長卡時順便做前置檢查（事件數）再決定。


## 結果（2026-10-17）

前置檢查（未看報酬）：主樣本事件數 2019–2022 40 個、2023–2026/04 18 個，低於門檻 40，依點子卡不做主檢定。見 [docs/asset_growth_report.md](../../docs/asset_growth_report.md)。

研究點子，非投資建議。
