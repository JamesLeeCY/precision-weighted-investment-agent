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
claude.ai 上的網站副本不會自動更新，需要時再手動重新發佈。

## 已知紀錄瑕疵

- 回填的 2026-07-01 起四批預測，`git_dirty` 記為 True：當時的檢查把尚未 commit 的 `predictions.csv` 本身算成「未 commit 的修改」。規則程式碼的指紋檢查每次都通過，且四批都記錄同一個 commit `e940168`（新增 spec 檔的 commit，規則程式碼與凍結時的 `57c364d` 相同）。已於 2026-10-10 修正檢查（只看已追蹤檔案、排除前瞻紀錄本身）；既有紀錄依「只能新增」原則不修改。

## 回填（backfill）

2026-06 到 2026-10 在開發時沒有使用過（回測資料只到 2026-05），已在凍結後以 `backfill` 標記補做，作為第一批檢查。回填使用的是今天抓取的資料，若 FinMind 事後修正過歷史財報，會與當時實際可得的資料略有差異，因此不算入正式檢定。
