# I005 產業層級營收驚奇：同產業多數公司營收驚奇後的產業輪動

| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |
|---|---|---|---|---|---|
| 已測：未通過 | B | 橫斷面 IC（產業層級）＋產業多空 | free | 約 0（前 300／500 的月營收與股價已快取）；選做：用第 501–1000 名成員一起算產業平均 SUE 以降低雜訊，需約 580 次月營收請求 | 2026-10-15 |

## 假設

每月營收公告後，產業平均 SUE（成員 SUE 截尾後平均）較高的產業，之後 20–60 個交易日的產業等權報酬高於產業平均 SUE 較低的產業（跨產業 Spearman IC > 0）；產業前 1/3 減後 1/3 的多空扣成本後為正，且與 fv3（產業中性）多空的日報酬相關接近 0。

## 機制（為什麼會有超額報酬）

行為偏誤（產業資訊逐步擴散）：產業共同的需求或景氣訊息分散在數十家公司的月營收裡，投資人逐家看、不加總，產業整體的資訊被低估；Hou（2007）發現領先落後主要是產業內現象，且與大型公司公告後小型公司的漂移有關。Moskowitz & Grinblatt（1999）顯示個股動能大部分來自產業動能。若產業動能背後是基本面消息（營收），用營收直接建構產業訊號應比用價格更早、更乾淨。

## 出處

- （同儕審查）Moskowitz & Grinblatt（1999）Do Industries Explain Momentum?，Journal of Finance 54(4)，https://doi.org/10.1111/0022-1082.00146：產業動能解釋大部分個股動能；控制規模、淨值市價比與個股動能後，產業動能仍獲利，1 個月期最強
- （同儕審查）Hou（2007）Industry Information Diffusion and the Lead-lag Effect in Stock Returns，Review of Financial Studies，https://doi.org/10.1093/revfin/hhm003：大小型股的領先落後主要發生在產業內，受負面消息的緩慢調整驅動；小型、競爭較少、被忽略的產業效果較強
- （同儕審查）Hong, Lim & Stein（2000）Bad News Travels Slowly，Journal of Finance，https://doi.org/10.1111/0022-1082.00206：資訊逐步擴散的實證基礎
- （同儕審查）Information diffusion of upstream and downstream industry-wide earnings surprises and its implications（2017），Review of Quantitative Finance and Accounting，https://doi.org/10.1007/s11156-017-0687-0：產業整體盈餘驚奇沿上下游擴散（只看到標題，摘要不可得）
- （同儕審查）Thinking Outside the Borders: Investors' Underreaction to Foreign Operations Information（2015），Review of Financial Studies，https://doi.org/10.1093/rfs/hhv039：以產業層級報酬建構的資訊訊號，月超額約 0.8%，屬同類『產業資訊反應不足』證據
- （同儕審查，台灣）Foreign institutional industrial herding in Taiwan stock market（2012），Managerial Finance，https://doi.org/10.1108/03074351211201442：外資在台股有產業層級的群聚買賣，並檢驗其對之後產業報酬的影響（摘要未給數字）
- （論壇，只當假設來源）PTT〈[請益] 先佈局低基期族群等資金輪動可行嗎？〉https://www.ptt.cc/bbs/Stock/M.1778424459.A.5E0.html ；〈[新聞] 台塑四寶9月營收全紅〉https://www.ptt.cc/bbs/Stock/M.1791808608.A.396.html：散戶以『族群營收同步轉強』作為輪動依據

## 台股適用性

台股族群輪動明顯，月營收又是全市場同月公告，產業加總很自然；但沒有找到以台股月營收建構產業訊號的學術實證（lit 只找到美國產業動能與資訊擴散）。主要限制：(1) 產業數少：2024 年市值前 300 名共 34 個 sector，成員 ≥ 5 檔的只有 20 個；前 500 名為 38 個、≥ 5 檔 28 個；跨產業 IC 每期只有 20–28 個觀察值，雜訊大、檢定力低。(2) 半導體業在前 500 名約 86 檔、前 300 名約 61 檔，市值加權版本會被台積電主導，所以主規格用產業內等權。(3) 等權持股相對市值加權台指期有結構差（leg_pool 報告），所以不用『做多產業 − β × 台指期』當主規格，而用產業多空或相對股票池等權基準的超額。(4) 金融保險業有延後申報（15 日前）問題，主規格排除該產業。(5) 產業分類用 universe_mcap_membership.csv 的 sector（TWSE 產業別），『其他』『其他電子業』異質性高，另做排除這兩類的穩健性。

## 所需資料

- FinMind TaiwanStockMonthRevenue（已快取）：各股 SUE（data/revenue_signal.revenue_surprise）
- FinMind TaiwanStockPrice（已快取）：還原報酬，組成產業等權與市值加權報酬
- FinMind TaiwanFuturesDaily TX、TaiwanStockTotalReturnIndex（已快取）：β 對沖與市場基準
- config/universe_mcap_membership.csv：sector 欄與市值排名

