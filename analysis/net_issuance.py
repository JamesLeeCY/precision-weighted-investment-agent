"""I029 淨發行股數（點子卡 research/ideas/I029-net-share-issuance.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料大多已快取）：
    .venv/Scripts/python analysis/net_issuance.py
輸出 docs/net_issuance.md。

設計（依點子卡；點子卡沒寫清楚、在看結果前補上的細節以「補」標示）：
- 股數：FinMind TaiwanStockShareholding NumberOfSharesIssued（2018-06 起每日），換倉日用前一個交易日的值。
- 調整：股票股利與分割（TaiwanStockDividendResult 中含「權」的事件、TaiwanStockSplitPrice）。
  補：除權參考價比例在「權息」事件混入現金股利，無法單獨得到配股率，所以改用實際股數跳升：除權（或分割）日 E 之後
  80 個交易日內股數第一次高於 E 前一日的日子 J，配股率 s = min(J 的股數 ÷ E 前一日股數 − 1, 除權前價 ÷ 參考價 − 1)，
  在 J 起調整（J 當天已知，沒有前視）；找不到股數跳升則不調整。減資、現金增資、可轉債轉換、員工股票、庫藏股註銷都留在 NSI 內。
- NSI = log 調整後股數_t − log 調整後股數_(t 往前 12 個月的最後一個交易日)；每期 1%／99% 截尾；全部產業（金融股另報 IC）。
- 樣本：前 500 名，2019-07 ~ 2026-04 每月最後一個交易日；兩段 2019-07–2022 / 2023–2026/04；驗證第 501–1000 名；2026-05 以後不用。
- 主檢定 (1)：產業內 Spearman IC(−NSI, 之後 20／60 個交易日報酬)，視窗須在 2026-05 前結束；Newey-West t（20 日落後 1、60 日落後 3）。
- 主檢定 (2)：每月 Fama-MacBeth：20 日報酬 = a + b·(−NSI) + 資產成長 AG + SUE + log 市值 + 過去 12-1 月報酬 + 產業固定效果；
  補：各變數用當月橫斷面百分位 − 0.5；AG 缺值（金融股與缺資料者）以 0 計。
- 可交易 (3)（(1)(2) 都成立才做）：(a) 單獨產業內前／後 30% 等權多空；(b) 2/3 SUE 百分位 + 1/3 (−NSI) 百分位（NSI 缺值以 0.5 計）；
  fv5 架構（借券條件 D、每 3 個換倉日換倉三份錯開、台指期對沖、單邊 0.29625% ＋ 借券費）。
- 通過：(1) 主樣本 20 日 IC 兩段 > 0、全期 t > 2；(2) Fama-MacBeth 控制 AG 後全期 t > 2；(3) 驗證樣本全期 20 日 IC 同號；
  (4) (b) 合成兩段 Sharpe 都不低於 fv5。
研究結果，非投資建議。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import asset_growth as agm  # noqa: E402
import borrow_capacity as bc  # noqa: E402
import corp_event_study as ce  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

FIN = ("金融保險", "金融業")
START = pd.Timestamp("2019-07-01")
JUMP_WIN = 80


def adj_log_shares(client, sid: str, days: pd.DatetimeIndex) -> tuple[pd.Series, int]:
    sh = client.get("TaiwanStockShareholding", sid, lp.EV_START, lp.EV_END)
    if sh.empty:
        return pd.Series(np.nan, index=days), 0
    s = pd.Series(sh["NumberOfSharesIssued"].astype(float).to_numpy(), index=pd.to_datetime(sh["date"]))
    s = s[~s.index.duplicated(keep="last")].sort_index().reindex(days).ffill().where(lambda x: x > 0)
    ev = []
    d = client.get("TaiwanStockDividendResult", sid, lp.EV_START, lp.EV_END)
    if not d.empty:
        d = d[d["stock_or_cache_dividend"].astype(str).str.contains("權")]
        ev += [(pd.Timestamp(r.date), float(r.before_price), float(r.after_price)) for r in d.itertuples()]
    sp = client.get("TaiwanStockSplitPrice", sid, lp.EV_START, lp.EV_END)
    if not sp.empty:
        ev += [(pd.Timestamp(r.date), float(r.before_price), float(r.after_price)) for r in sp.itertuples()]
    adj = pd.Series(0.0, index=days)
    n = 0
    v = s.to_numpy()
    for e, bp, ap in ev:
        if not (bp > 0 and ap > 0 and bp > ap):
            continue
        k = int(days.searchsorted(e))
        if k < 1 or k >= len(days) or not np.isfinite(v[k - 1]):
            continue
        base = v[k - 1]
        for j in range(k, min(k + JUMP_WIN, len(days))):
            if np.isfinite(v[j]) and v[j] > base * 1.0005:
                rate = min(v[j] / base - 1, bp / ap - 1)
                adj.iloc[j:] += np.log1p(rate)
                n += 1
                break
    return np.log(s) - adj, n


def nsi_matrix(S, client) -> tuple[pd.DataFrame, int]:
    cols, n_adj = {}, 0
    for t in S.tickers:
        ls, n = adj_log_shares(client, t.split(".")[0], S.days)
        cols[t] = ls
        n_adj += n
    L = pd.DataFrame(cols).shift(1)          # 換倉日用前一日股數
    k = S.days.searchsorted(S.days - pd.DateOffset(months=12), side="right") - 1
    base = L.iloc[np.clip(k, 0, None)].set_axis(S.days).where(pd.Series(k >= 0, index=S.days), axis=0)
    return L - base, n_adj


def ic_series(S, x, sector, h, sectors=None):
    out = {}
    for d in agm.month_ends(S.days, S.limit):
        if d < START:
            continue
        k = int(S.days.searchsorted(d))
        if k + h >= S.limit:
            continue
        mem = S.member.iloc[k].to_numpy(bool)
        v = agm.winsor(x.iloc[k][mem])
        if sectors is not None:
            v = v[sector.reindex(v.index).isin(sectors)]
        fwd = S.adj.iloc[k + h] / S.adj.iloc[k] - 1
        out[d] = lp.within_ic(-v, fwd, sector)
    return pd.Series(out).dropna()


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    S = ce.Sample(client, 1, 500, mkt, tx)
    nsi, n_adj = nsi_matrix(S, client)
    print(f"[I029] 主樣本 NSI 完成，股票股利／分割調整 {n_adj} 次", flush=True)
    ag, sector, _, _ = agm.sample_ag(S, client)
    ic20, ic60 = ic_series(S, nsi, sector, 20), ic_series(S, nsi, sector, 60)
    icf = ic_series(S, nsi, sector, 20, FIN)
    mom = (S.adj.shift(21) / S.adj.shift(252) - 1)
    fm, corr_ag, corr_sue, stats = {}, {}, {}, []
    for d in agm.month_ends(S.days, S.limit):
        if d < START:
            continue
        k = int(S.days.searchsorted(d))
        if k + 20 >= S.limit:
            continue
        mem = S.member.iloc[k].to_numpy(bool)
        x = agm.winsor(nsi.iloc[k][mem])
        stats.append((float((x > 0.01).mean()), float(x.median()), len(x)))
        df = pd.DataFrame({"y": S.adj.iloc[k + 20] / S.adj.iloc[k] - 1, "nsi": x, "ag": ag.iloc[k], "sue": S.sue.iloc[k],
                           "lm": S.lmcap.iloc[k], "mom": mom.iloc[k], "sec": sector}).dropna(subset=["y", "nsi", "sue", "lm", "mom"])
        if len(df) < 50:
            continue
        r = lambda c: (df[c].rank(pct=True) - 0.5).fillna(0.0)  # noqa: E731
        X = np.column_stack([np.ones(len(df)), -r("nsi"), r("ag"), r("sue"), r("lm"), r("mom"),
                             pd.get_dummies(df["sec"], drop_first=True, dtype=float).to_numpy()])
        beta, *_ = np.linalg.lstsq(X, df["y"].to_numpy(float), rcond=None)
        fm[d] = beta[1]
        corr_ag[d] = df["nsi"].rank().corr(df["ag"].rank())
        corr_sue[d] = df["nsi"].rank().corr(df["sue"].rank())
    fm = pd.Series(fm)
    V = ce.Sample(client, 501, 1000, mkt, tx)
    vnsi, _ = nsi_matrix(V, client)
    vsec = pd.Series({t: V.sector.get(t.split(".")[0], "NA") for t in V.tickers})
    v20, v60 = ic_series(V, vnsi, vsec, 20), ic_series(V, vnsi, vsec, 60)

    a20, a60, afm, av20, av60, af = agm.segs(ic20, 1), agm.segs(ic60, 3), agm.segs(fm, 1), agm.segs(v20, 1), agm.segs(v60, 3), agm.segs(icf, 1)
    c1 = a20["2019–2022"][0] > 0 and a20["2023–2026/04"][0] > 0 and a20["全期"][1] > 2
    c2 = afm["全期"][1] > 2
    c3 = av20["全期"][0] > 0
    st = np.array(stats)
    L = ["# I029 淨發行股數（自動產生）", "",
         "由 [analysis/net_issuance.py](../analysis/net_issuance.py) 產生；設計見程式開頭（看結果前固定）。"
         "IC 為產業內 Spearman（−NSI vs 之後報酬，−1～1，0 為無預測力；正值代表股數膨脹少的股票較好），括號為（Newey-West t 值，月份數）；"
         "Fama-MacBeth 係數為 −NSI 百分位差 1 對應的 20 日報酬差；Sharpe 為扣成本與台指期對沖後，格式 2019–2022 / 2023–2026/04。研究結果，非投資建議。", "",
         f"主樣本股票股利／分割調整 {n_adj} 次；每月 NSI 中位數 {np.median(st[:, 1]):+.2%}、NSI > 1% 的比例平均 {st[:, 0].mean():.0%}；"
         f"NSI 與 AG 的平均等級相關 {pd.Series(corr_ag).mean():+.2f}、與 SUE {pd.Series(corr_sue).mean():+.2f}。", "",
         "| 統計量 | 2019-07–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         "| **主樣本 IC 20 日（主檢定 1）** | " + " | ".join(agm.fmt(a20[s]) for s in a20) + " |",
         "| 主樣本 IC 60 日 | " + " | ".join(agm.fmt(a60[s]) for s in a60) + " |",
         "| **Fama-MacBeth −NSI 係數（控制 AG、SUE、市值、12-1 動能、產業；主檢定 2）** | " + " | ".join(agm.fmt(afm[s], True) for s in afm) + " |",
         "| 只報告：金融股內 IC 20 日 | " + " | ".join(agm.fmt(af[s]) for s in af) + " |",
         "| 驗證樣本 IC 20 日 | " + " | ".join(agm.fmt(av20[s]) for s in av20) + " |",
         "| 驗證樣本 IC 60 日 | " + " | ".join(agm.fmt(av60[s]) for s in av60) + " |", ""]
    c4 = None
    if c1 and c2:
        c = lp.prepare(500)
        sched = c.schedule
        fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
        quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
        close = bc.raw_close(c)
        cn = nsi.reindex(index=c.adj.index, columns=c.tickers)
        sue = lp.leg_scores(c, "sue")

        def shortable_at(d, q):
            n_short = max(1, int(c.member.loc[d].sum() * q))
            need = lt.K_CAPITAL / n_short / close.loc[d]
            return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

        def book(fn, q_in):
            parts = []
            for off in range(3):
                wd = {d: lt.ew_ls_buffer(fn(d), c.sector, shortable_at(d, q_in), q_in=q_in, q_keep=None) for d in sched[off::3]}
                parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)["ret"])
            x = pd.concat(parts, axis=1).mean(axis=1)
            x = x[x.index > sched[2]]
            return hc.stats(x) | {"full": lp.sharpe(x.dropna())}

        def neg(d):
            return -agm.winsor(cn.loc[d][c.member.loc[d].to_numpy(bool)])

        def comp(d):
            s = sue[d].dropna()
            return 2 / 3 * s.rank(pct=True) + 1 / 3 * neg(d).reindex(s.index).rank(pct=True).fillna(0.5)
        port = {"(a) 單獨 −NSI（產業內前／後 30%）": book(neg, 0.3), "fv5 原版（SUE）": book(lambda d: sue[d], 1 / 3),
                "(b) 合成：2/3 SUE ＋ 1/3 (−NSI)": book(comp, 1 / 3)}
        L += ["| 建構 | Sharpe | 全期 | 年化報酬 | 最大回撤 |", "|---|---|---|---|---|"]
        for k, s in port.items():
            L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} |")
        pb, p0 = port["(b) 合成：2/3 SUE ＋ 1/3 (−NSI)"], port["fv5 原版（SUE）"]
        c4 = pb["sh_oos"] >= p0["sh_oos"] and pb["sh_is"] >= p0["sh_is"]
        L.append("")
    mark = lambda b: "—（未執行）" if b is None else ("✓" if b else "✗")  # noqa: E731
    L += ["## 判定", "",
          f"1. 主樣本 20 日 IC 兩段 > 0、全期 t > 2 → {mark(c1)}",
          f"2. Fama-MacBeth 控制 AG 後全期 t > 2：{agm.fmt(afm['全期'], True)} → {mark(c2)}",
          f"3. 驗證樣本全期 20 日 IC > 0：{agm.fmt(av20['全期'])} → {mark(c3)}",
          f"4. 合成兩段 Sharpe 不低於 fv5 → {mark(c4)}{'（(1)(2) 未全部成立，依點子卡不做可交易版本）' if c4 is None else ''}", "",
          f"**結論：{'通過' if c1 and c2 and c3 and c4 else '未通過'}**"]
    (ROOT / "docs" / "net_issuance.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
