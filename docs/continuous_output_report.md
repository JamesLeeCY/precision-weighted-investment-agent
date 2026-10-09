# 連續輸出模式報告：讓 Agent 直接輸出分數映射的機率

| | |
|---|---|
| 執行日期 | 2026-10-09 |
| 動機 | [擴大股票池報告](expanded_universe_report.md)發現：財報 Agent 內部連續分數的產業內 IC 約 +0.02 ~ +0.03，但門檻化成「訊號 + 信心」後幾乎消失 |
| 實作 | `agents/base.py:continuous_judgement`，四個規則式 Agent 皆支援；`--agent-output continuous` 開啟，預設仍為門檻模式（既有報告逐筆可重現，已驗證） |
| 輸出 | [reports/finmind_expanded_continuous/](../reports/finmind_expanded_continuous/comparison_report.md)（41 檔 × 2019–2026）、[reports/finmind_macro_continuous/](../reports/finmind_macro_continuous/comparison_report.md)（5 檔 × 2024–2026，含新聞） |
| 分析 | [analysis/phase_robustness_agents.py](../analysis/phase_robustness_agents.py)、[analysis/portfolio_phase_robustness.py](../analysis/portfolio_phase_robustness.py) |

## 1. 設計

| | 門檻模式（原設計） | 連續模式 |
|---|---|---|
| 方向 | \|score\| ≤ 0.2（新聞 0.15）一律中性 | score 的正負號 |
| 機率 | 另一條信心公式：0.3 + 0.2·覆蓋率 + 0.35·\|score\| − 矛盾懲罰，下限 0.5 | **p = σ(ln 3 · score · 證據強度)** |
| 範圍 | 中性 = 0.5；有方向時 0.5–0.95 | 0.25–0.75（分數 ±1、證據完整時） |

- **證據強度**：財報 / 總經 / 供應鏈為資料覆蓋率（有值的分量數 ÷ 分量總數）；新聞為平均來源可信度 × min(1, 事件數 ÷ 5)。
- **相容規格**：signal = p 在 0.5 的哪一側，confidence = max(p, 1 − p) ≥ 0.5，規格 6.1 的換算恰好還原 p；合併公式與校準不變。
- 比例常數 ln 3 事先固定（分數 ±1 → 0.75 / 0.25），過度自信交給 Agent 層級校準收縮。LLM 判讀不受影響。

## 2. 排序資訊確實保住了（41 檔，每個交易日，21 種取樣起點）

產業內 IC（每日平均；括號為 21 種起點中為正的個數）：

| Agent | 門檻模式 2019–2023 | **連續模式 2019–2023** | 門檻模式 2024–2026 | **連續模式 2024–2026** |
|---|---|---|---|---|
| 財報 | +0.002（10/21） | **+0.022（20/21）** | +0.017（16/21） | **+0.028（18/21）** |
| 總經/籌碼 | −0.003（11/21） | −0.015（6/21） | −0.042（4/21） | −0.025（5/21） |
| 供應鏈 | −0.031（2/21） | −0.030（1/21） | −0.037（3/21） | −0.019（7/21） |

財報 Agent 的連續機率與原始分數的產業內 IC 完全一致（+0.022 / +0.028），門檻化丟掉的排序資訊已回收。總經與供應鏈本來就沒有產業內排序能力，連續化也不會無中生有。

## 3. 回測（41 檔 × 2019–2026，扣交易成本）

| 策略 | Brier（門檻 → 連續） | 每期超額 vs 等權持有（門檻 → 連續） |
|---|---|---|
| 財報 Agent | 0.2574 → 0.2558 | +0.50%（t 1.30）→ +0.23%（t 1.09） |
| 簡單平均合併 | 0.2501 → 0.2500 | +0.38%（t 0.67）→ **+1.31%（t 2.21）** |
| 精度加權合併 | 0.2500 → 0.2500 | +0.50%（t 0.81）→ +1.12%（t 1.70） |
| 校準後精度加權 | 0.2498 → 0.2500 | 兩者都幾乎不持股（平均 < 1 檔），大幅落後 |

