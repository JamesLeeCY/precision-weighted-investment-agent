# 前瞻驗證（forward validation）操作說明

| | |
|---|---|
| 規格 | [forward/spec_fv1.yaml](../forward/spec_fv1.yaml)（2026-10-09 凍結於 git `57c364d`） |
| 程式 | [forward/run_forward.py](../forward/run_forward.py) |
| 紀錄 | [forward/predictions.csv](../forward/predictions.csv)、[forward/outcomes.csv](../forward/outcomes.csv)（只能新增） |
| 報告 | [forward/REPORT.md](../forward/REPORT.md)（每次 `report` 自動產生） |

## 為什麼要做

回測的期間（2019–2026-05）在開發過程中被反覆看過；即使改用無選股偏誤股票池，仍可能有多重比較與期間重疊的問題。唯一乾淨的檢驗，是**把規則凍結，在結果出現之前寫下預測，之後再對答案**。

## 凍結了什麼（fv1）

- **Agent**：只用財報 Agent，連續輸出模式。
- **股票池**：當年的無偏誤成員（`config/universe_pit_membership.csv`），每年 1 月依前 60 個交易日平均成交金額取前 100 檔。
- **時程**：每月第一個交易日預測；持有到之後第 20 個交易日收盤，含息總報酬。
- **主要指標（事先登錄）**：產業內 IC；回測預期平均 +0.029、每期標準差 0.122。
- **評估方式（事先登錄）**：
  - 只有 `live` 期數算入正式檢定，`backfill` 另列。
  - 24 個 live 期數（約 2 年）時，平均 IC < 0 視為失效警訊。
  - 73 個 live 期數（約 6 年）時正式檢定，t > 2 才算確認。

## 完整性機制

| 機制 | 作用 |
|---|---|
| 程式碼指紋 | spec 記錄財報 Agent、評分公式、機率映射、財報公告遞延、含息還原的 SHA-256；任何一段被改，`predict` 會拒絕執行 |
| 只能新增 | 同一個預測日不能預測兩次；結算不會覆寫 |
| 執行紀錄 | 每筆預測記錄 UTC 時間、git commit、是否有未 commit 的修改、規格版本、mode |
| git 時間戳 | 每次預測後 commit 並 push，GitHub 上的時間證明預測寫在結果之前 |
| 資料快照 | 每次執行使用 `data_cache/forward/<抓取日期>/` 的新資料（一般快取不會過期），快照保留在本機作為稽核依據 |

**修改規則的正確做法**：建立新版本（例如 `spec_fv2.yaml`）並從新版本開始累積紀錄，不要更動 fv1 或沿用 fv1 的紀錄。

## 每月操作

每個月第一個交易日（台股開盤前或當天收盤前皆可；預測只用前一天以前公告的財報資料）：

```bash
.venv/Scripts/python forward/run_forward.py predict --as-of YYYY-MM-DD   # 當月第一個交易日；3 天內自動標為 live
.venv/Scripts/python forward/run_forward.py resolve                       # 結算已滿 20 個交易日的預測
.venv/Scripts/python forward/run_forward.py report                        # 更新 forward/REPORT.md
git add forward/ && git commit -m "forward: YYYY-MM prediction" && git push
```

每年 1 月第一個交易日之後、當月預測之前，先建立當年股票池（約 930 次 FinMind 呼叫，約 2 小時）：

```bash
.venv/Scripts/python forward/run_forward.py build-universe --year YYYY
```

查看各預測日的狀態：

```bash
.venv/Scripts/python forward/run_forward.py schedule
```

每次預測與結算各約需 300 次 FinMind 呼叫（免費額度每小時約 600 次，客戶端會自動等待）。

## 自動執行（Windows 工作排程器）

工作 `PrecisionWeightedAgent-ForwardValidation` 每個平日 18:30 執行：

```bash
.venv/Scripts/python forward/run_forward.py auto --push    # 輸出附加到 logs/forward_auto.log
```

`auto` 依序：1 月且當年股票池不存在時 `build-universe` → 當月第一個交易日尚未預測就 `predict` → `resolve` →
有新預測或新結算時 `report`、重新產生研究網站（`site/build_site.py`），再只 commit 前瞻紀錄三個檔案與
`site/data.json`、`site/research-dashboard.html` 並 push。沒有變動就只補推先前失敗的 push。

