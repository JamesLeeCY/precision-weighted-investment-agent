"""事件研究：處置股、庫藏股買回（全市場市值前 N 檔）。

用法（於專案根目錄；先執行 fetch_events.py）：
    .venv/Scripts/python analysis/event_study.py 500
輸出 docs/event_study_top{N}.md 與 reports/legs/event_study_top{N}.csv（策略每日報酬）。

設計（看結果前固定）：
- 樣本：2019-01 ~ 2026-04 的事件，事件當日須為股票池成員（市值前 N 名）；報酬只用到 2026/04（之後保留給前瞻驗證）。
- 事件日（第 0 日）：公告當天（遇非交易日取之前最後一個交易日）；處置 = 證交所／櫃買「公布日期」（盤後公布，隔日起處置），
  庫藏股 = 董事會決議日期（多於盤後公告）。
  第 +1 日報酬包含公告後第一個開盤的跳空，用收盤價無法安全取得；**可交易視窗從第 +2 日起**（第 +1 日收盤進場）。
- 異常報酬：r − β × 加權指數含息報酬（β = 250 日，只用前一日以前的資料）。
- CAR 視窗：[−20, 0]（事件前）、[+1]（隔日，不可交易）、[+2, +6]、[+2, +21]、[+2, +61]。
  t 值：同一天的事件先平均，再對事件日做 t 檢定（避免同日事件互相相關造成高估）。
- 分組：處置 = 第一次 / 第二次以上、上市 / 上櫃；庫藏股 = 目的（1 轉讓員工、2 轉換、3 維護信用與股東權益）、
  預定買回股數占已發行股數（≥ 2% / < 2%）、事件前 20 日報酬（跌 ≥ 10% / 其他）。
- 策略（日曆時間組合）：庫藏股做多、處置做空；第 +1 日收盤進場、持有 20 個交易日；同時持有的事件等權；
  剩餘 β 以台指期對沖；換手 × 單邊 0.29625%，放空扣借券費（前 60 日成交量加權費率；借不到者以全市場中位數計，偏樂觀）。
  沒有事件時持有現金（報酬 0）。指標：Sharpe（2019–2022 / 2023–2026/04）、年化報酬、平均持有檔數。
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

EV_FROM = pd.Timestamp("2019-01-01")
WINDOWS = {"[−20, 0] 事件前": (-20, 0), "[+1] 隔日（不可交易）": (1, 1), "[+2, +6]": (2, 6), "[+2, +21]": (2, 21), "[+2, +61]": (2, 61)}
HOLD = 20
PURPOSE = {"1": "轉讓員工", "2": "轉換", "3": "維護信用與股東權益"}


def event_index(days: pd.DatetimeIndex, d: pd.Timestamp) -> int:
    """d 當天或之前最後一個交易日的位置。"""
    return int(days.searchsorted(d, side="right")) - 1


def car(ar: np.ndarray, k0: int, a: int, b: int, limit: int) -> float:
    lo, hi = k0 + a, k0 + b
    if lo < 0 or hi >= limit:
        return float("nan")
    seg = ar[lo:hi + 1]
    return float(np.nansum(seg)) if np.isfinite(seg).any() else float("nan")


def date_clustered(df: pd.DataFrame, col: str) -> tuple[float, float, int]:
    g = df.dropna(subset=[col]).groupby("t0")[col].mean()
    if len(g) < 5:
        return float("nan"), float("nan"), len(g)
    return float(g.mean()), float(g.mean() / g.std(ddof=1) * math.sqrt(len(g))), len(g)


def calendar_portfolio(events: pd.DataFrame, sign: float, days: pd.DatetimeIndex, limit: int) -> dict:
    """{日期: 權重 Series}：第 k0+1 日收盤建立，持有到 k0+1+HOLD 日收盤；同日持有者等權（含 sign）。"""
    active = {}
    for r in events.itertuples():
        s, e = r.k0 + 1, min(r.k0 + 1 + HOLD, limit - 1)
        for k in range(s, e):
            active.setdefault(days[k], set()).add(r.ticker)
    return {d: pd.Series(sign / len(v), index=sorted(v)) for d, v in active.items()}


def simulate_daily(wmap: dict, c, fee: pd.DataFrame | None) -> pd.DataFrame:
    """每日換倉：當日收盤持有 wmap[d]，賺隔日報酬；β 以台指期對沖；成本與借券費。"""
    days = c.rets.index
    days = days[(days >= EV_FROM) & (days < lp.HOLDOUT)]
    tx = c.tx.reindex(days).fillna(0.0)
    out, w_prev, b_prev = [], pd.Series(dtype=float), 0.0
    for k in range(len(days) - 1):
        d, nx = days[k], days[k + 1]
        w = wmap.get(d, pd.Series(dtype=float))
        b = float((w * c.betas.loc[d].reindex(w.index).fillna(1.0)).sum()) if len(w) else 0.0
        to = float(w.sub(w_prev, fill_value=0.0).abs().sum())
        ret = float((w * c.rets.loc[nx].reindex(w.index).fillna(0.0)).sum()) - b * tx[nx] if len(w) else 0.0
        ret -= to * lp.STOCK_COST + abs(b - b_prev) * lp.FUT_COST
        short = -w[w < 0]
        if fee is not None and len(short):
            rate = fee.loc[d].reindex(short.index).fillna(fee.loc[d].median()) / 100
            ret -= float((short * rate).sum()) / 252
        out.append((nx, ret, to, len(w)))
        w_prev, b_prev = w, b
    return pd.DataFrame(out, columns=["date", "ret", "turnover", "n"]).set_index("date")


def load_events(c, close: pd.DataFrame, days: pd.DatetimeIndex, limit: int):
    ev = ROOT / "data_cache" / "events"
    disp = pd.read_csv(ev / "disposition.csv", dtype={"stock_id": str}, parse_dates=["announce"])
    bb = pd.read_csv(ev / "buyback.csv", dtype={"stock_id": str, "purpose": str}, parse_dates=["board_date"])
    disp = disp.rename(columns={"announce": "date"}).drop_duplicates(["stock_id", "date"])
    bb = bb.rename(columns={"board_date": "date"})
    cap = np.exp(c.logcap)

    def attach(df):
        df = df[(df["date"] >= EV_FROM) & (df["date"] < lp.HOLDOUT)].copy()
        df["ticker"] = df["stock_id"] + ".TW"
        df = df[df["ticker"].isin(c.tickers)]
        df["k0"] = [event_index(days, d) for d in df["date"]]
        df = df[df["k0"] >= 0]
        df["t0"] = days[df["k0"].to_numpy()]
        df = df[[bool(c.member.at[t, tk]) for t, tk in zip(df["t0"], df["ticker"])]]
        df["seg"] = np.where(df["t0"] < lp.SPLIT, "2019–2022", "2023–2026/04")
        df["shares_out"] = [cap.at[t, tk] / close.at[t, tk] if close.at[t, tk] > 0 else np.nan for t, tk in zip(df["t0"], df["ticker"])]
        return df.reset_index(drop=True)
    return attach(disp), attach(bb)


def main(top_n: int):
    c = lp.prepare(top_n)
    days = c.rets.index
    limit = int(days.searchsorted(lp.HOLDOUT))          # 只用 2026-05 以前的報酬
    mkt = lp.market_tri(c.client).pct_change().reindex(days)
    ar = (c.rets - c.betas.fillna(1.0).mul(mkt, axis=0)).to_numpy()
    col = {t: j for j, t in enumerate(c.rets.columns)}
    close = bc.raw_close(c)
    disp, bb = load_events(c, close, days, limit)

    for df in (disp, bb):
        for name, (a, b) in WINDOWS.items():
            df[name] = [car(ar[:, col[t]], k, a, b, limit) for t, k in zip(df["ticker"], df["k0"])]
    bb["plan_pct"] = bb["plan_shares"] / bb["shares_out"]
    bb["big"] = bb["plan_pct"] >= 0.02
    bb["fell"] = bb["[−20, 0] 事件前"] <= -0.10
    bb["purpose_name"] = bb["purpose"].map(PURPOSE).fillna("其他")
    disp["nth"] = np.where(disp["second"], "第二次以上", "第一次")

    lines = [f"# 事件研究：處置股與庫藏股買回（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/event_study.py](../analysis/event_study.py) 產生；設計見程式開頭。"
             "CAR = 累積異常報酬（個股報酬 − β × 加權指數含息報酬），單位 %；括號為 t 值（同日事件先平均）。研究結果，非投資建議。", ""]

    def table(title, df, groups):
        nonlocal lines
        lines += [f"## {title}", "", "| 分組 | 事件數 | " + " | ".join(WINDOWS) + " |", "|---|---|" + "---|" * len(WINDOWS)]
        for gname, g in groups(df):
            cells = []
            for w in WINDOWS:
                m, t, _ = date_clustered(g, w)
                cells.append(f"{m:+.2%}（{t:.1f}）" if m == m else "—")
            lines.append(f"| {gname} | {len(g)} | " + " | ".join(cells) + " |")
        lines.append("")

    def seg_groups(extra):
        def f(df):
            out = [("全部", df)] + [(s, df[df["seg"] == s]) for s in ("2019–2022", "2023–2026/04")]
            return out + extra(df)
        return f

    table("1. 處置股", disp, seg_groups(lambda df: [(n, df[df["nth"] == n]) for n in ("第一次", "第二次以上")]
                                     + [(("上市" if m == "sii" else "上櫃"), df[df["market"] == m]) for m in ("sii", "otc")]))
    table("2. 庫藏股買回", bb, seg_groups(lambda df: [(f"目的：{p}", df[df["purpose_name"] == p]) for p in PURPOSE.values()]
                                       + [("預定買回 ≥ 已發行 2%", df[df["big"]]), ("預定買回 < 2%", df[~df["big"]]),
                                          ("事件前 20 日跌 ≥ 10%", df[df["fell"]]), ("事件前 20 日其他", df[~df["fell"]])]))

    # ---- 策略 ----
    fee = hc.lending_fees(c.client, c.tickers, days)
    sims = {"庫藏股做多（持有 20 日）": simulate_daily(calendar_portfolio(bb, 1.0, days, limit), c, None),
            "處置股做空（持有 20 日）": simulate_daily(calendar_portfolio(disp, -1.0, days, limit), c, fee)}
    pd.DataFrame({k: v["ret"] for k, v in sims.items()}).to_csv(ROOT / "reports" / "legs" / f"event_study_top{top_n}.csv")
    lines += ["## 3. 日曆時間策略（台指期對沖，扣交易成本與借券費；2019 ~ 2026/04）", "",
              "| 策略 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 年化波動 | 最大回撤 | 平均持有檔數 | 有持股的日子 | 年換手（倍） |",
              "|---|---|---|---|---|---|---|---|---|"]
    for name, sim in sims.items():
        s = hc.stats(sim["ret"])
        yrs = len(sim) / 252
        lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} | "
                     f"{sim.loc[sim['n'] > 0, 'n'].mean():.1f} | {(sim['n'] > 0).mean():.0%} | {sim['turnover'].sum() / yrs:.0f} |")
    lines += ["", "逐年 Sharpe：", ""]
    for name, sim in sims.items():
        lines.append(f"- {name}：" + "、".join(f"{y}:{v:+.1f}" for y, v in hc.stats(sim["ret"])["yearly"].items() if v == v))

    # ---- 事後追加（看過第 1 節結果後才加，非事前設定）：處置股做多 ----
    w = "[+2, +21]"
    x = disp.dropna(subset=[w])
    trim = x[x[w] <= x[w].quantile(0.95)]
    lines += ["", "## 4. 事後追加：處置股做多（看過第 1 節結果後才加入，屬事後檢定，需前瞻驗證）", "",
              f"[+2, +21] CAR：平均 {x[w].mean():+.2%}、中位數 {x[w].median():+.2%}、為正的比例 {(x[w] > 0).mean():.0%}；"
              f"去掉最高 5% 的事件後平均 {trim[w].mean():+.2%}（t {date_clustered(trim, w)[1]:.1f}）。", "",
              "逐年 [+2, +21] CAR（事件數）：" + "、".join(f"{y}:{g[w].mean():+.1%}（{len(g)}）" for y, g in x.groupby(x['t0'].dt.year)), ""]
    # 漲停買不到：進場日收盤漲 ≥ 9.5% 時順延到第一個非漲停日收盤進場
    R = c.rets.to_numpy()

    def delayed(t, k):
        j = k + 1
        while j < limit and R[j, col[t]] >= 0.095:
            j += 1
        return es_car(t, j), j - (k + 1)

    def es_car(t, j):
        return car(ar[:, col[t]], j, 1, HOLD, limit)
    dl = [delayed(t, k) for t, k in zip(disp["ticker"], disp["k0"])]
    disp["car_delayed"] = [a for a, _ in dl]
    lines.append(f"進場日（第 +1 日）收盤漲停（≥ 9.5%）的比例 {np.mean([b > 0 for _, b in dl]):.0%}；改在第一個非漲停日收盤進場後，"
                 "持有 20 日的 CAR：" + "、".join(
                     f"{n} {date_clustered(g, 'car_delayed')[0]:+.2%}（t {date_clustered(g, 'car_delayed')[1]:.1f}）"
                     for n, g in [("全部", disp), ("第一次", disp[~disp["second"]]), ("第二次以上", disp[disp["second"]]),
                                  ("2019–2022", disp[disp["seg"] == "2019–2022"]), ("2023–2026/04", disp[disp["seg"] == "2023–2026/04"])]) + "。")
    lines.append("")
    long_sims = {"處置股做多（持有 20 日）": simulate_daily(calendar_portfolio(disp, 1.0, days, limit), c, None),
                 "處置股做多：只做第二次以上": simulate_daily(calendar_portfolio(disp[disp["second"]], 1.0, days, limit), c, None)}
    lines += ["| 策略 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 年化波動 | 最大回撤 | 平均持有檔數 | 有持股的日子 | 年換手（倍） |",
              "|---|---|---|---|---|---|---|---|---|"]
    for name, sim in long_sims.items():
        s = hc.stats(sim["ret"])
        yrs = len(sim) / 252
        lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} | "
                     f"{sim.loc[sim['n'] > 0, 'n'].mean():.1f} | {(sim['n'] > 0).mean():.0%} | {sim['turnover'].sum() / yrs:.0f} |")
    lines += ["", "逐年 Sharpe：", ""]
    for name, sim in long_sims.items():
        lines.append(f"- {name}：" + "、".join(f"{y}:{v:+.1f}" for y, v in hc.stats(sim["ret"])["yearly"].items() if v == v))
    sims |= long_sims
    pd.DataFrame({k: v["ret"] for k, v in sims.items()}).to_csv(ROOT / "reports" / "legs" / f"event_study_top{top_n}.csv")
    (ROOT / "docs" / f"event_study_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
