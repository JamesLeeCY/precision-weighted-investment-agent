"""I038 非金融按月自結公司的盈餘驚奇增量（點子卡 research/ideas/I038-nonfinancial-esue-increment.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/nonfin_esue.py
輸出 docs/nonfin_esue.md。

設計（依點子卡；補充以「補」標示）：
- 事件：I015 的 ESUE 事件（analysis/self_earnings_events.esue_table：同一份解析、13:30 以後發言者事件日 0 為下一個交易日），
  只取產業不是「金融保險」「金融業」的公司；事件日當天為市值前 1000 名成員（前 500 名 ∪ 第 501–1000 名）。
- 訊號：R = ESUE 對同月營收 SUE 的合併迴歸殘差；係數只用 2019–2022 事件估計後固定，套用到全期。
  補：ESUE、SUE 先截在 ±5 再迴歸（兩者都是標準化驚奇，少數公司年差標準差很小會產生極端值）。
- 報酬：第 +1 日收盤進場，CAR[+2, +21]（個股 − β × 加權指數含息，與 I015 相同）。
- 迴歸：CAR = 公司固定效果 + b·R，標準誤以公司與月份雙向群聚（V = V公司 + V月份 − V異質）。
- 通過（事前固定）：b 兩段皆 > 0、全期 t > 2；排除事件數最多的單一公司後全期 b 仍 > 0。
- 事件數門檻：每段至少 400 個公司月，不足即停止（只報告事件數）。
- 只報告：排除中租-KY（5871）、只看前 500 名、前 − 後三分之一 R 的月份差額、原始 ESUE 係數（不扣 SUE）。
- 即使通過也不建可交易組合（公司數不足），只考慮加入 forward/se 的前瞻觀察。
研究結果，非投資建議。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import corp_event_study as ce  # noqa: E402
import leg_probe as lp  # noqa: E402
import self_earnings_events as see  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

CLIP = 5.0
MIN_EVENTS = 400
CHAILEASE = "5871"


def twoway(y: np.ndarray, X: np.ndarray, g1: np.ndarray, g2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ beta
    inv = np.linalg.pinv(X.T @ X)

    def meat(groups):
        m = np.zeros((X.shape[1], X.shape[1]))
        for g in np.unique(groups):
            s = X[groups == g].T @ e[groups == g]
            m += np.outer(s, s)
        return m
    het = (X * e[:, None]).T @ (X * e[:, None])
    V = inv @ (meat(g1) + meat(g2) - het) @ inv
    return beta, np.sqrt(np.clip(np.diag(V), 0, None))


def fe_reg(df: pd.DataFrame, x: str) -> tuple[float, float, int]:
    df = df.dropna(subset=["car", x])
    if len(df) < 30 or df["stock_id"].nunique() < 2:
        return float("nan"), float("nan"), len(df)
    yd = df["car"] - df.groupby("stock_id")["car"].transform("mean")
    xd = df[x] - df.groupby("stock_id")[x].transform("mean")
    b, se = twoway(yd.to_numpy(float), xd.to_numpy(float)[:, None], df["stock_id"].to_numpy(), df["month"].astype(str).to_numpy())
    return float(b[0]), float(b[0] / se[0]) if se[0] > 0 else float("nan"), len(df)


def segs(ev, f):
    return {"2019–2022": f(ev[ev["seg"] == "2019–2022"]), "2023–2026/04": f(ev[ev["seg"] == "2023–2026/04"]), "全期": f(ev)}


def fmt(v) -> str:
    b, t, n = v
    return "—" if b != b else f"{b:+.3%}（{t:.1f}，{n}）"


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    e = see.esue_table(client)
    parts = []
    for lo, hi in ((1, 500), (501, 1000)):
        S = ce.Sample(client, lo, hi, mkt, tx)
        ev = see.attach(S, e).assign(tier="前 500 名" if lo == 1 else "第 501–1000 名")
        parts.append(ev[~ev["fin"]])
    ev = pd.concat(parts, ignore_index=True).sort_values(["ticker", "t0"]).drop_duplicates(["ticker", "month"], keep="first")
    ev = ev.dropna(subset=["car", "esue", "sue"]).reset_index(drop=True)
    ev["esue_c"], ev["sue_c"] = ev["esue"].clip(-CLIP, CLIP), ev["sue"].clip(-CLIP, CLIP)
    est = ev[ev["seg"] == "2019–2022"]
    A = np.column_stack([np.ones(len(est)), est["sue_c"].to_numpy(float)])
    coef, *_ = np.linalg.lstsq(A, est["esue_c"].to_numpy(float), rcond=None)
    ev["R"] = ev["esue_c"] - coef[0] - coef[1] * ev["sue_c"]
    names = ev.groupby("stock_id")["name"].first() if "name" in ev else pd.Series(dtype=str)
    n_seg = ev.groupby("seg").size()
    top = ev["stock_id"].value_counts()
    L = ["# I038 非金融按月自結公司的盈餘驚奇增量（自動產生）", "",
         "由 [analysis/nonfin_esue.py](../analysis/nonfin_esue.py) 產生；設計見程式開頭（看結果前固定）。"
         "CAR = 第 +2 ~ +21 個交易日累積異常報酬（個股 − β × 加權指數含息）；係數 = R（或 ESUE）每增加 1 個標準化單位的 CAR 變化；"
         "括號為（t 值，事件數），公司固定效果、公司與月份雙向群聚。研究結果，非投資建議。", "",
         f"非金融事件（市值前 1000 名、2019-01 ~ 2026-04、有 ESUE 與 SUE）：{len(ev):,} 個公司月、{ev['stock_id'].nunique()} 家；"
         f"2019–2022 {n_seg.get('2019–2022', 0)}、2023–2026/04 {n_seg.get('2023–2026/04', 0)}（門檻每段 {MIN_EVENTS}）。", "",
         f"R 的估計（2019–2022）：ESUE = {coef[0]:+.3f} + {coef[1]:+.3f} × SUE；全期 ESUE 與 SUE 相關 {ev['esue_c'].corr(ev['sue_c']):+.2f}。", "",
         "事件數最多的公司：" + "、".join(f"{s}（{n}）" for s, n in top.head(6).items()), ""]
    enough = all(n_seg.get(k, 0) >= MIN_EVENTS for k in ("2019–2022", "2023–2026/04"))
    if not enough:
        L += [f"**事件數未達門檻（每段至少 {MIN_EVENTS} 個公司月），依點子卡停止；以下只作描述。**", ""]
    main_r = segs(ev, lambda x: fe_reg(x, "R"))
    excl = ev[ev["stock_id"] != top.index[0]]
    ex_r = fe_reg(excl, "R")
    L += ["| 統計量 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
          "| **R 係數（主檢定）** | " + " | ".join(fmt(v) for v in main_r.values()) + " |",
          f"| 排除事件最多的公司（{top.index[0]}） | " + " | ".join(fmt(v) for v in segs(excl, lambda x: fe_reg(x, 'R')).values()) + " |",
          f"| 只報告：排除中租-KY（{CHAILEASE}） | " + " | ".join(fmt(v) for v in segs(ev[ev['stock_id'] != CHAILEASE], lambda x: fe_reg(x, 'R')).values()) + " |",
          "| 只報告：只看前 500 名 | " + " | ".join(fmt(v) for v in segs(ev[ev['tier'] == '前 500 名'], lambda x: fe_reg(x, 'R')).values()) + " |",
          "| 只報告：原始 ESUE 係數（不扣 SUE） | " + " | ".join(fmt(v) for v in segs(ev, lambda x: fe_reg(x, 'esue_c')).values()) + " |",
          "| 只報告：SUE 係數 | " + " | ".join(fmt(v) for v in segs(ev, lambda x: fe_reg(x, 'sue_c')).values()) + " |"]
    # 只報告：每月 R 前 − 後三分之一
    ev["q"] = -1
    for _, g in ev.groupby("month"):
        ev.loc[g.index, "q"] = ce.terciles(g["R"].to_numpy(float), np.ones(len(g), bool))

    def spread(x):
        d = x[x["q"] >= 0].groupby(["month", "q"])["car"].mean().unstack()
        if 0 not in d or 2 not in d:
            return float("nan"), float("nan"), 0
        s = (d[2] - d[0]).dropna()
        return (float(s.mean()), float(s.mean() / s.std(ddof=1) * math.sqrt(len(s))) if len(s) > 4 else float("nan"), len(s))
    L.append("| 只報告：R 前 − 後三分之一（每月，t 依月份；括號第二個數字為月份數） | " + " | ".join(fmt(v) for v in segs(ev, spread).values()) + " |")
    p1 = all(main_r[k][0] > 0 for k in ("2019–2022", "2023–2026/04")) and main_r["全期"][1] > 2
    p2 = ex_r[0] > 0
    L += ["", "## 判定", "",
          f"- 事件數門檻（每段 ≥ {MIN_EVENTS}）：{'✓' if enough else '✗'}",
          f"- R 係數兩段皆 > 0、全期 t > 2：{'✓' if p1 else '✗'}",
          f"- 排除事件最多的公司後全期仍 > 0：{'✓' if p2 else '✗'}", "",
          f"**結論：{'通過（只作研究紀錄）' if enough and p1 and p2 else '未通過'}**"]
    (ROOT / "docs" / "nonfin_esue.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