網站更新失敗（例如快照缺資料又遇到網路錯誤）只會寫進 log，前瞻紀錄照常 commit；下次有變動時網站會再重建。

### 線上網站重新發佈（Claude 桌面 App 排程工作）

線上版在 claude.ai Artifact：<https://claude.ai/artifact/UZu73HRzdmfWJrTG7TizLo>（私人，分享需從頁面的 Share 選單設定）。
發佈 Artifact 只能在 Claude 工作階段中進行，Windows 工作排程器做不到，因此另設一個 Claude 桌面 App 的排程工作：

| | |
|---|---|
| 名稱 | 研究網站自動重新發佈（taskId `republish-research-site`） |
| 時間 | 每個平日 19:15（App 顯示約 19:23；排在 18:30 的 `auto` 之後） |
| 設定檔 | `%USERPROFILE%\.claude\scheduled-tasks\republish-research-site\SKILL.md`（不在 repo 內） |
| 狀態檔 | `logs/site_published.sha256`：上次發佈時 `site/research-dashboard.html` 的 SHA-256（logs/ 不進 git） |

每次執行：

1. 計算 `site/research-dashboard.html` 的 SHA-256，與 `logs/site_published.sha256` 相同就結束（線上已是最新）。
2. 不同時先完整讀取頁面，確認是本專案產生的網站（標題、內嵌數據、免責聲明，沒有外部表單或非允許來源的腳本）；不符就不發佈。
3. 讀取線上 Artifact 後，以同一個網址重新發佈本機檔案。
4. 發佈成功才寫入新的雜湊；失敗不寫，下次執行會重試。

它不修改、不 commit、不 push repo，也不執行 `run_forward.py`。

注意事項：

- 只在 Claude 桌面 App 開著時執行；App 關閉時到期的執行會在下次開啟時補跑。
- 工具權限（PowerShell、Read、Artifact）已在 2026-10-10 首次執行時允許並存在工作上。若執行卡在權限確認，
  到側欄 Scheduled → 研究網站自動重新發佈 打開該次執行並允許；必要時停止後按 Run now 重跑。
- 想強制重新發佈：刪除 `logs/site_published.sha256` 後按 Run now。
- 查看執行紀錄：側欄 Scheduled → 研究網站自動重新發佈 → Runs。

## 已知紀錄瑕疵

- **fv3 / fv4 / fv5 產業內 IC（次要指標，2026-10-14 發現並修正）**：結算程式用 `DataFrame.asof` 取期末價，只要任一檔在期末日缺價（停牌），就會整列退回到所有股票都有值的較早日期，使多數股票的期末報酬用錯日期。受影響的回填段落：fv3、fv4 各 2 段，fv5 3 段。原紀錄保留不改，更正值記在各規格的 `corrections.csv`，報告標示「已更正」；更正後回填 IC 平均 fv3 +0.046、fv4 +0.053、fv5 +0.018。主要指標（每段淨報酬）以每日報酬計算，不受影響；結算程式已改為每檔各自取期末前最後價格（非凍結的規則程式，指紋不變）。

- 回填的 2026-07-01 起四批預測，`git_dirty` 記為 True：當時的檢查把尚未 commit 的 `predictions.csv` 本身算成「未 commit 的修改」。規則程式碼的指紋檢查每次都通過，且四批都記錄同一個 commit `e940168`（新增 spec 檔的 commit，規則程式碼與凍結時的 `57c364d` 相同）。已於 2026-10-10 修正檢查（只看已追蹤檔案、排除前瞻紀錄本身）；既有紀錄依「只能新增」原則不修改。

## 回填（backfill）

2026-06 到 2026-10 在開發時沒有使用過（回測資料只到 2026-05），已在凍結後以 `backfill` 標記補做，作為第一批檢查。回填使用的是今天抓取的資料，若 FinMind 事後修正過歷史財報，會與當時實際可得的資料略有差異，因此不算入正式檢定。


---

# 前瞻驗證 fv2：月營收驚奇（SUE）