## 檢定計畫（看結果前固定）

- 樣本：主樣本市值前 500 名（產業較多、每產業成員較多）；次要前 300 名；換倉日同 leg_probe.prepare 的 schedule（2019-01 至 2026-04，約 88 期）；分 2019–2022 與 2023–2026/04 兩段；2026-05 以後不用。只納入該期成員 ≥ 5 檔的產業；排除金融保險業。
- 訊號（主要）：ISUE_k = 產業 k 在該期所有成員原始 SUE 截尾到 [−3, 3] 後的等權平均。次要（同號才算穩健，不作主判準）：廣度 = 成員中 SUE > 0 的比例；市值加權平均 SUE。每期在產業之間排名，所以只測產業輪動，不測大盤擇時。
- 控制：同時報告產業過去 1 個月與 12−1 個月等權報酬（產業價格動能）、以及公告期間（上月底 → 進場前一日）產業報酬，並做 Fama-MacBeth：產業報酬對 ISUE、產業 1 個月報酬、產業 12−1 報酬回歸，看 ISUE 係數是否仍為正。
- 檢定一（跨產業 IC）：每期 ISUE 與產業等權 fwd20、fwd40、fwd60 報酬的 Spearman IC；88 期平均，t 值用 Newey-West（重疊視窗 lag = 1、2）。
- 檢定二（產業多空）：每期依 ISUE 排名，做多前 1/3 產業、放空後 1/3 產業；產業內等權持有全部成員，產業之間等權；放空只用可借條件 D（borrow_capacity，資金 2 億）的股票；剩餘 β 以台指期對沖。持有 1 個月（每期換倉）與 3 個月（三份錯開，同 ls_turnover 的寫法）兩種，事先以 3 個月為主規格。
- 檢定三（與 fv3 的關係）：報告產業多空與同股票池 fv3 等權多空（ls_turnover 3 個月 + 緩衝 + 條件 D）的日報酬相關（預期接近 0，因 fv3 產業中性、產業權重等於股票池權重）；並以兩者波動相同的 50/50 合成，比較合成 Sharpe 與 fv3 單獨。
- 成本：股票單邊 0.29625%（換手兩邊皆扣）、借券費逐日扣、台指期單邊 0.005%；報告年換手（產業排名翻轉會造成整個產業換股，換手可能高）。
- 穩健性（只報告）：排除半導體業；排除『其他』與『其他電子業』；產業報酬改市值加權；用前 300 名。
- 通過標準（全部成立）：(1) 前 500 名 fwd40 的跨產業 IC 兩段皆 > 0，合併 Newey-West t > 2.5（產業數少，門檻比個股高）；(2) Fama-MacBeth 加入產業價格動能後 ISUE 係數兩段仍 > 0；(3) 主規格產業多空扣成本後 Sharpe 兩段皆 > 0.3；(4) 與 fv3 的 50/50 合成 Sharpe 兩段都高於 fv3 單獨。只有 (1)(2) 成立記為 partial；前 300 名需同號。

## 與已測點子的關係

- 月營收驚奇 SUE（effective，docs/revenue_surprise_report.md）：命中 revenue surprise, sue, 營收驚奇
- 12-1 動能、持續性動能、frog-in-the-pan（failed，docs/revmom_persist_report.md）：命中 動能, momentum
- 月營收驚奇 × 低法人關注：注意力低的股票漂移較強（條件分組與加權）（card:待確認，research/ideas/I004-sue-x-low-attention.md）：命中 資訊擴散
- 補充：與已失敗的『產業領先落後、供應鏈』不同：(a) 領先落後（short_term_reversal_report）是產業內大型股過去 5 日『價格』預測同產業追隨股之後 5 日報酬，屬短週期、產業內、價格；本卡是每月『營收基本面』在產業之間的排名，持有 1–3 個月。(b) 供應鏈 Agent 依 2026 年挑選的 AI 股票與 NVIDIA 下游代理，受選股偏誤汙染，且是 Agent 規則；本卡用無存活偏誤的市值股票池與機械式產業平均。與已失敗的個股 12−1 動能不同：本卡以營收訊號排產業，並把產業價格動能列為控制變數。與 SUE（effective）的關係：fv3 在產業內中性化，丟掉的正是產業間成分；預期兩者日報酬相關接近 0，是補充而非重複。主要風險：產業數少導致檢定力不足、產業多空換手高、等權與市值加權結構差。

研究點子，非投資建議。

## 結果（2026-10-15）

已測：未通過，見 [docs/sue_attention_industry_report.md](../../docs/sue_attention_industry_report.md)。
