"""I013 外資台指期／台指選擇權淨部位擇時（點子卡 research/ideas/I013-foreign-futures-options-positions-timing.md，檢定計畫看結果前固定）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/fut_inst_timing.py
輸出 docs/fut_inst_timing.md。

設計（依點子卡；點子卡沒寫清楚、在看結果前補上的細節以「補」標示）：
- 資料：FinMind TaiwanFuturesInstitutionalInvestors（TX、MTX）、TaiwanOptionInstitutionalInvestors（TXO），2018-06-05 起（3 次請求）；
  外資列為 institutional_investors 含「外資」者。樣本到 2026-04-30。
- 訊號：S1 = 外資（TX 淨未平倉口數 + MTX 淨未平倉口數 ÷ 4）的 5 日變化 ÷ 過去 250 日（含當日）同一變化的標準差；
  S2 = 外資 TXO 淨多方金額 [(買權多方未平倉金額 − 空方) − (賣權多方 − 空方)] 的 1 日變化 ÷ 過去 250 日標準差。前 250 日暖機。
- 時點：第 t 日訊號在第 t+1 日開盤執行；報酬用近月台指期（成交量最大的月契約）開盤價：第 t+1 日開盤 → 第 t+2 日開盤。
- 檢定一（預測迴歸）：未來 1 日、5 日開盤到開盤報酬對單一訊號迴歸，Newey-West 落後 5；判定用未加控制的係數（補），
  另報告加入過去 1 日、5 日台指期（收盤到收盤）報酬的版本，檢查外資是否只是追隨價格。
- 檢定二（規則）：淨曝險 e = 100%（訊號 > 0）或 50%（≤ 0）；持有 100% 0050，以放空台指期調整到 e（避險比例 1 − e，台指期部位以開盤價計）。
  對照：同平均曝險的固定比例（同樣以台指期開盤價執行）；差額的 t 值用 Newey-West 落後 5（補）。
- 檢定三（滾動前進）：候選 {S1, S2} × 變化期間 {1, 5, 20 日}；2021 起每年 1 月用之前資料選 Sharpe 最高者持有一年，2021 ~ 2026/04 為樣本外。
- 成本：台指期部位變動 × 0.005%；每月轉倉日扣 2 × 放空部位 × 0.005%（timing_futures.roll_days）。
- 期間：兩段 2018-06（暖機後約 2019-06 起）~ 2022-12、2023-01 ~ 2026-04。
- 通過（每個訊號各自判定，兩個訊號 Bonferroni：t > 2.24）：(1) 5 日預測係數兩段皆 > 0、全期 t > 2.24；
  (2) 規則 − 固定比例年化差兩段皆 > 0、全期 t > 2.24；(3) 滾動前進樣本外相對固定比例 > 0。
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
import timing_futures as tf  # noqa: E402
from data.fetch_financials import FinMindClient, get_total_return_prices  # noqa: E402
from sue_attention import nw_t  # noqa: E402

START, END, SPLIT = "2018-06-01", "2026-04-30", pd.Timestamp("2023-01-01")
WF_START = 2021
T_CRIT = 2.24
FUT_COST = tf.FUT_COST


def foreign(d: pd.DataFrame) -> pd.DataFrame:
    return d[d["institutional_investors"].astype(str).str.contains("外資")]


def signals(client) -> pd.DataFrame:
    out = {}
    for fid in ("TX", "MTX"):
        d = foreign(client.get("TaiwanFuturesInstitutionalInvestors", fid, START, "2026-05-31"))
        out[fid] = (d.set_index(pd.to_datetime(d["date"]))["long_open_interest_balance_volume"].astype(float)
                    - d.set_index(pd.to_datetime(d["date"]))["short_open_interest_balance_volume"].astype(float)).groupby(level=0).sum()
    fut_net = out["TX"].add(out["MTX"] / 4, fill_value=0.0)
    o = foreign(client.get("TaiwanOptionInstitutionalInvestors", "TXO", START, "2026-05-31")).copy()
    o["date"] = pd.to_datetime(o["date"])
    o["net"] = o["long_open_interest_balance_amount"].astype(float) - o["short_open_interest_balance_amount"].astype(float)
    p = o.pivot_table(index="date", columns="call_put", values="net", aggfunc="sum")
    opt_net = p["買權"] - p["賣權"]
    return pd.DataFrame({"fut": fut_net, "opt": opt_net}).sort_index()


def z_change(x: pd.Series, k: int) -> pd.Series:
    dx = x.diff(k)
    return dx / dx.rolling(250, min_periods=250).std()


def tx_open(client) -> tuple[pd.Series, pd.Series]:
    """近月台指期：r_oo[d] = 第 d 日開盤 → 下一交易日開盤（同一契約）；r_cc[d] = 收盤到收盤。"""
    parts = [client.get("TaiwanFuturesDaily", "TX", f"{y}-01-01", f"{y}-12-31") for y in range(2018, 2027)]
    d = pd.concat([x for x in parts if not x.empty])
    d = d[(d["trading_session"] == "position") & d["contract_date"].astype(str).str.fullmatch(r"\d{6}") & (d["open"].astype(float) > 0)].copy()
    d["date"] = pd.to_datetime(d["date"])
    front = d.sort_values(["date", "volume"]).groupby("date").tail(1).set_index("date")["contract_date"]
    po = d.pivot_table(index="date", columns="contract_date", values="open")
    pc = d.pivot_table(index="date", columns="contract_date", values="close")
    dates = list(po.index)
    oo, cc = {}, {}
    for k in range(len(dates) - 1):
        c = front[dates[k]]
        a, b = po.at[dates[k], c], po.at[dates[k + 1], c] if c in po.columns else np.nan
        oo[dates[k]] = b / a - 1 if a == a and b == b and a > 0 else 0.0
        c1 = front[dates[k + 1]]
        p0, p1 = pc.at[dates[k], c1] if c1 in pc.columns else np.nan, pc.at[dates[k + 1], c1]
        cc[dates[k + 1]] = p1 / p0 - 1 if p0 == p0 and p0 > 0 else 0.0
    return pd.Series(oo), pd.Series(cc)


def nw_reg(y: pd.Series, X: pd.DataFrame, lags: int = 5) -> tuple[np.ndarray, np.ndarray]:
    df = pd.concat([y.rename("y"), X], axis=1).dropna()
    Xm = np.column_stack([np.ones(len(df)), df[X.columns].to_numpy(float)])
    yv = df["y"].to_numpy(float)
    beta, *_ = np.linalg.lstsq(Xm, yv, rcond=None)
    e = yv - Xm @ beta
    S = (Xm * e[:, None]).T @ (Xm * e[:, None])
    for l in range(1, lags + 1):
        G = (Xm[l:] * e[l:, None]).T @ (Xm[:-l] * e[:-l, None])
        S += (1 - l / (lags + 1)) * (G + G.T)
    inv = np.linalg.pinv(Xm.T @ Xm)
    se = np.sqrt(np.diag(inv @ S @ inv))
    return beta, beta / se


def overlay(hedge: pd.Series, r0050: pd.Series, r_oo: pd.Series) -> pd.Series:
    """hedge[d]：第 d 日開盤到下一日開盤的放空比例；日損益 = 0050 收盤到收盤 − hedge × 台指期開盤到開盤 − 成本。"""
    h = hedge.reindex(r0050.index).ffill().fillna(0.0)
    cost = h.diff().abs().fillna(h.abs()) * FUT_COST + tf.roll_days(r0050.index).astype(float) * 2 * h * FUT_COST
    return r0050 - h * r_oo.reindex(r0050.index).fillna(0.0) - cost


def sharpe(x: pd.Series) -> float:
    x = x.dropna()
    return float(x.mean() / x.std() * math.sqrt(252)) if len(x) > 20 and x.std() > 0 else float("nan")


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    sig = signals(client)
    r_oo, r_cc = tx_open(client)
    px = get_total_return_prices(client, "0050.TW", "2018-01-01", "2026-05-31").set_index("date")["adj_close"].astype(float)
    r0050 = px.pct_change()
    cands = {f"{nm}・{k} 日": z_change(sig[col], k) for nm, col in (("S1 期貨", "fut"), ("S2 選擇權", "opt")) for k in (1, 5, 20)}
    main_sig = {"S1": cands["S1 期貨・5 日"], "S2": cands["S2 選擇權・1 日"]}
    days = r_oo.index[(r_oo.index >= START) & (r_oo.index <= END)]
    y1 = r_oo.shift(-1)                                             # 第 t 日訊號 → t+1 開盤到 t+2 開盤
    y5 = (1 + r_oo).rolling(5).apply(np.prod, raw=True).shift(-5) - 1
    past1, past5 = r_cc, (1 + r_cc).rolling(5).apply(np.prod, raw=True) - 1
    L = ["# I013 外資台指期／台指選擇權淨部位擇時（自動產生）", "",
         "由 [analysis/fut_inst_timing.py](../analysis/fut_inst_timing.py) 產生；設計見程式開頭（看結果前固定）。"
         "報酬為近月台指期開盤到開盤；係數為訊號每 1 個標準差對應的報酬，括號為 Newey-West t 值（落後 5）；"
         "規則差額 = 擇時 − 同平均曝險固定比例（皆以台指期執行、扣成本）的年化報酬差。研究結果，非投資建議。", "",
         f"資料：{sig.index.min():%Y-%m-%d} ~ {sig.index.max():%Y-%m-%d}，{len(sig):,} 個交易日；暖機 250 日後訊號從 "
         f"{main_sig['S1'].dropna().index.min():%Y-%m-%d} 起。", "",
         "## 1. 預測迴歸", "", "| 訊號 | 未來報酬 | 期間 | 只有訊號 | 加入過去 1、5 日報酬 | 日數 |", "|---|---|---|---|---|---|"]
    reg = {}
    for nm, s in main_sig.items():
        for h, y in (("1 日", y1), ("5 日", y5)):
            for lab, lo, hi in (("~2022", START, "2022-12-31"), ("2023~", "2023-01-01", END), ("全期", START, END)):
                X = pd.DataFrame({"s": s[(s.index >= lo) & (s.index <= hi)]})
                yy = y.reindex(X.index)
                b0, t0 = nw_reg(yy, X)
                b1, t1 = nw_reg(yy, X.assign(p1=past1.reindex(X.index), p5=past5.reindex(X.index)))
                n = int(pd.concat([yy, X], axis=1).dropna().shape[0])
                reg[(nm, h, lab)] = (b0[1], t0[1])
                L.append(f"| {nm} | {h} | {lab} | {b0[1]:+.3%}（{t0[1]:.1f}） | {b1[1]:+.3%}（{t1[1]:.1f}） | {n} |")
    r = r0050.reindex(days)
    seg1, seg2 = r.index < SPLIT, r.index >= SPLIT

    def rule(s: pd.Series) -> pd.Series:
        e = pd.Series(np.where(s > 0, 1.0, 0.5), index=s.index).where(s.notna())
        return (1 - e).shift(1)                                     # 第 t 日訊號 → 第 t+1 日開盤起的放空比例

    def compare(hedge: pd.Series, mask) -> dict:
        h = hedge.reindex(r.index)
        valid = mask & h.notna().to_numpy()
        hf = h.ffill().fillna(float(h[valid].mean()))
        fut = overlay(hf, r, r_oo)
        fixed = overlay(pd.Series(float(hf[valid].mean()), index=r.index), r, r_oo)
        d = (fut - fixed)[valid].dropna()
        return {"avg": 1 - float(hf[valid].mean()), "diff": float(d.mean() * 252), "t": nw_t(d, 5), "sh": sharpe(fut[valid]),
                "sh_fixed": sharpe(fixed[valid]), "sh_bh": sharpe(r[valid]), "turn": float(hf[valid].diff().abs().sum() / (valid.sum() / 252))}

    L += ["", "## 2. 規則：e = 100%（訊號 > 0）／50%（≤ 0），相對同平均曝險固定比例", "",
          "| 訊號 | 期間 | 平均曝險 | 年化差額（t） | Sharpe：規則 / 固定 / 0050 | 期貨年換手（倍） |", "|---|---|---|---|---|---|"]
    rr = {}
    for nm, s in main_sig.items():
        for lab, m in (("~2022", seg1), ("2023~", seg2), ("全期", np.ones(len(r), bool))):
            c = compare(rule(s), m)
            rr[(nm, lab)] = c
            L.append(f"| {nm} | {lab} | {c['avg']:.0%} | {c['diff']:+.2%}（{c['t']:.1f}） | {c['sh']:.2f} / {c['sh_fixed']:.2f} / {c['sh_bh']:.2f} | {c['turn']:.0f} |")
    # 滾動前進
    hedges = {k: rule(v) for k, v in cands.items()}
    wf = pd.Series(np.nan, index=r.index)
    picks = []
    for y in range(WF_START, 2027):
        hist = (r.index < f"{y}-01-01")

        def sh_hist(k):
            h = hedges[k].reindex(r.index)
            ok = hist & h.notna().to_numpy()
            return sharpe(overlay(h.ffill().fillna(0.25), r, r_oo)[ok]) if ok.sum() > 120 else -9
        best = max(hedges, key=sh_hist)
        picks.append((y, best))
        yr = (r.index >= f"{y}-01-01") & (r.index < f"{y + 1}-01-01")
        wf[yr] = hedges[best].reindex(r.index)[yr]
    cw = compare(wf, r.index >= f"{WF_START}-01-01")
    L += ["", f"## 3. 滾動前進（{WF_START} 起每年 1 月用之前資料選 6 種候選中 Sharpe 最高者）", "",
          f"樣本外 {WF_START} ~ 2026/04：年化差額 {cw['diff']:+.2%}（t {cw['t']:.1f}），Sharpe {cw['sh']:.2f} vs 固定 {cw['sh_fixed']:.2f}。", "",
          "每年選中：" + "、".join(f"{y} {k}" for y, k in picks) + "。", "", "## 判定（Bonferroni：t > 2.24）", ""]
    verdict = {}
    for nm in main_sig:
        a, b, f = reg[(nm, "5 日", "~2022")], reg[(nm, "5 日", "2023~")], reg[(nm, "5 日", "全期")]
        c1 = a[0] > 0 and b[0] > 0 and f[1] > T_CRIT
        ra, rb, rf = rr[(nm, "~2022")], rr[(nm, "2023~")], rr[(nm, "全期")]
        c2 = ra["diff"] > 0 and rb["diff"] > 0 and rf["t"] > T_CRIT
        c3 = cw["diff"] > 0
        verdict[nm] = c1 and c2 and c3
        L += [f"**{nm}**",
              f"1. 5 日係數兩段 > 0、全期 t > 2.24：{a[0]:+.3%} / {b[0]:+.3%}，全期 t {f[1]:.1f} → {'✓' if c1 else '✗'}",
              f"2. 規則年化差兩段 > 0、全期 t > 2.24：{ra['diff']:+.2%} / {rb['diff']:+.2%}，全期 t {rf['t']:.1f} → {'✓' if c2 else '✗'}",
              f"3. 滾動前進 > 0：{cw['diff']:+.2%} → {'✓' if c3 else '✗'}", ""]
    L.append(f"**結論：S1 {'通過' if verdict['S1'] else '未通過'}；S2 {'通過' if verdict['S2'] else '未通過'}**")
    (ROOT / "docs" / "fut_inst_timing.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