| | |
|---|---|
| 規格 | [forward/fv2/spec.yaml](../forward/fv2/spec.yaml)（2026-10-12 凍結於 git `c06469a`） |
| 程式 | [forward/run_forward_fv2.py](../forward/run_forward_fv2.py)、訊號 [data/revenue_signal.py](../data/revenue_signal.py) |
| 紀錄 | `forward/fv2/predictions.csv`（含每檔入選與權重）、`outcomes.csv`、`periods.csv`（每期組合 / 等權 / 0050 / 0050 擇時 / 50-50 的報酬）；只能新增 |
| 報告 | [forward/fv2/REPORT.md](../forward/fv2/REPORT.md) |
| 依據 | [revenue_surprise_report.md](revenue_surprise_report.md)：SUE 是第一個在 2019–2022、2023–2026 兩段都顯著的訊號 |

## 凍結了什麼

- **預測日**：每月「10 日或之後第一個加權指數交易日」（營收公告期限）的下一個交易日。
- **訊號**：SUE =（本月營收 − 去年同月 − μ）÷ σ，μ、σ 為過去 24 個月營收年差的平均與標準差。
  **只採用 create_time ≤ 公告期限交易日的營收**（前瞻期間 FinMind 有收錄時間），避免逾期才公告的資料混入。
- **組合**：當年無偏誤成員，產業內 SUE 前 1/3；已持有者產業內百分位 > 50% 續留；產業權重 = 股票池權重。預測時就寫下每檔權重。
- **持有**：預測日收盤到第 20 個交易日收盤的含息總報酬。
- **主要指標（事先登錄）**：產業內 IC；回測預期平均 +0.044、每期標準差 0.119（88 期，t 3.5）。
- **評估**：只算 live 期數；12 期時平均 IC < 0 視為警訊；30 期（約 2.5 年）時正式檢定，t > 2 才算確認。
- **次要指標**：組合（扣成本）相對等權的每期超額報酬（回測 +0.44%）；50% 組合 + 50%「0050 + 每日 200 日線濾網」相對 0050 買進持有。
- **程式碼指紋**：`data/revenue_signal.py` 全檔、選股、期間報酬計算與常數；改了就拒絕預測（修改規則請建立 fv3）。
- fv1 的規格、紀錄與指紋完全不受影響。

## 回填與排程

- 開發時最後一個事件是 2026-04-13，因此 2026-05 到 2026-09 共 5 期以 `backfill` 補做（不計入正式檢定）。
  4 期已結算：產業內 IC 平均 −0.015（每期標準差約 0.12，4 期無統計意義）。
- 第一個 live 預測日：2026-10-13（10 月公告期限 10-12）。
- 自動執行：`forward/run_forward.py auto` 每個平日 18:30 會一併呼叫 fv2（預測當月、結算到期者、更新報告，並 commit / push fv2 紀錄）；
  fv2 出錯只寫入 log，fv1 照常。

手動操作：

```bash
.venv/Scripts/python forward/run_forward_fv2.py schedule
.venv/Scripts/python forward/run_forward_fv2.py predict --as-of YYYY-MM-DD
.venv/Scripts/python forward/run_forward_fv2.py resolve
.venv/Scripts/python forward/run_forward_fv2.py report
```

# 前瞻驗證 fv3：月營收驚奇等權多空（三份資金錯開、每 3 個月換倉、限制可借、台指期對沖）

| | |
|---|---|
| 規格 | [forward/fv3/spec.yaml](../forward/fv3/spec.yaml)（2026-10-13 凍結於 git `774c33c`） |
| 程式 | [forward/run_forward_fv3.py](../forward/run_forward_fv3.py)；權重 [analysis/ls_turnover.py](../analysis/ls_turnover.py) 的 `ew_ls_buffer`、中性化 [analysis/leg_probe.py](../analysis/leg_probe.py) 的 `neutralize` |
| 紀錄 | `forward/fv3/predictions.csv`（每檔分數、可借、費率、β、權重）、`segments.csv`（每份資金每段的毛報酬／避險／借券費／成本／淨報酬）、`periods.csv`（組合每段淨報酬、產業內 IC、0050）；只能新增 |
| 報告 | [forward/fv3/REPORT.md](../forward/fv3/REPORT.md) |
| 依據 | [borrow_capacity_report.md](borrow_capacity_report.md)、[ls_turnover_report.md](ls_turnover_report.md)、[ls_offsets_top300.md](ls_offsets_top300.md)：三個換倉起點都通過，三份平均回測 Sharpe 0.93 / 1.79 |

