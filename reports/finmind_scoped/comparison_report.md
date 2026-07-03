# 回測比較報表：三種合併策略（規格 6.3）

- 執行模式：`finmind`
- 預測事件數：47（3 檔股票）
- 期間：2025-01-02 ~ 2026-04-28
- 應驗判定：horizon 期末絕對報酬 > 0（20 個交易日）

| 策略 | 平均 Brier ↓ | 方向準確率 ↑ | ECE ↓ | n(方向) |
|---|---|---|---|---|
| Baseline A：單一 Agent（財報） | 0.2553 | 0.524 | 0.1490 | 21 |
| Baseline B：簡單平均合併 | 0.2529 | 0.517 | 0.0848 | 29 |
| 本系統：精度加權合併 | 0.2532 | 0.517 | 0.1103 | 29 |

## 驗收標準（規格 6.3）

- 精度加權 Brier 優於兩個 baseline：❌ 未通過
- 精度加權 ECE 不劣於兩個 baseline：❌ 未通過

## 校準曲線

![Baseline A](calibration_baseline_a.png)
![Baseline B](calibration_baseline_b.png)
![Precision Weighted](calibration_precision_weighted.png)

## 備註

- Baseline A 的機率採規格 6.1 轉換；合併策略的機率為各 Agent 6.1 機率的
  加權線性意見池（權重同規格 5.2 合併公式）。
- 精度加權在回測初期（冷啟動，n<5）等同簡單平均，差異隨精度記錄累積浮現。