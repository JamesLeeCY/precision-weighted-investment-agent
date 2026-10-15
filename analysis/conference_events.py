"""I010 法人說明會：券商受邀法說會的會後報酬（點子卡 research/ideas/I010-investor-conference.md 的檢定計畫，看結果前固定）。

用法（於專案根目錄；先執行 fetch_corp_events.py conference）：
    .venv/Scripts/python analysis/conference_events.py
輸出 docs/conference_events.md 與 reports/legs/conference_events.csv。

- 事件：公開資訊觀測站法人說明會一覽表，召開日 2019-01 ~ 2026-04。
  受邀 = 擇要訊息含「受邀」或「邀請」，或含「證券」「投顧」「論壇」「Conference」「Summit」且不含「財務報告」；其餘為自辦。
  首次召開 = 召開日前 3 年（756 個交易日）一覽表中沒有該公司紀錄（一覽表 2016 年起）。
- t0 = 召開日（多日取第一天；非交易日取下一交易日），第 +1 日收盤進場。
- 去重疊：同公司 40 個交易日內的受邀事件只取第一個；受邀與自辦在 ±5 個交易日內同時發生時歸為自辦。
- 主檢定排除：t0 ±5 個交易日內有同公司自辦法說會或 I007 年度董事會決議日（股利分派彙總表），或落在季報法定期限
  （3/31、5/15、8/14、11/14）前 10 個交易日內的受邀事件；報告排除比例。
- 異常報酬：還原報酬 − β × 加權指數含息（250 日 β）；t 值以 t0 聚集。視窗 [−20, −1]（描述）、[−1, +1]（反應）、
  [+2, +20]、[+2, +40]（主要）、[+2, +60]（首次召開的主要視窗）。
- 截面迴歸（每段）：CAR[+2,+40] = a + 事件前 CAR[−20,−1] + SUE + log 市值 + 20 日周轉率 + 距最近自辦法說會天數（排名 −0.5～+0.5）
  + 產業與年度虛擬變數（去均值，使截距 = 控制後平均異常報酬）；標準誤依 t0 分群。
- 可交易：(i) 放空受邀事件股中條件 D 通過者（1,000 萬、2 億），第 +1 日收盤到第 +40 日；(ii) fv5 做多名單排除過去 40 個交易日內有受邀法說會者。
- 通過（全部成立）：(1) 主樣本受邀 CAR[+2,+40] 兩段 < 0、全期 t < −2；(2) 迴歸截距全期 < 0 且 t < −2、兩段同號；
  (3) 驗證樣本全期 < 0 且 t < −2；(4) 放空（2 億）兩段 Sharpe > 0，或濾網版兩段優於 fv5。(1)–(3) 成立而 (4) 不成立 → partial；
  方向為正只記錄為反向發現。
- 未做：用重大訊息公告日當 t0 的子樣本（需另抓約 200–270 次全文檢索）；法說會次數年變動腿。
研究結果，非投資建議。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import borrow_capacity as bc  # noqa: E402
import corp_event_study as ce  # noqa: E402
import dividend_surprise as dsu  # noqa: E402
import earnings_board_date as ebd  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

WINDOWS = {"[−20, −1]": (-20, -1), "[−1, +1]": (-1, 1), "[+2, +20]": (2, 20), "[+2, +40]": (2, 40), "[+2, +60]": (2, 60)}
MAIN = "[+2, +40]"
INVITE_KW = ("受邀", "邀請")
HOST_KW = ("證券", "投顧", "論壇", "Conference", "Summit", "conference", "summit")


def is_invited(summary: str) -> bool:
    s = str(summary)
    return any(k in s for k in INVITE_KW) or (any(k in s for k in HOST_KW) and "財務報告" not in s)


def build_events(days: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict]:
    c = pd.read_csv(ROOT / "data_cache" / "events" / "conferences.csv", dtype={"stock_id": str}, parse_dates=["date", "date_end"])
    c = c[c["stock_id"].str.fullmatch(r"\d{4}")].copy()
    c["invited"] = c["summary"].map(is_invited)
    c["k"] = days.searchsorted(c["date"], side="left")
    c = c[c["k"] < len(days)].copy()
    c["t0"] = days[c["k"].to_numpy()]
    first_seen = {}
    firsts = []
    for r in c.sort_values("date").itertuples():
        prev = first_seen.get(r.stock_id)
        firsts.append(prev is None or (r.k - prev) > 756)
        first_seen[r.stock_id] = r.k
    c = c.sort_values("date")
    c["first_time"] = firsts
    c.loc[c["date"] < "2019-01-01", "first_time"] = False                  # 2016–2018 只用來判斷首次
    self_k = c[~c["invited"]].groupby("stock_id")["k"].apply(lambda s: np.array(sorted(s)))
    # 受邀與自辦 ±5 日內同時 → 歸自辦；同公司 40 日內受邀只取第一個
    keep, last = [], {}
    for r in c[c["invited"]].itertuples():
        sk = self_k.get(r.stock_id, np.array([]))
        if len(sk) and np.abs(sk - r.k).min() <= 5:
            continue
        if r.stock_id in last and r.k - last[r.stock_id] <= 40:
            continue
        last[r.stock_id] = r.k
        keep.append(r.Index)
    inv = c.loc[keep].copy()
    inv["grp"] = "受邀"
    slf = c[~c["invited"]].drop_duplicates(["stock_id", "k"]).copy()
    slf["grp"] = "自辦"
    ev = pd.concat([inv, slf])
    ev = ev[(ev["date"] >= "2019-01-01") & (ev["date"] < lp.HOLDOUT)].copy()
    # 主檢定排除（只對受邀）
    board = ebd.annual_events(dsu.fetch_mops())[["stock_id", "board"]].dropna()
    board["k"] = days.searchsorted(board["board"], side="left")
    bk = board.groupby("stock_id")["k"].apply(lambda s: np.array(sorted(s)))
    deadlines = [pd.Timestamp(y, m, d) for y in range(2019, 2027) for m, d in ((3, 31), (5, 15), (8, 14), (11, 14))]
    dk = np.array([days.searchsorted(x, side="right") - 1 for x in deadlines])
    excl = []
    for r in ev.itertuples():
        if r.grp != "受邀":
            excl.append(False)
            continue
        sk, b = self_k.get(r.stock_id, np.array([])), bk.get(r.stock_id, np.array([]))
        near_self = len(sk) and np.abs(sk - r.k).min() <= 5
        near_board = len(b) and np.abs(b - r.k).min() <= 5
        before_deadline = np.any((dk - r.k >= 0) & (dk - r.k <= 10))
        excl.append(bool(near_self or near_board or before_deadline))
    ev["excluded"] = excl
    ev["days_since_self"] = [((r.k - sk[sk <= r.k].max()) if len(sk := self_k.get(r.stock_id, np.array([]))) and (sk <= r.k).any() else np.nan)
                             for r in ev.itertuples()]
    stats = {"invited_raw": int(c["invited"].sum()), "self_raw": int((~c["invited"]).sum())}
    return ev.reset_index(drop=True), stats


def add_cars(S: ce.Sample, ev: pd.DataFrame) -> pd.DataFrame:
    ev = S.events(ev.drop(columns=["t0", "k"], errors="ignore"))
    for w, (a, b) in WINDOWS.items():
        ev[w] = [float(S.car(S.col[t], k + a, k + b)) for t, k in zip(ev["ticker"], ev["k0"])]
    ev["seg"] = np.where(ev["t0"] < lp.SPLIT, "2019–2022", "2023–2026/04")
    return ev


def regression(S: ce.Sample, ev: pd.DataFrame, client) -> dict:
    money = {}
    for t in ev["ticker"].unique():
        px = client.get("TaiwanStockPrice", t.split(".")[0], lp.PX_START)
        if not px.empty:
            money[t] = pd.Series(px["Trading_money"].astype(float).to_numpy(), index=pd.to_datetime(px["date"]))
    M = pd.DataFrame(money).reindex(S.days)
    turn = M.rolling(20, min_periods=10).sum().shift(1)
    df = ev.copy()
    df["sue"] = [S.sue.iat[k, S.col[t]] for t, k in zip(df["ticker"], df["k0"])]
    df["lm"] = [S.lmcap.iat[k, S.col[t]] for t, k in zip(df["ticker"], df["k0"])]
    df["turn"] = [turn.at[S.days[k], t] / np.exp(lm) if t in turn.columns and lm == lm else np.nan for t, k, lm in zip(df["ticker"], df["k0"], df["lm"])]
    df["dss"] = df["days_since_self"].fillna(df["days_since_self"].max())
    df["year"] = df["t0"].dt.year
    out = {}
    for seg, g in (("2019–2022", df[df["seg"] == "2019–2022"]), ("2023–2026/04", df[df["seg"] == "2023–2026/04"]), ("全期", df)):
        g = g.dropna(subset=[MAIN, "[−20, −1]", "sue", "lm", "turn"]).copy()
        if len(g) < 30:
            out[seg] = {"a": np.nan, "t": np.nan, "b_pre": np.nan, "t_pre": np.nan, "n": len(g)}
            continue
        for v in ("[−20, −1]", "sue", "turn", "dss"):
            g[v + "_r"] = g.groupby("year")[v].rank(pct=True) - 0.5
        D = pd.concat([pd.get_dummies(g["ticker"].str[:4].map(S.sector).fillna("NA"), drop_first=True, dtype=float),
                       pd.get_dummies(g["year"], drop_first=True, dtype=float, prefix="y")], axis=1)
        D = D - D.mean()
        X = pd.concat([pd.Series(1.0, index=g.index, name="c"), g[["[−20, −1]_r", "sue_r", "turn_r", "dss_r"]],
                       (g["lm"] - g["lm"].mean()).rename("lm"), D], axis=1)
        beta, se = dsu.ols_cluster(g[MAIN].to_numpy(float), X.to_numpy(float), g["t0"].astype(str).to_numpy())
        out[seg] = {"a": beta[0], "t": beta[0] / se[0], "b_pre": beta[1], "t_pre": beta[1] / se[1], "n": len(g)}
    return out


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    lines = ["# I010 法人說明會：券商受邀法說會的會後報酬（自動產生）", "",
             "由 [analysis/conference_events.py](../analysis/conference_events.py) 產生；檢定計畫見點子卡 "
             "[I010](../research/ideas/I010-investor-conference.md)（看結果前固定）。CAR = 累積異常報酬（個股 − β × 加權指數含息），"
             "括號為 t 值（同一召開日先平均）。研究結果，非投資建議。", ""]
    res = {}
    for name, (lo, hi) in (("前 500 名（主樣本）", (1, 500)), ("第 501–1000 名（驗證）", (501, 1000))):
        S = ce.Sample(client, lo, hi, mkt, tx)
        raw, st = build_events(S.days)
        ev = add_cars(S, raw)
        inv = ev[ev["grp"] == "受邀"]
        main_ev = inv[~inv["excluded"]]
        slf = ev[ev["grp"] == "自辦"]
        reg = regression(S, main_ev, client)
        res[name] = {"S": S, "main": main_ev, "reg": reg}
        lines += [f"## {name}", "",
                  f"一覽表（2016 ~ 2026）受邀 {st['invited_raw']} 場、自辦 {st['self_raw']} 場（全市場）。股票池內 2019-01 ~ 2026-04："
                  f"受邀事件（去重疊後）{len(inv)} 筆，其中因鄰近自辦法說會、年度董事會或季報期限而排除 {int(inv['excluded'].sum())} 筆"
                  f"（{inv['excluded'].mean():.0%}），主檢定 {len(main_ev)} 筆；自辦 {len(slf)} 筆；首次召開 {int(ev['first_time'].sum())} 筆。", "",
                  "| 分組 | 期間 | 事件數 | " + " | ".join(WINDOWS) + " |", "|---|---|---|" + "---|" * len(WINDOWS)]
        groups = [("受邀（主檢定）", main_ev, True), ("受邀（含被排除者）", inv, False), ("自辦（對照，不判定）", slf, False),
                  ("首次召開", ev[ev["first_time"]], False),
                  ("受邀：國外或線上場", main_ev[main_ev["place"].fillna("").str.contains("線上|視訊|online|Online|香港|新加坡|美國|日本|英國|紐約|倫敦|東京|Hong Kong|Singapore|New York|London|Tokyo")], False),
                  ("受邀：排除金融業", main_ev[~main_ev["ticker"].str[:4].map(S.sector).fillna("").str.contains("金融")], False)]
        for g, gdf, segs in groups:
            parts = ([("2019–2022", gdf[gdf["seg"] == "2019–2022"]), ("2023–2026/04", gdf[gdf["seg"] == "2023–2026/04"])] if segs else []) + [("全期", gdf)]
            for seg, sdf in parts:
                lines.append(f"| {g} | {seg} | {len(sdf)} | " + " | ".join(ce.fmt(ce.clustered(sdf, w)) for w in WINDOWS) + " |")
        up = np.mean([S.rets.iat[k + 1, S.col[t]] >= 0.095 for t, k in zip(main_ev["ticker"], main_ev["k0"])])
        lines += ["", f"主檢定事件第 +1 日漲停比例 {up:.1%}。", "",
                  "截面迴歸（CAR[+2,+40]；控制事件前 20 日報酬、SUE、log 市值、20 日周轉率、距最近自辦法說會天數、產業與年度；依召開日分群）：", "",
                  "| 期間 | 事件數 | 截距（控制後平均異常報酬） | 事件前報酬係數 |", "|---|---|---|---|"]
        for seg, r in reg.items():
            lines.append(f"| {seg} | {r['n']} | {r['a']:+.2%}（{r['t']:.1f}） | {r['b_pre']:+.2%}（{r['t_pre']:.1f}） |")
        lines.append("")
        if lo == 1:
            fee = hc.lending_fees(client, S.tickers, S.days)
            quota, lend60 = bc.load_short_data(client, S.tickers, S.days)
            A = ce.short_version(S, main_ev, 39, fee, quota, lend60)
            res[name]["A"] = A
            lines += ["可交易 (i)（第 +1 日收盤放空到第 +40 日，只放空條件 D 通過者，台指期對沖，扣成本與借券費）：", "",
                      "| 資金 | 可放空比例 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 最大回撤 | 有部位的日子 |", "|---|---|---|---|---|---|---|"]
            for lab, a in A.items():
                s = a["stats"]
                lines.append(f"| {lab} | {a['cover']:.0%} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} | {a['active']:.0%} |")
            lines.append("")
    B = ce.fv5_filter(res["前 500 名（主樣本）"]["main"][["ticker", "t0"]], 40)
    lines += ["## 可交易 (ii)：fv5 做多名單排除過去 40 日內有受邀法說會者", "", f"被排除的做多權重平均 {B['share']:.1%}。", "",
              "| 版本 | Sharpe 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|"]
    for k in ("fv5 建構（基準）", "濾網版"):
        lines.append(f"| {k} | {B[k]['sh_oos']:.2f} | {B[k]['sh_is']:.2f} | {B[k]['full']:.2f} |")
    m = res["前 500 名（主樣本）"]["main"]
    v = res["第 501–1000 名（驗證）"]["main"]
    reg = res["前 500 名（主樣本）"]["reg"]
    a = ce.clustered(m[m["seg"] == "2019–2022"], MAIN)
    b = ce.clustered(m[m["seg"] == "2023–2026/04"], MAIN)
    f = ce.clustered(m, MAIN)
    vv = ce.clustered(v, MAIN)
    c1 = a[0] < 0 and b[0] < 0 and f[1] < -2
    c2 = reg["全期"]["a"] < 0 and reg["全期"]["t"] < -2 and np.sign(reg["2019–2022"]["a"]) == np.sign(reg["2023–2026/04"]["a"])
    c3 = vv[0] < 0 and vv[1] < -2
    A2 = res["前 500 名（主樣本）"]["A"]["2 億"]
    c4 = (A2["stats"]["sh_oos"] > 0 and A2["stats"]["sh_is"] > 0) or \
         (B["濾網版"]["sh_oos"] > B["fv5 建構（基準）"]["sh_oos"] and B["濾網版"]["sh_is"] > B["fv5 建構（基準）"]["sh_is"])
    overall = "通過" if c1 and c2 and c3 and c4 else ("partial" if c1 and c2 and c3 else "未通過")
    if f[0] > 0 and f[1] > 2:
        overall += "（方向為正，只記錄為反向發現）"
    lines += ["", "## 判定", "",
              f"1. 主樣本受邀 {MAIN} 兩段 < 0、全期 t < −2：{ce.fmt(a)}、{ce.fmt(b)}、全期 {ce.fmt(f)} → {'✓' if c1 else '✗'}",
              f"2. 迴歸截距全期 < 0 且 t < −2、兩段同號：全期 {reg['全期']['a']:+.2%}（{reg['全期']['t']:.1f}） → {'✓' if c2 else '✗'}",
              f"3. 驗證樣本全期 < 0 且 t < −2：{ce.fmt(vv)} → {'✓' if c3 else '✗'}",
              f"4. 可交易（放空 2 億兩段 Sharpe > 0，或濾網版兩段優於 fv5）：{'✓' if c4 else '✗'}", "", f"**結論：{overall}**"]
    pd.DataFrame({k: x["ret"] for k, x in res["前 500 名（主樣本）"]["A"].items()}).to_csv(ROOT / "reports" / "legs" / "conference_events.csv")
    (ROOT / "docs" / "conference_events.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