## 凍結了什麼

- **預測日**：同 fv2（每月營收公告期限後的下一個交易日）。
- **股票池**：`config/universe_mcap_membership.csv` 當年市值前 300 名；**每年 1 月需先執行 `analysis/build_universe_mcap.py` 建立當年成員**（約 4,300 次 FinMind 呼叫），否則 fv3 會略過並在 log 中提示。
- **分數**：SUE（只採 create_time ≤ 公告期限的營收）→ 產業內 z → 對產業虛擬變數與 log 市值迴歸取殘差。
- **三份資金**：每個預測日只重建一份（第 1、2、3 份輪流），持有到 3 個預測日後；組合 = 三份加總 ÷ 3（回填初期在場不足 3 份時，其餘為現金）。
- **每份**：做多產業內前 1/3、放空後 1/3（只放空可借者），產業內等權、多空各 100%；剩餘 β 以台指期近月對沖。
- **可借**：前 60 個交易日有借券成交、需借股數 ≤ 前一日借券賣出額度、≤ 前 60 日借券成交量的 10%、借券費 ≤ 5%／年（需借股數以 2 億元資金估計）。
- **主要指標（事先登錄）**：組合每段（相鄰兩個預測日之間）扣成本、借券費、對沖後的淨報酬；回測平均 +0.61%／段、標準差 1.88%（85 段，t 3.0）。
- **評估**：只算 live 段數；12 段時平均 < 0 為警訊；38 段（約 3 年）時正式檢定，t > 2 才算確認。
- **注意**：此建構是看過多種組合建構後選出的，回測已含選擇偏誤；前瞻結果才是乾淨的驗證。

## 回填與排程

- 回填 2026-05 ~ 09 共 5 個預測日（`backfill`）；2026-10-13 為第一個 live 預測日。
- 回填期間 `forward/fv3/BACKFILL_PENDING` 存在時，`auto` 會略過 fv3，避免在回填完成前結算段落（紀錄只能新增，結算錯了無法更正）。
- 自動執行：`forward/run_forward.py auto` 在 fv1 / fv2 發佈之後才呼叫 fv3（預測日約 2,100 次 FinMind 呼叫、3–4 小時），並另外 commit / push fv3 紀錄；fv3 出錯只寫入 log。
- fv3 使用自己的快照快取 `data_cache/forward/fv3/<日期>/`；環境變數 `FV3_FETCH_DATE` 可固定抓取日（回填跨午夜時仍命中快取）。

```bash
.venv/Scripts/python forward/run_forward_fv3.py schedule
.venv/Scripts/python forward/run_forward_fv3.py predict --as-of YYYY-MM-DD
.venv/Scripts/python forward/run_forward_fv3.py resolve
.venv/Scripts/python forward/run_forward_fv3.py report
```

# 前瞻驗證 fv4：月營收驚奇 + 營收創新高（fv3 建構）

| | |
|---|---|
| 規格 | [forward/fv4/spec.yaml](../forward/fv4/spec.yaml)（2026-10-13 凍結於 git `e2a25be`） |
| 程式 | [forward/run_forward_fv4.py](../forward/run_forward_fv4.py)（由 fv3 程式產生，只改分數與紀錄位置） |
| 紀錄 | `forward/fv4/`（同 fv3 的 predictions / segments / periods，另多一欄 `rec24`）；只能新增 |
| 報告 | [forward/fv4/REPORT.md](../forward/fv4/REPORT.md) |
| 依據 | [revmom_persist_report.md](revmom_persist_report.md)：營收創新高是第二個兩段都顯著的訊號；與 SUE 各半合成 1.22 / 2.13（SUE 單獨 0.93 / 1.79） |

