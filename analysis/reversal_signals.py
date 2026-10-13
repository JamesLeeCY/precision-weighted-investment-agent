"""新一批反轉／動能訊號：隔夜與盤中報酬拆解、殘差反轉、季節性動能（全市場市值前 N 檔）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/reversal_signals.py 300
輸出 docs/reversal_signals_top{N}.md 與 reports/legs/reversal_signals_top{N}.csv。

設計（看結果前固定；方向依文獻事先決定，不依結果翻號）：
- 隔夜／盤中（Ho 等 2023，PBFJ）：隔夜報酬 = 還原開盤 ÷ 前一日還原收盤，盤中 = 收盤 ÷ 開盤（還原因子取自含息報酬指數，
  除權息日的落差歸在隔夜）。訊號為對數報酬加總：
  imom_12_1（盤中，252 日前 ~ 21 日前，方向 +）、omom_12_1（隔夜，同窗口，方向 −）、imom_1m（盤中 21 日，+）、omom_1m（隔夜 21 日，−）。
- 殘差反轉（Medhat & Novy-Marx；Blitz 等 2023）：每日殘差 = 個股報酬 − 同產業成員等權報酬；
  resrev = −Σ21 日殘差 ÷ 252 日殘差標準差；resrev_ex = 同上但排除每月 1–10 日（月營收公告期間）。
- 季節性動能（Fu & Hsieh 2024）：seasonal_mom = 12-1 動能，換倉日在 1–2 月時乘 −1。
- 所有訊號第 t 日只用 t−1 日以前的資料；同一套包裝（產業內 z → 20 日平均 → 對產業與 log 市值中性化）。
- 評估：產業內 20 日 IC（2019–2022 / 2023–2026，t 值）；等權多空（放空只用可借股票，資金 2 億、條件 D，每月換倉、無緩衝），
  扣交易成本與借券費、剩餘 β 以台指期對沖的 Sharpe；與月營收驚奇多空的日報酬相關；與月營收驚奇多空各半的合成 Sharpe。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import borrow_capacity as bc  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402

SIGNS = {"imom_12_1": 1, "omom_12_1": -1, "imom_1m": 1, "omom_1m": -1, "resrev": 1, "resrev_ex": 1, "seasonal_mom": 1}


def split_returns(adj: pd.DataFrame, open_: pd.DataFrame, close: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """隔夜與盤中報酬；(1 + 隔夜)(1 + 盤中) = 還原收盤報酬。"""
    f = adj / close
    overnight = open_ * f / adj.shift(1) - 1
    intraday = close / open_ - 1
    return overnight, intraday


def raw_signals(adj, open_, close, sector, member, schedule_months) -> dict:
    on, intra = split_returns(adj, open_, close)
    lon, lin = np.log1p(on), np.log1p(intra)
    sig = {
        "imom_12_1": lin.shift(21).rolling(231, min_periods=180).sum(),
        "omom_12_1": lon.shift(21).rolling(231, min_periods=180).sum(),
        "imom_1m": lin.rolling(21, min_periods=15).sum(),
        "omom_1m": lon.rolling(21, min_periods=15).sum(),
    }
    r = adj.pct_change().where(member)
    sec_mean = r.T.groupby(sector.reindex(r.columns)).transform("mean").T
    e = r - sec_mean
    vol = e.rolling(252, min_periods=120).std()
    sig["resrev"] = -e.rolling(21, min_periods=15).sum() / vol
    mask = pd.DataFrame(np.repeat((e.index.day > 10)[:, None], e.shape[1], axis=1), index=e.index, columns=e.columns)
    sig["resrev_ex"] = -e.where(mask, 0.0).rolling(21, min_periods=15).sum() / vol
    mom = adj.shift(21) / adj.shift(252) - 1
    flip = pd.Series(np.where(adj.index.month.isin([1, 2]), -1.0, 1.0), index=adj.index)
    sig["seasonal_mom"] = mom.mul(flip, axis=0)
    out = {}
    for k, v in sig.items():
        out[k] = (v * SIGNS[k]).shift(1)          # 第 t 日只用 t−1 日以前
    return out


def ic_stats(ics: pd.Series) -> dict:
    out = {}
    for seg, m in (("oos", ics.index < lp.SPLIT), ("is", ics.index >= lp.SPLIT)):
        x = ics[m].dropna()
        out[seg] = (x.mean(), x.mean() / (x.std(ddof=1) / math.sqrt(len(x))) if len(x) > 2 else float("nan"))
    return out


def main(top_n: int):
    c = lp.prepare(top_n)
    opens, closes = {}, {}
    for sid in c.ids:
        px = c.client.get("TaiwanStockPrice", sid, lp.PX_START)
        if not px.empty:
            px = px[(px["close"].astype(float) > 0) & (px["open"].astype(float) > 0)]
            idx = pd.to_datetime(px["date"])
            opens[sid + ".TW"] = pd.Series(px["open"].astype(float).to_numpy(), index=idx)
            closes[sid + ".TW"] = pd.Series(px["close"].astype(float).to_numpy(), index=idx)
    open_ = pd.DataFrame(opens).reindex(index=c.adj.index, columns=c.tickers)
    close = pd.DataFrame(closes).reindex(index=c.adj.index, columns=c.tickers)
    raws = raw_signals(c.adj, open_, close, c.sector, c.member, None)

    fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    sched = c.schedule
    short_ok = {d: shortable_at(d) for d in sched}

    def ls(scores):
        wd = {d: lt.ew_ls_buffer(scores[d], c.sector, short_ok[d], q_keep=None) for d in sched}
        sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, sched, fee=fee)
        return sim

    sue_sim = ls(lp.leg_scores(c, "sue"))
    sue_ret = sue_sim["ret"]
    series = {"sue": sue_ret}
    rows = []
    for name, raw in raws.items():
        wz = lp.wrap(raw, c.member, c.sector)
        scores = {d: lp.neutralize(wz.loc[d], c.sector, c.logcap.loc[d]) for d in sched}
        ics = pd.Series({d: lp.within_ic(scores[d], c.fwd20.loc[d], c.sector) for d in sched})
        sim = ls(scores)
        s = hc.stats(sim["ret"], sim)
        blend = hc.stats(0.5 * sim["ret"] + 0.5 * sue_ret.reindex(sim.index))
        rows.append((name, ic_stats(ics), s, float(sim["ret"].corr(sue_ret)), blend))
        series[name] = sim["ret"]
        print(f"  {name}: IC {rows[-1][1]['oos'][0]:+.3f} / {rows[-1][1]['is'][0]:+.3f}；多空 {s['sh_oos']:.2f} / {s['sh_is']:.2f}", flush=True)
    pd.DataFrame(series).to_csv(ROOT / "reports" / "legs" / f"reversal_signals_top{top_n}.csv")

    ss = hc.stats(sue_ret, sue_sim)
    names = {"imom_12_1": "盤中動能 12-1（+）", "omom_12_1": "隔夜動能 12-1（−，反轉）", "imom_1m": "盤中 1 個月（+）",
             "omom_1m": "隔夜 1 個月（−，反轉）", "resrev": "殘差反轉（產業調整、波動標準化）", "resrev_ex": "殘差反轉，排除每月 1–10 日",
             "seasonal_mom": "季節性動能（1–2 月反轉、3–12 月動能）"}
    lines = [f"# 隔夜／盤中拆解、殘差反轉、季節性動能（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/reversal_signals.py](../analysis/reversal_signals.py) 產生；設計見程式開頭。IC 為產業內 20 日 Spearman IC（−1～1，括號 t 值）；"
             "多空 = 等權多空、放空只用可借股票（資金 2 億），扣交易成本與借券費、剩餘 β 以台指期對沖的年化 Sharpe；"
             "兩段為 2019–2022 / 2023–2026/04。研究結果，非投資建議。", "",
             f"對照：月營收驚奇多空 Sharpe {ss['sh_oos']:.2f} / {ss['sh_is']:.2f}（年換手 {ss['turnover']:.1f}）。", "",
             "| 訊號（方向） | IC 2019–2022 | 2023–2026 | 多空 Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 年換手（倍） | 與月營收驚奇多空相關 | 各半合成 Sharpe |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, ic, s, corr, bl in rows:
        lines.append(f"| {names[name]} | {ic['oos'][0]:+.3f}（{ic['oos'][1]:+.1f}） | {ic['is'][0]:+.3f}（{ic['is'][1]:+.1f}） | "
                     f"{s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['turnover']:.1f} | {corr:+.2f} | {bl['sh_oos']:.2f} / {bl['sh_is']:.2f} |")
    lines += ["", "逐年多空 Sharpe：", ""]
    for name, ic, s, corr, bl in rows:
        lines.append(f"- {names[name]}：" + "、".join(f"{y}:{v:+.1f}" for y, v in s["yearly"].items() if v == v))
    (ROOT / "docs" / f"reversal_signals_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
