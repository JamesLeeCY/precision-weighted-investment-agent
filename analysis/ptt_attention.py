"""I041 PTT 股版討論量暴增（點子卡 research/ideas/I041-ptt-discussion-surge-attention.md，檢定計畫看結果前固定）。

用法（於專案根目錄；先執行 fetch_ptt_titles.py 與 ptt_counts.py，歧義排除名單已固定）：
    .venv/Scripts/python analysis/ptt_attention.py
輸出 docs/ptt_attention.md。

設計（依點子卡；補充以「補」標示）：
- 計數：data_cache/events/ptt_daily_counts.csv（交易日 D 計入前一交易日 13:30 後到 D 13:30 的文章標題提及）。
  N20 = 過去 20 個交易日提及篇數。surge = ts_rank(N20, 250 日，至少 120 日，同 I040 定義)，再往後移一日（第 t 日只用 t−1 以前）；
  過去 250 日提及總數 < 12 設缺值。PTT_surge = −surge。包裝：產業內 z（成員中）→ 對產業與 log 市值取殘差（不做 20 日平均）。
- 樣本：前 500 名中 PTT_surge 有值者；換倉日 = leg_probe schedule（88 個月營收換倉日），有效檔數 < 60 的換倉日不計。
- H1：產業內 Spearman IC（PTT_surge vs 之後 20 日〔主〕、60 日報酬），Newey-West t（落後 1、3）。
  Fama-MacBeth（20 日報酬產業內百分位 − 0.5）控制 dt20、20 日周轉率、abvol60、MAX、前 20 日報酬、12-1 動能、log 市值、SUE，
  皆為橫斷面百分位 − 0.5（補，同 I009）。
- 同族檢查：PTT_surge 與 dt20、abvol60 的產業內等級相關（換倉日平均）|ρ| > 0.6 則停止。
- 右偏檢查：surge 五分位（換倉日內）等權平均 60 日報酬，最暴增 − 最冷的差與 t（每期差的 t），以及剔除每期報酬前 1% 後的同一數字。
- H2：Fama-MacBeth 60 日報酬 = SUE + surge + SUE × surge + 同上控制；補：surge 用 +ts_rank 百分位（暴增越大越高），
  所以假設的方向是交互項 < 0（暴增時 SUE 漂移較弱）。
- Bonferroni（H1、H2 兩個）：t 門檻 2.24。
- 通過：H1 需 20 日 IC 兩段 > 0、全期 t > 2.24，Fama-MacBeth 全期 t > 2.24，且五分位差兩段同為負；H2 需交互項全期 t < −2.24、兩段同號。
  任一通過才做可交易檢查（H1：fv5 分數 = SUE 與 PTT_surge 的產業內百分位 0.75 / 0.25，缺值 0.5；H2：SUE 在 surge 前 1/3 者 SUE 百分位減半，補），
  兩段 Sharpe 都不低於 fv5 且全期高於 fv5 全期。
- 驗證：第 501–1000 名只報告有效檔數與 20 日 IC。
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
import corp_event_study as ce  # noqa: E402
import daytrading_leg as dl  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import lending_legs as ll  # noqa: E402
import ls_turnover as lt  # noqa: E402
from sue_attention import nw_t  # noqa: E402
from ts_rank_chips import ts_rank  # noqa: E402

COUNTS = ROOT / "data_cache" / "events" / "ptt_daily_counts.csv"
T_CRIT = 2.24
MIN_N = 60


def surge_raw(index: pd.DatetimeIndex, tickers: list) -> pd.DataFrame:
    c = pd.read_csv(COUNTS, index_col=0, parse_dates=True)
    c.columns = [f"{x}.TW" for x in c.columns]
    c = c.reindex(index=index, columns=tickers)
    covered = c.notna().any(axis=1)
    c = c.fillna(0.0).where(covered, np.nan)          # PTT 抓取範圍外為缺值
    n20 = c.rolling(20, min_periods=20).sum()
    tot = c.rolling(250, min_periods=120).sum()
    return ts_rank(n20).where(tot >= 12).shift(1)


def scores(raw: pd.DataFrame, member, sector, logcap, sched) -> dict:
    z = lp.wrap(raw, member, sector, smooth=False)
    return {d: lp.neutralize(z.loc[d], sector, logcap.loc[d]) for d in sched}


def segs(s: pd.Series, lag: int) -> dict:
    s = s.dropna()
    f = lambda y: (float(y.mean()), nw_t(y, lag), len(y))  # noqa: E731
    return {"2019–2022": f(s[s.index < lp.SPLIT]), "2023–2026/04": f(s[s.index >= lp.SPLIT]), "全期": f(s)}


def fic(v, pct=False) -> str:
    return "—" if v[0] != v[0] else (f"{v[0]:+.2%}" if pct else f"{v[0]:+.3f}") + f"（{v[1]:.1f}，{v[2]}）"


def main():
    c = lp.prepare(500)
    days, sector = c.adj.index, c.sector
    limit = int(days.searchsorted(lp.HOLDOUT))
    raw = surge_raw(days, c.tickers)
    sched0 = c.schedule
    sc_all = scores(-raw, c.member, sector, c.logcap, sched0)
    n_valid = pd.Series({d: int(sc_all[d].notna().sum()) for d in sched0})
    sched = [d for d in sched0 if n_valid[d] >= MIN_N]
    sc = {d: sc_all[d] for d in sched}
    fwd60 = c.adj.shift(-60) / c.adj - 1
    ok20 = [d for d in sched if int(days.searchsorted(d)) + 20 < limit]
    ok60 = [d for d in sched if int(days.searchsorted(d)) + 60 < limit]
    ic20 = pd.Series({d: lp.within_ic(sc[d], c.fwd20.loc[d], sector) for d in ok20})
    ic60 = pd.Series({d: lp.within_ic(sc[d], fwd60.loc[d], sector) for d in ok60})

    # 控制變數
    dtr, _, vol = dl.dtr_frames(c.client, c.tickers, days)
    dt20 = dl.legs(dtr)["dt20"]
    shares = ll.load_shares(c.client, c.tickers, days)
    r = c.adj.pct_change()
    ctrl = {"dt20": dt20, "周轉率": (vol.rolling(20, min_periods=15).sum() / shares).shift(1), "abvol60": c.raws["abvol60"],
            "MAX": r.rolling(21, min_periods=15).max().shift(1), "前 20 日報酬": (c.adj / c.adj.shift(20) - 1).shift(1),
            "12-1 動能": (c.adj.shift(21) / c.adj.shift(252) - 1).shift(1), "log 市值": c.logcap}
    sue = lp.leg_scores(c, "sue")
    fm1, fm2, rho = {}, {}, {"dt20": [], "abvol60": []}
    for d in sched:
        mem = c.member.loc[d]
        base = pd.DataFrame({"s": sc[d], **{k: v.loc[d] for k, v in ctrl.items()}, "SUE": sue[d]})
        base = base[mem.reindex(base.index).fillna(False).to_numpy(bool)].replace([np.inf, -np.inf], np.nan).dropna()
        if len(base) < 40:
            continue
        for k in rho:
            rho[k].append(lp.within_ic(base["s"], base[k], sector))
        X = base.rank(pct=True) - 0.5
        if d in ok20:
            y = c.fwd20.loc[d].reindex(base.index)
            y = y.groupby(sector.reindex(base.index)).rank(pct=True) - 0.5
            m = y.notna()
            b, *_ = np.linalg.lstsq(np.column_stack([np.ones(m.sum()), X[m].to_numpy()]), y[m].to_numpy(), rcond=None)
            fm1[d] = b[1]
        if d in ok60:
            y = fwd60.loc[d].reindex(base.index)
            y = y.groupby(sector.reindex(base.index)).rank(pct=True) - 0.5
            m = y.notna()
            su = -X["s"]                                   # surge 方向：暴增越大越高
            Z = np.column_stack([np.ones(m.sum()), X.loc[m, "SUE"], su[m], (X["SUE"] * su)[m], X[m].drop(columns=["s", "SUE"]).to_numpy()])
            b, *_ = np.linalg.lstsq(Z, y[m].to_numpy(), rcond=None)
            fm2[d] = b[3]
    rho_m = {k: float(np.nanmean(v)) for k, v in rho.items()}
    family = any(abs(v) > 0.6 for v in rho_m.values())

    # 右偏檢查：五分位平均 60 日報酬
    q_raw, q_trim = {}, {}
    for d in ok60:
        s = sc[d].dropna()
        f = fwd60.loc[d].reindex(s.index)
        df = pd.DataFrame({"s": s, "f": f}).dropna()
        if len(df) < 25:
            continue
        df["q"] = pd.qcut(-df["s"].rank(method="first"), 5, labels=False)      # q4 = 最暴增
        q_raw[d] = df.loc[df["q"] == 4, "f"].mean() - df.loc[df["q"] == 0, "f"].mean()
        cap = df["f"].quantile(0.99)
        t = df[df["f"] <= cap]
        q_trim[d] = t.loc[t["q"] == 4, "f"].mean() - t.loc[t["q"] == 0, "f"].mean()

    a20, a60, b1, b2 = segs(ic20, 1), segs(ic60, 3), segs(pd.Series(fm1), 1), segs(pd.Series(fm2), 3)
    qr, qt = segs(pd.Series(q_raw), 3), segs(pd.Series(q_trim), 3)

    # 驗證
    import dotenv
    dotenv.load_dotenv(ROOT / ".env")
    mkt, tx = lp.market_tri(c.client), lp.tx_continuous(c.client)
    V = ce.Sample(c.client, 501, 1000, mkt, tx)
    vsec = pd.Series({t: V.sector.get(t.split(".")[0], "NA") for t in V.tickers})
    vraw = surge_raw(V.days, V.tickers)
    vsched = [d for d in sched0 if d in V.days]
    vsc = scores(-vraw, V.member, vsec, V.lmcap, vsched)
    vfwd = V.adj.shift(-20) / V.adj - 1
    vlim = int(V.days.searchsorted(lp.HOLDOUT))
    vn = pd.Series({d: int(vsc[d].notna().sum()) for d in vsched})
    vic = pd.Series({d: lp.within_ic(vsc[d], vfwd.loc[d], vsec) for d in vsched if vn[d] >= 20 and int(V.days.searchsorted(d)) + 20 < vlim})
    av = segs(vic, 1)

    h1 = (a20["2019–2022"][0] > 0 and a20["2023–2026/04"][0] > 0 and a20["全期"][1] > T_CRIT and b1["全期"][1] > T_CRIT
          and qr["2019–2022"][0] < 0 and qr["2023–2026/04"][0] < 0)
    h2 = b2["全期"][1] < -T_CRIT and np.sign(b2["2019–2022"][0]) == np.sign(b2["2023–2026/04"][0])
    L = ["# I041 PTT 股版討論量暴增（自動產生）", "",
         "由 [analysis/ptt_attention.py](../analysis/ptt_attention.py) 產生；設計見程式開頭（看結果前固定）。"
         "PTT_surge = −（過去 20 日標題提及篇數在自身過去 250 日的排名），正值代表討論冷清；IC 為產業內 Spearman（−1～1），括號為（Newey-West t，換倉日數）；"
         "Fama-MacBeth 為報酬產業內百分位對各變數百分位的係數；五分位差為最暴增 − 最冷一組的等權平均 60 日報酬。Bonferroni t 門檻 2.24。研究結果，非投資建議。", "",
         f"有效檔數（前 500 名中過去 250 日提及 ≥ 12 篇）：換倉日中位數 {int(n_valid.median())}、最少 {int(n_valid.min())}、最多 {int(n_valid.max())}；"
         f"有效檔數 ≥ {MIN_N} 的換倉日 {len(sched)} / {len(sched0)} 個。", "",
         f"同族檢查（PTT_surge 與控制變數的產業內等級相關，換倉日平均）：dt20 {rho_m['dt20']:+.2f}、abvol60 {rho_m['abvol60']:+.2f}"
         f"（|ρ| > 0.6 則停止）→ {'同族，停止' if family else '不同族'}。", "",
         "| 統計量 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         "| **H1：IC 20 日（主）** | " + " | ".join(fic(a20[s]) for s in a20) + " |",
         "| H1：IC 60 日 | " + " | ".join(fic(a60[s]) for s in a60) + " |",
         "| **H1：Fama-MacBeth 20 日（控制 dt20、周轉率、abvol60、MAX、前 20 日報酬、動能、市值、SUE）** | " + " | ".join(fic(b1[s]) for s in b1) + " |",
         "| **H1 右偏檢查：五分位差 60 日（最暴增 − 最冷）** | " + " | ".join(fic(qr[s], True) for s in qr) + " |",
         "| 同上，剔除每期報酬前 1% | " + " | ".join(fic(qt[s], True) for s in qt) + " |",
         "| **H2：SUE × 暴增 交互項（60 日 Fama-MacBeth）** | " + " | ".join(fic(b2[s]) for s in b2) + " |",
         f"| 驗證（第 501–1000 名，有效檔數中位數 {int(vn.median()) if len(vn) else 0}）IC 20 日 | " + " | ".join(fic(av[s]) for s in av) + " |", ""]
    port_lines, c4 = [], None
    if (h1 or h2) and not family:
        fee = hc.lending_fees(c.client, c.tickers, days)
        quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
        close = bc.raw_close(c)
        sched_all = c.schedule

        def shortable_at(d):
            n_short = max(1, int(c.member.loc[d].sum() / 3))
            need = lt.K_CAPITAL / n_short / close.loc[d]
            return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

        def comp(d):
            s = sue[d].dropna()
            sec = sector.reindex(s.index)
            ps = s.groupby(sec).rank(pct=True)
            if h1:
                pm = sc_all[d].reindex(s.index).groupby(sec).rank(pct=True).fillna(0.5)
                return 0.75 * ps + 0.25 * pm
            su = (-sc_all[d]).reindex(s.index)
            hot = su.groupby(sec).rank(pct=True) > 2 / 3
            return ps.where(~hot.fillna(False), ps * 0.5)

        def book(fn):
            parts = []
            for off in range(3):
                wd = {d: lt.ew_ls_buffer(fn(d), sector, shortable_at(d), q_keep=None) for d in sched_all[off::3]}
                parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)["ret"])
            x = pd.concat(parts, axis=1).mean(axis=1)
            x = x[x.index > sched_all[2]]
            return hc.stats(x) | {"full": lp.sharpe(x.dropna())}
        port = {"fv5 原版（SUE）": book(lambda d: sue[d]), ("H1 合成 0.75 SUE ＋ 0.25 PTT_surge" if h1 else "H2：暴增前 1/3 的 SUE 減半"): book(comp)}
        port_lines = ["| 建構 | Sharpe | 全期 | 年化報酬 | 最大回撤 |", "|---|---|---|---|---|"]
        for k, s in port.items():
            port_lines.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} |")
        p0, p1 = list(port.values())
        c4 = p1["sh_oos"] >= p0["sh_oos"] and p1["sh_is"] >= p0["sh_is"] and p1["full"] > p0["full"]
        L += port_lines + [""]
    mark = lambda b: "—（未執行）" if b is None else ("✓" if b else "✗")  # noqa: E731
    L += ["## 判定", "",
          f"- 同族檢查：{'✗ 與當沖比或異常成交量同族' if family else '✓'}",
          f"- H1（20 日 IC 兩段 > 0、全期 t > {T_CRIT}；Fama-MacBeth 全期 t > {T_CRIT}；五分位差兩段皆 < 0）：{mark(h1)}",
          f"- H2（交互項全期 t < −{T_CRIT}、兩段同號）：{mark(h2)}",
          f"- 可交易（兩段 Sharpe 不低於 fv5、全期高於 fv5）：{mark(c4)}", "",
          f"**結論：{'通過' if c4 else '未通過'}**"]
    (ROOT / "docs" / "ptt_attention.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