- **與 fv3 唯一的差別是分數**：SUE 與營收創新高（本月營收 ÷ 前 24 個月最高 − 1）各自產業內 z → 中性化 → 全體 z，兩者平均；任一缺值不入選；兩者都只採 create_time ≤ 公告期限的營收。其餘（股票池、三份資金、可借條件、對沖、成本）與 fv3 相同。
- **主要指標（事先登錄）**：組合每段淨報酬；回測平均 +0.76%／段、標準差 1.95%（85 段，t 3.6）；12 段警訊、26 段（約 2 年）正式檢定 t > 2。
- **與 fv3 比較**：同期 fv4 − fv3 每段淨報酬差只作描述（回測 +2.0%／年，t 1.7），不作為確認條件。
- **共用資料**：fv4 讀 fv3 的快照快取（`data_cache/forward/fv3/<日期>/`），由 auto 在 fv3 之後執行，每月不多花 FinMind 額度；`forward/fv4/BACKFILL_PENDING` 存在時 auto 略過 fv4。
- 營收創新高是同一批 5 個候選中唯一通過判準者，回測數字已含選擇偏誤；前瞻結果才是乾淨的驗證。

```bash
.venv/Scripts/python forward/run_forward_fv4.py schedule
.venv/Scripts/python forward/run_forward_fv4.py report
```

# 前瞻驗證 fv5：fv3 建構、市值前 500 檔

| | |
|---|---|
| 規格 | [forward/fv5/spec.yaml](../forward/fv5/spec.yaml)（2026-10-14 凍結於 git `c5afa73`） |
| 程式 | [forward/run_forward_fv5.py](../forward/run_forward_fv5.py)（由 fv3 程式產生；規則函式與 fv3 完全相同，程式碼指紋一致，只有常數 `TOP_N = 500`） |
| 紀錄 | `forward/fv5/`（同 fv3 的 predictions / segments / periods）；只能新增 |
| 報告 | [forward/fv5/REPORT.md](../forward/fv5/REPORT.md) |
| 依據 | [top500_report.md](top500_report.md)：前 500 檔 SUE 等權多空 1.45 / 1.87（前 300 檔 0.93 / 1.79） |

- **主要指標（事先登錄）**：組合每段淨報酬；回測平均 +0.61%／段、標準差 1.42%（85 段，t 4.0）；12 段警訊、24 段（約 2 年）正式檢定 t > 2。
- **與 fv3 比較**：同期 fv5 − fv3 只作描述，不作為確認條件。
- **共用資料**：讀 fv3 的快照快取，由 auto 在 fv3 / fv4 之後執行；預測日只多約 200 檔 × 7 ≈ 1,400 次 FinMind。
- **注意**：前 500 檔是看過前 300 檔結果後才測的，回測數字已含選擇偏誤。
- 回填 2026-05 ~ 09（backfill）與 2026-10-13（live）；回填期間 `forward/fv5/BACKFILL_PENDING` 存在時 auto 略過 fv5。

## 前瞻記錄 msci：MSCI 臺灣指數季度調整（2026-10-15 建立）

- 程式：`forward/run_forward_msci.py`；紀錄：`forward/msci/`（spec.yaml、events.csv、records.csv、REPORT.md）。
- 研究依據：docs/index_rebalance_report.md（23 次審核，公告到生效的納入 − 刪除 +5.5%、t 2.1，兩段各自不顯著）。
- 規則：MSCI 臺灣（標準型）新增與刪除名單；公布日收盤進場、生效日收盤出場；含息報酬 − 加權指數含息報酬；
  每次審核的「納入 − 刪除」，淨值另扣每邊一買一賣 2 × 0.29625%（不計借券費）。
- 名單登錄：每季公布當天由人工（或排程中的 Claude）用 `fetch` 讀 MSCI PDF、對應代號後以 `add` 登錄；登錄後不得修改。
- 回填：2026-05（淨 +1.68%）、2026-08（淨 −2.06%）在研究期間之後，另列為 backfill。
- 檢定：8 次 live 審核時平均淨報酬 < 0 為警訊；12 次 live 審核（約 3 年）時平均 > 0 且 t > 2 才算確認。
- 每日 `forward/run_forward.py auto` 會呼叫 `run_forward_msci.auto()` 結算生效日已過的審核。

## 前瞻記錄 se：每月自結損益驚奇（2026-10-16 建立）

- 程式：`forward/run_forward_se.py`；紀錄：`forward/se/`（spec.yaml、events.csv、records.csv、REPORT.md）。
- 研究依據：docs/self_earnings_report.md（點子卡 I015；87 個月，同月 ESUE 前三分之一 − 後三分之一 CAR[+2,+21] +1.19%、t 4.4；金融股內部 +1.06%、t 4.9）。
- 規則：每天重抓當年公開資訊觀測站「自結」重大訊息主旨與新公告內文，依 analysis/self_earnings_parse.py（整個檔案雜湊凍結）解析並計算 ESUE；
  事件第一次出現時登錄、之後不改；13:30 以後發言者事件日為下一個交易日；市值前 500 名中每月依 ESUE 分三組，記錄前 − 後的平均 CAR，另記金融股內部。
