"""I040 相對自身歷史的時間序列排名（ts_rank）：借券賣出餘額比、融資餘額比、外資持股比例
（點子卡 research/ideas/I040-ts-rank-own-history-chip-fields.md，檢定計畫看結果前固定）。

用法（於專案根目錄；前 500 名資料已快取）：
    .venv/Scripts/python analysis/ts_rank_chips.py
輸出 docs/ts_rank_chips.md。第 (c) 步驗證樣本只在 (a)(b) 成立的欄位才需要另抓資料（本程式會在報告中標示，需另行執行）。

設計（依點子卡；補充以「補」標示）：
- x1 = 借券賣出餘額 ÷ 已發行股數；x2 = 融資餘額（張）× 1000 ÷ 已發行股數；x3 = 外資持股比例。
- ts_rank = x 在自身過去 250 個交易日（含當日）中的平均名次百分位（(名次 − 1) ÷ (有效個數 − 1)），至少 120 日；
  再整體往後移一日（第 t 日只用 t−1 以前）；x1 視窗內最大值為 0 時設缺值。S1 = −ts(x1)、S2 = −ts(x2)、S3 = +ts(x3)。
- 包裝：leg_probe.wrap（產業內 z → 20 日平均）→ 換倉日 neutralize（產業與 log 市值）。
- IC：leg_probe schedule（88 個換倉日），產業內 Spearman，對 20 日與 60 日報酬；Newey-West t（20 日落後 1、60 日落後 3，補）。
- Fama-MacBeth：60 日報酬的產業內百分位 − 0.5 對 S 與控制（SUE、營收創新高 rec24、同欄位水準、同欄位 20 日變化、12-1 動能、前 20 日報酬、log 市值、20 日周轉率），
  皆為橫斷面百分位 − 0.5（補）。
- Bonferroni：t 門檻 2.39。通過（逐欄位）：(a) 60 日 IC 兩段 > 0、全期 t > 2.39，20 日 IC 兩段同號；(b) FM 係數全期 t > 2.39、兩段同號；
  (c) 驗證 60 日 IC > 0、t > 2；(d) fv5 合成（SUE 0.75 ＋ S 0.25 的產業內百分位）兩段 ≥ fv5、全期 > 1.64。
- 只報告：未包裝的原始 ts_rank 60 日 IC、S 與 SUE 的分數相關。點子卡的 120／500 日視窗、融資除權息排除、S 單獨多空未做（補）。
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
import borrow_capacity as bc  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import lending_legs as ll  # noqa: E402
import ls_turnover as lt  # noqa: E402
import max_rec_robust as mr  # noqa: E402
from sue_attention import nw_t  # noqa: E402

T_CRIT = 2.39


def ts_rank(x: pd.DataFrame) -> pd.DataFrame:
    r = x.rolling(250, min_periods=120).rank(method="average")
    n = x.rolling(250, min_periods=120).count()
    return ((r - 1) / (n - 1)).where(n > 1)


def raw_fields(c):
    idx, tk = c.adj.index, c.tickers
    sbl, mg, fr = {}, {}, {}
    for t in tk:
        sid = t.split(".")[0]
        d = c.client.get("TaiwanDailyShortSaleBalances", sid, "2018-06-01", "2026-05-31")
        if not d.empty:
            sbl[t] = pd.Series(d["SBLShortSalesCurrentDayBalance"].astype(float).to_numpy(), index=pd.to_datetime(d["date"]))
        ch = lp.load_chips(c.client, sid)
        if "margin_bal" in ch:
            mg[t] = ch["margin_bal"]
        if "foreign_ratio" in ch:
            fr[t] = ch["foreign_ratio"]
    f = lambda m: pd.DataFrame(m).reindex(index=idx, columns=tk).ffill()  # noqa: E731
    sh = ll.load_shares(c.client, tk, idx)
    x1 = f(sbl) / sh
    x2 = f(mg) * 1000 / sh
    x3 = f(fr)
    return {"x1": x1, "x2": x2, "x3": x3}, sh


def main():
    c = lp.prepare(500)
    sched = c.schedule
    X, shares = raw_fields(c)
    ts = {k: ts_rank(v) for k, v in X.items()}
    ts["x1"] = ts["x1"].where(X["x1"].rolling(250, min_periods=120).max() > 0)
    S_raw = {"S1 借券賣出餘額比（−）": -ts["x1"].shift(1), "S2 融資餘額比（−）": -ts["x2"].shift(1), "S3 外資持股比例（+）": ts["x3"].shift(1)}
    keymap = {"S1 借券賣出餘額比（−）": "x1", "S2 融資餘額比（−）": "x2", "S3 外資持股比例（+）": "x3"}
    fwd60 = c.adj.shift(-60) / c.adj - 1
    limit = int(c.adj.index.searchsorted(lp.HOLDOUT))
    sue = lp.leg_scores(c, "sue")
    revs = {t: c.client.get("TaiwanStockMonthRevenue", t.split(".")[0], "2017-01-01") for t in c.tickers}
    rec = pd.DataFrame({t: mr.rec_n(rv, 24) for t, rv in revs.items() if not rv.empty})
    r = c.adj.pct_change()
    close = bc.raw_close(c)
    turn = (c.money / close.reindex(columns=c.money.columns)).rolling(20, min_periods=15).sum().reindex(columns=c.tickers) / shares
    mom = (c.adj.shift(21) / c.adj.shift(252) - 1)
    p20 = c.adj / c.adj.shift(20) - 1

    def segs(s, lag):
        s = s.dropna()
        f = lambda y: (float(y.mean()), nw_t(y, lag), len(y))  # noqa: E731
        return {"2019–2022": f(s[s.index < lp.SPLIT]), "2023–2026/04": f(s[s.index >= lp.SPLIT]), "全期": f(s)}
    res = {}
    for name, raw in S_raw.items():
        wz = lp.wrap(raw.replace([np.inf, -np.inf], np.nan), c.member, c.sector)
        sc = {d: lp.neutralize(wz.loc[d], c.sector, c.logcap.loc[d]) for d in sched}
        ok_d = [d for d in sched if int(c.adj.index.searchsorted(d)) + 60 < limit]
        ic20 = pd.Series({d: lp.within_ic(sc[d], c.fwd20.loc[d], c.sector) for d in sched if int(c.adj.index.searchsorted(d)) + 20 < limit})
        ic60 = pd.Series({d: lp.within_ic(sc[d], fwd60.loc[d], c.sector) for d in ok_d})
        ic60_raw = pd.Series({d: lp.within_ic(raw.loc[d].where(c.member.loc[d]), fwd60.loc[d], c.sector) for d in ok_d})
        k = keymap[name]
        x = X[k].shift(1)
        dx = (X[k] - X[k].shift(20)).shift(1)
        fm, corr = {}, []
        for d in ok_d:
            mo = d.to_period("M").to_timestamp()
            df = pd.DataFrame({"y": fwd60.loc[d], "s": sc[d], "sue": sue[d], "rec": rec.loc[mo] if mo in rec.index else np.nan,
                               "lvl": x.loc[d], "chg": dx.loc[d], "mom": mom.loc[d], "p20": p20.loc[d], "lm": c.logcap.loc[d], "turn": turn.loc[d]})
            df = df[c.member.loc[d].reindex(df.index).fillna(False).to_numpy(bool)].replace([np.inf, -np.inf], np.nan).dropna()
            if len(df) < 50:
                continue
            df["y"] = df["y"].groupby(c.sector.reindex(df.index)).rank(pct=True) - 0.5
            Z = df.drop(columns="y").rank(pct=True) - 0.5
            beta, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(Z)), Z.to_numpy()]), df["y"].to_numpy(), rcond=None)
            fm[d] = beta[1]
            corr.append(Z["s"].corr(Z["sue"]))
        a20, a60, b = segs(ic20, 1), segs(ic60, 3), segs(pd.Series(fm), 3)
        ca = a60["2019–2022"][0] > 0 and a60["2023–2026/04"][0] > 0 and a60["全期"][1] > T_CRIT and np.sign(a20["2019–2022"][0]) == np.sign(a20["2023–2026/04"][0])
        cb = b["全期"][1] > T_CRIT and np.sign(b["2019–2022"][0]) == np.sign(b["2023–2026/04"][0])
        res[name] = {"a20": a20, "a60": a60, "raw": segs(ic60_raw, 3), "fm": b, "ca": ca, "cb": cb, "corr": float(np.mean(corr)) if corr else np.nan,
                     "cov": float(np.mean([sc[d].notna().sum() / max(1, c.member.loc[d].sum()) for d in sched]))}
    fic = lambda v: "—" if v[0] != v[0] else f"{v[0]:+.3f}（{v[1]:.1f}）"  # noqa: E731
    L = ["# I040 相對自身歷史的籌碼 ts_rank（自動產生）", "",
         "由 [analysis/ts_rank_chips.py](../analysis/ts_rank_chips.py) 產生；設計見程式開頭（看結果前固定）。"
         "IC 為產業內 Spearman（−1～1），括號為 Newey-West t；Fama-MacBeth 為 60 日報酬產業內百分位對 S 百分位的係數（控制 SUE、營收創新高、同欄位水準與 20 日變化、動能、前 20 日報酬、市值、周轉率）。"
         "Bonferroni t 門檻 2.39。研究結果，非投資建議。", "",
         "| 訊號 | 有值比例 | 60 日 IC：2019–2022 / 2023–2026/04 / 全期 | 20 日 IC：兩段 | Fama-MacBeth：兩段 / 全期 | 只報告：未包裝 60 日 IC（全期） | 與 SUE 相關 |",
         "|---|---|---|---|---|---|---|"]
    for name, v in res.items():
        L.append(f"| {name} | {v['cov']:.0%} | {fic(v['a60']['2019–2022'])} / {fic(v['a60']['2023–2026/04'])} / {fic(v['a60']['全期'])} | "
                 f"{fic(v['a20']['2019–2022'])} / {fic(v['a20']['2023–2026/04'])} | {fic(v['fm']['2019–2022'])} / {fic(v['fm']['2023–2026/04'])} / {fic(v['fm']['全期'])} | "
                 f"{fic(v['raw']['全期'])} | {v['corr']:+.2f} |")
    L += ["", "## 判定（逐欄位）", ""]
    any_pass = False
    for name, v in res.items():
        L.append(f"- {name}：(a) IC {'✓' if v['ca'] else '✗'}；(b) Fama-MacBeth {'✓' if v['cb'] else '✗'}"
                 + ("" if v["ca"] and v["cb"] else " → 停止"))
        any_pass |= v["ca"] and v["cb"]
    L += ["", f"**結論：{'有欄位通過 (a)(b)，需抓第 501–1000 名資料做驗證 (c) 與 fv5 合成 (d)' if any_pass else '三個欄位都未通過，ts_rank 籌碼整族登錄為未通過'}**"]
    (ROOT / "docs" / "ts_rank_chips.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
