"""I010 診斷（只報告，不改判定）：受邀法說會的會後 CAR 是否只是「一般股票相對加權指數落後」。

用法：.venv/Scripts/python analysis/conference_diag.py
輸出 docs/conference_diag.md。
- 配對差額：同 corp_event_study.matched（同日、同產業、SUE 三分位與事件前 60 日報酬三分位相同、前後 40 日內沒有受邀法說會的股票）。
- 基準：同一召開日、股票池全部成員的平均 CAR（等權），代表「一般股票」相對加權指數的表現。
研究結果，非投資建議。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import conference_events as cf  # noqa: E402
import corp_event_study as ce  # noqa: E402
import leg_probe as lp  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

W = {"[+2, +20]": (2, 20), "[+2, +40]": (2, 40)}


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    lines = ["# I010 診斷：會後 CAR 與「一般股票相對加權指數」的比較（自動產生）", "",
             "由 [analysis/conference_diag.py](../analysis/conference_diag.py) 產生；只報告，不改 [I010](conference_events.md) 的判定。"
             "括號為 t 值（同一召開日先平均）。研究結果，非投資建議。", ""]
    for name, (lo, hi) in (("前 500 名（主樣本）", (1, 500)), ("第 501–1000 名（驗證）", (501, 1000))):
        S = ce.Sample(client, lo, hi, mkt, tx)
        raw, _ = cf.build_events(S.days)
        ev = cf.add_cars(S, raw)
        inv = ev[ev["grp"] == "受邀"]
        main_ev = inv[~inv["excluded"]]
        m = ce.matched(S, main_ev, inv, W, exclude_span=40)
        mem = S.member.to_numpy()
        for w, (a, b) in W.items():
            m[f"{w}_all"] = [float(np.nanmean(S.car(np.where(mem[k])[0], k + a, k + b))) for k in m["k0"]]
            m[f"{w}_vs_all"] = m[w] - m[f"{w}_all"]
        lines += [f"## {name}", "", f"主檢定受邀事件 {len(m)} 筆，有配對 {int((m['n_ctrl'] > 0).sum())} 筆。", "",
                  "| 統計量 | 期間 | " + " | ".join(W) + " |", "|---|---|" + "---|" * len(W)]
        for lab, suf in (("事件 CAR（原判定用）", ""), ("同日全部成員平均 CAR（一般股票）", "_all"),
                         ("事件 − 全部成員平均", "_vs_all"), ("配對差額（同產業、SUE、動能）", "_diff")):
            for seg, g in (("2019–2022", m[m["seg"] == "2019–2022"]), ("2023–2026/04", m[m["seg"] == "2023–2026/04"]), ("全期", m)):
                lines.append(f"| {lab} | {seg} | " + " | ".join(ce.fmt(ce.clustered(g, f"{w}{suf}")) for w in W) + " |")
        lines.append("")
    (ROOT / "docs" / "conference_diag.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