- 只記錄訊號，不是可交易規格（回測的金融股月度多空扣成本後 Sharpe 0.04 / 0.51）。
- 回填：2026-05 ~ 2026-10 事件月份為 backfill（研究期間之後、凍結之前）；2026-05 ~ 08 平均 +1.29%（t 0.4，4 個月）。live 從 2026-11 起。
- 檢定：12 個 live 月份時平均 < 0 為警訊；24 個 live 月份（約 2 年）時平均 > 0 且 t > 2 才算確認。
- 每日 `forward/run_forward.py auto` 會呼叫 `run_forward_se.auto()`（公開資訊觀測站約 16 次請求；新公告另抓內文；月份結算時約 30 次 FinMind）。

## 前瞻規格 fv5e：fv5 的金融股改用自結盈餘驚奇排序（2026-10-16 建立）

- 程式：`forward/run_forward_fv5e.py`；紀錄：`forward/fv5e/`（spec.yaml、predictions.csv、segments.csv、periods.csv、REPORT.md）。
- 研究依據：docs/fin_esue_followup_report.md（點子卡 I018；1.51 / 1.88、全期 1.68 vs fv5 1.45 / 1.87、全期 1.64；事後設計、改善小）。
- 規則：直接讀 fv5 同一預測日的成員資料（不另外呼叫 FinMind）；金融股若有已知 ESUE（事件日 0 + 1 ≤ 預測日、45 個交易日內），
  以 ESUE 在這些金融股間的百分位取全體 fv5 分數的同分位數值取代；其餘、權重、三份資金錯開、成本與結算都同 fv5。
  不替換時可完全重現 fv5 權重（已驗證）。約一半金融股在 fv5 中原本沒有 SUE 分數，fv5e 讓它們以 ESUE 加入。
- 回填：2026-05-12 ~ 2026-10-13 的 6 個預測日（凍結前，皆為 backfill）；5 段平均 fv5e −0.40%、fv5 −0.47%，差 +0.07%（t 0.9）。
- 檢定：24 個 live 期數時，fv5e − fv5 平均差 ≤ 0 則維持 fv5；平均差 > 0 且 fv5e 本身 t > 2 才考慮取代 fv5。
- 每日 `forward/run_forward.py auto` 在 fv5、se 之後呼叫 `run_forward_fv5e.auto()`。

## 前瞻規格 fv5s：fv5 加入借券賣出餘額比相對自身歷史排名（2026-10-21 建立）

- 程式：`forward/run_forward_fv5s.py`；紀錄：`forward/fv5s/`（spec.yaml、predictions.csv、segments.csv、periods.csv、REPORT.md）。
- 研究依據：docs/ts_rank_report.md（點子卡 I040 S1；回測 1.48 / 2.15、全期 1.78 vs fv5 1.45 / 1.87、全期 1.64；改善集中在 2023 年後）。
- 規則：S1 = −（借券賣出餘額 ÷ 股本 在自身過去 250 日（至少 120 日）的百分位排名，前一日值），產業與市值中性化；
  合成分數 = 0.75 × SUE 產業內百分位 + 0.25 × S1 產業內百分位（S1 缺值以 0.5 代入）；其餘、權重、三份資金錯開、成本與結算都同 fv5。
- 回填：2026-05-12 ~ 2026-10-13 的 6 個預測日（凍結後回填，皆為 backfill）；S1 有值約 470–481 檔，持股方向與 fv5 不同 35–56 檔；
  5 段平均 fv5s −0.23%、fv5 −0.47%，差 +0.24%（t 1.8，只作描述）。
- 檢定：24 個 live 期數時，fv5s − fv5 平均差 ≤ 0 則維持 fv5；平均差 > 0 且 fv5s 本身 t > 2 才考慮取代 fv5。
- 每日 `forward/run_forward.py auto` 在 fv5e 之後呼叫 `run_forward_fv5s.auto()`（預測日約 1,500 次 FinMind）。