連續模式下簡單平均的超額集中在 2019–2023（+1.84%，t 2.36），2024–2026 只有 +0.19%（t 0.23）。所有策略的 Brier 仍比「永遠預測基率 57.6%」（0.2442）差：連續機率集中在 0.5 附近，合併後更接近 0.5。

## 4. 合併組合的穩健性與拆解（21 種取樣起點，未扣成本）

簡單平均合併、合併機率 > 0.55 的股票等權持有 20 個交易日，相對等權持有全部 41 檔；以 Brinson 方式拆成「產業配置」與「產業內選股」：

| | 門檻模式 | 連續模式 |
|---|---|---|
| **2019–2023** 每期超額（21 起點中位） | +0.91%（範圍 −0.38% ~ +2.36%，20/21 為正，t 中位 1.29） | **+1.58%（範圍 +0.04% ~ +3.02%，21/21 為正，t 中位 1.82）** |
| — 產業配置 | +0.76% | +0.72% |
| — 產業內選股 | +0.33% | **+0.97%** |
| **2024–2026** 每期超額 | −0.05%（8/21 為正） | −0.02%（10/21 為正） |
| — 產業配置 / 選股 | +0.44% / −0.33% | +0.31% / −0.32% |

## 5. 解讀

1. **連續輸出達成了目標**：財報 Agent 的排序資訊不再被門檻化丟掉；2019–2023 合併組合的選股貢獻從 +0.33% 提高到 +0.97%，且 21 種取樣起點全部為正。
2. **但 2024–2026 完全沒有超額**，選股貢獻甚至為負（−0.32%）。效果只出現在前半段。
3. **為什麼還不能宣稱有效：**
   - **選股偏誤**：股票池是事後挑選的 AI 贏家。產業配置部分直接受影響；產業內選股受影響較小，但仍是在「之後都活下來且表現好」的公司之間比較。
   - **多重比較**：本專案已試過多種 Agent、圖譜、合併公式與輸出模式，這是其中表現最好的一個組合；名目 t ≈ 1.8–2.2 在這個脈絡下不足以排除運氣。
   - **兩期不一致**：真正的訊號不應該在近 2.4 年完全消失。
   - 單一 Agent（財報）的產業內 IC 雖然兩期都為正，但幅度小（約 0.02–0.03），單一起點 t 中位數約 0.8。
4. **5 檔 × 2024–2026（含新聞）沒有改善**：合併 Brier 0.2530 → 0.2564；財報 Agent 跨股票 IC −0.149 → −0.230。只有 5 檔時雜訊範圍很大（見[供應鏈驗證報告](supply_chain_validation_report.md)），不應過度解讀，但至少沒有看到改善。

## 6. 建議

- **後續擴大股票池研究建議改用連續模式**：它保留了資訊、沒有明顯缺點（目前設定檔預設仍為門檻模式，以便重現既有報告；需加 `--agent-output continuous`）。
- 要確認 2019–2023 的選股貢獻是否真實，需要**無選股偏誤的股票池**（每年依當時資料選股、含下市公司）與**完全未看過的期間**；在那之前，結論是「有方向一致的弱訊號，未經證實」。

---

*重現方式：*

```bash
.venv/Scripts/python backtest/run_backtest.py --mode finmind --config config/tickers_expanded.yaml --agents fundamentals_agent,macro_agent,supply_chain_agent --agent-output continuous --output-dir reports/finmind_expanded_continuous
.venv/Scripts/python backtest/run_backtest.py --mode finmind --start-date 2024-01-01 --end-date 2026-05-31 --step-days 21 --agents fundamentals_agent,news_agent,macro_agent --agent-output continuous --output-dir reports/finmind_macro_continuous
.venv/Scripts/python analysis/phase_robustness_agents.py config/tickers_expanded.yaml daily_expanded.csv
.venv/Scripts/python analysis/portfolio_phase_robustness.py daily_expanded.csv config/tickers_expanded.yaml
```
