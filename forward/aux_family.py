"""fv5 家族前瞻輔助判定：機制指標與非劣性（點子卡 I053；使用者 2026-10-24 決定登錄，登錄時尚無任何 live 機制指標）。

用法（於專案根目錄）：
    .venv/Scripts/python forward/aux_family.py
輸出 forward/AUX_REPORT.md。每日由 forward/run_forward.py auto 在 compare_family 之後呼叫 auto()。
價格與 fv5 前瞻共用快照快取（fv5.snapshot、fv5.load_prices 同鍵），通常不需新的 FinMind 請求。

規則（事前固定；不取代 docs/forward_validation.md 的正式規則）：
- 只用 mode = live 的預測日與段；backfill 不計。M_s 用 fv5s 的 live 預測日；fv5 的日報酬只取與規格 live 段相同的日期。
- M_s（fv5s、fv5x）：每個 live 預測日，fv5 成員中 SUE 分數與 S1 都有值者，60 日報酬（預測日收盤起 60 個交易日）的產業內百分位 − 0.5
  對 SUE 百分位 − 0.5、S1 百分位 − 0.5 迴歸，取 S1 係數；60 日視窗完整者才計入；單尾 t（Newey-West 落後 2）。
- M_v（fv5v、fv5x）：live 段的日淨報酬（重建方式同各規格 resolve：在場各份資金日報酬加總 ÷ 3），ln(Var(規格) ÷ Var(fv5))，
  以區塊長度 20 日的成對區塊 bootstrap（5,000 次）估標準誤，t = −ln ρ ÷ se（單尾）。
- 機制通過：同一規格的機制指標（fv5x 兩項、fv5s 只有 M_s、fv5v 只有 M_v）做 Holm 校正，家族單尾 10%。
- 非劣性 N_k：波動調整後每段報酬差 d_k（同 forward/compare_family.py、forward/family_scale.yaml）的 90% 單尾下界 > −0.05%／段（下界 = 平均 − 1.2816 × 標準差 ÷ √n）。
- 標記：機制通過且非劣性通過 →「機制確認、報酬非劣」，提交使用者決定是否提前採用；
  live 12 段以上且任一機制指標 t < −1 →「機制失效」，建議停止該規格的記錄（由使用者決定）。
- fv5e 沒有進入 Holm 的機制指標（ESUE 的 IC 差只報告、本程式不計算），只報告非劣性。
研究記錄，非投資建議。
"""
from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))

from forward import compare_family as cf  # noqa: E402

REPORT = ROOT / "forward" / "AUX_REPORT.md"
PUBLISH_FILES = ["forward/AUX_REPORT.md"]
MECH = {"fv5s": ("M_s",), "fv5v": ("M_v",), "fv5x": ("M_s", "M_v")}
NI_MARGIN = -0.0005


def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def live_dates() -> list[str]:
    """fv5s 的 live 預測日（S1 只在 fv5s 記錄）。"""
    from forward import run_forward_fv5s as fv5s
    from forward import run_forward as fv1
    p = fv1.read_csv(fv5s.PREDICTIONS, fv5s.PRED_COLUMNS)
    return sorted(p.loc[p["mode"] == "live", "as_of_date"].unique())


def m_s(dates: list[str]) -> pd.Series:
    from forward import run_forward as fv1
    from forward import run_forward_fv5 as fv5
    from forward import run_forward_fv5s as fv5s
    if not dates:
        return pd.Series(dtype=float)
    cal = pd.DatetimeIndex(fv1.trading_calendar(fv5.snapshot(dt.date.today().strftime("%Y-%m-%d")), "2025-01-01"))
    dates = [a for a in dates if int(cal.searchsorted(pd.Timestamp(a))) + 60 < len(cal)]   # 只算 60 日視窗已完整者
    if not dates:
        return pd.Series(dtype=float)
    p5 = fv1.read_csv(fv5.PREDICTIONS, fv5.PRED_COLUMNS)
    ps = fv1.read_csv(fv5s.PREDICTIONS, fv5s.PRED_COLUMNS)
    today = dt.date.today().strftime("%Y-%m-%d")
    client = fv5.snapshot(today)
    start = fv5.data_start(pd.Timestamp(sorted(p5["as_of_date"].unique())[0]))
    adj, _ = fv5.load_prices(client, sorted(set(p5["ticker"])), start, today)
    out = {}
    for a in dates:
        g = p5[p5["as_of_date"] == a].set_index("ticker")
        s1 = ps[ps["as_of_date"] == a].set_index("ticker")["s1"] if (ps["as_of_date"] == a).any() else pd.Series(dtype=float)
        k = int(adj.index.searchsorted(pd.Timestamp(a)))
        if k + 60 >= len(adj.index):
            continue
        fwd = adj.iloc[k + 60] / adj.iloc[k] - 1
        df = pd.DataFrame({"y": fwd.reindex(g.index), "sue": g["score"].astype(float), "s1": s1.reindex(g.index).astype(float),
                           "sec": g["sector"]}).dropna()
        if len(df) < 50:
            continue
        y = df["y"].groupby(df["sec"]).rank(pct=True) - 0.5
        X = np.column_stack([np.ones(len(df)), df["sue"].rank(pct=True) - 0.5, df["s1"].rank(pct=True) - 0.5])
        b, *_ = np.linalg.lstsq(X, y.to_numpy(), rcond=None)
        out[a] = b[2]
    return pd.Series(out, dtype=float)


def daily_book(spec_mod, fv5, live: set[str]) -> pd.Series:
    """重建規格在 live 段的日淨報酬（同 resolve）。"""
    from forward import run_forward as fv1
    import leg_probe as lp
    preds = fv1.read_csv(spec_mod.PREDICTIONS, spec_mod.PRED_COLUMNS)
    per = fv1.read_csv(spec_mod.PERIODS, spec_mod.PERIOD_COLUMNS)
    per = per[per["mode"] == "live"]
    if per.empty:
        return pd.Series(dtype=float)
    today = dt.date.today().strftime("%Y-%m-%d")
    client = fv5.snapshot(today)
    predicted = sorted(preds["as_of_date"].unique())
    start = fv5.data_start(pd.Timestamp(predicted[0]))
    adj, _ = fv5.load_prices(client, sorted(set(preds["ticker"])), start, today)
    rets, tx = adj.pct_change(), lp.tx_continuous(client, start, today)
    calendar = fv1.trading_calendar(client, "2025-01-01")
    entries = [e for _, e in fv5.scheduled(calendar)]
    out = []
    for r in per.itertuples():
        a, b = pd.Timestamp(r.seg_start), pd.Timestamp(r.seg_end)
        active = [e for e in entries if e <= a and e.strftime("%Y-%m-%d") in predicted][-fv5.N_TRANCHE:]
        daily = []
        for e in active:
            batch = preds[preds["as_of_date"] == e.strftime("%Y-%m-%d")]
            w = batch.set_index("ticker")["weight"]
            w = w[w != 0]
            k = int(batch["tranche"].iloc[0])
            earlier = preds[(preds["tranche"] == k) & (preds["as_of_date"] < e.strftime("%Y-%m-%d"))]
            if len(earlier):
                pb = earlier[earlier["as_of_date"] == earlier["as_of_date"].max()]
                prev_w, prev_b = pb.set_index("ticker")["weight"], float(pb["tranche_beta"].iloc[0])
                prev_w = prev_w[prev_w != 0]
            else:
                prev_w, prev_b = None, 0.0
            res = fv5.segment_return(w, float(batch["tranche_beta"].iloc[0]), batch.set_index("ticker")["fee"], rets, tx,
                                     a, b, first=(e == a), prev_weights=prev_w, prev_beta=prev_b)
            daily.append(res["daily"])
        if daily:
            out.append(pd.concat(daily, axis=1).sum(axis=1) / fv5.N_TRANCHE)
    return pd.concat(out).sort_index() if out else pd.Series(dtype=float)


def var_ratio_t(a: pd.Series, b: pd.Series, reps: int = 5000, block: int = 20) -> tuple[float, float]:
    df = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if len(df) < 40:
        return float("nan"), float("nan")
    lr = math.log(df["a"].var() / df["b"].var())
    rng = np.random.default_rng(0)
    T, n = len(df), len(df)
    nb = int(math.ceil(n / block))
    A, B = df["a"].to_numpy(), df["b"].to_numpy()
    sims = np.empty(reps)
    for r in range(reps):
        st = rng.integers(0, max(T - block, 1), nb)
        idx = np.clip((st[:, None] + np.arange(block)[None, :]).ravel()[:n], 0, T - 1)
        sims[r] = math.log(A[idx].var() / B[idx].var())
    se = float(sims.std(ddof=1))
    return lr, (-lr / se if se > 0 else float("nan"))


def build() -> str:
    from forward import run_forward_fv5 as fv5
    from forward import run_forward_fv5s as fv5s
    from forward import run_forward_fv5v as fv5v
    from forward import run_forward_fv5x as fv5x
    cfg = yaml.safe_load(cf.SCALE.read_text(encoding="utf-8"))
    dates = live_dates()
    ms = m_s(dates)
    ms_t = cf.nw_t(ms, 2) if len(ms) >= 3 else float("nan")
    mods = {"fv5s": fv5s, "fv5v": fv5v, "fv5x": fv5x}
    mv = {}
    base = None
    for k in ("fv5v", "fv5x"):
        x = daily_book(mods[k], fv5, set(dates))
        if len(x) and base is None:
            base = daily_book(fv5, fv5, set(dates)).reindex(x.index)
        base = base if base is not None else pd.Series(dtype=float)
        mv[k] = var_ratio_t(x, base) if len(x) and len(base) else (float("nan"), float("nan"))
    rows = []
    for k in cf.SPECS:
        p = ROOT / "forward" / k / "periods.csv"
        per = pd.read_csv(p) if p.exists() and p.stat().st_size > 0 else pd.DataFrame(columns=["mode", "book_net", "fv5_net"])
        sub = per[per["mode"] == "live"]
        d = float(cfg["scale"][k]) * sub["book_net"].astype(float) - sub["fv5_net"].astype(float)
        n = len(d)
        lb = float(d.mean() - 1.2816 * d.std(ddof=1) / math.sqrt(n)) if n >= 3 else float("nan")
        ni = lb > NI_MARGIN if lb == lb else None
        tests = {}
        if "M_s" in MECH.get(k, ()):
            tests["M_s"] = ms_t
        if "M_v" in MECH.get(k, ()):
            tests["M_v"] = mv[k][1]
        ps = sorted(((1 - phi(t) if t == t else 1.0, nm) for nm, t in tests.items()))
        mech_ok, still = (None if not tests or any(t != t for t in tests.values()) else True), True
        if mech_ok is not None:
            for i, (pv, nm) in enumerate(ps):
                ok = still and pv <= 0.10 / (len(ps) - i)
                still = ok
            mech_ok = still
        fail = n >= 12 and any(t == t and t < -1 for t in tests.values())
        if fail:
            flag = "機制失效（建議停止記錄，由使用者決定）"
        elif mech_ok and ni:
            flag = "機制確認、報酬非劣（提交使用者決定是否提前採用）"
        elif n == 0:
            flag = "尚無 live 段"
        else:
            flag = "觀察中"
        rows.append((k, n, tests, mech_ok, lb, ni, flag))
    f = lambda v: "—" if v != v else f"{v:.2f}"  # noqa: E731
    L = ["# fv5 家族前瞻輔助判定（機制指標與非劣性，自動產生）", "",
         "由 [forward/aux_family.py](aux_family.py) 產生；規則見程式開頭（點子卡 I053，2026-10-24 使用者決定登錄，登錄時尚無 live 機制指標）。"
         "只作輔助，不取代 [FAMILY_REPORT.md](FAMILY_REPORT.md) 的正式規則。研究記錄，非投資建議。", "",
         f"- live 預測日 {len(dates)} 個；M_s（S1 控制 SUE 後對 60 日報酬百分位的係數）已有 {len(ms)} 個完整 60 日視窗"
         + (f"，平均 {ms.mean():+.4f}、單尾 t {f(ms_t)}" if len(ms) else "") + "。",
         f"- M_v（日報酬變異數比，t = −ln ρ ÷ bootstrap 標準誤）：fv5v ρ {f(math.exp(mv['fv5v'][0])) if mv['fv5v'][0] == mv['fv5v'][0] else '—'}、t {f(mv['fv5v'][1])}；"
         f"fv5x ρ {f(math.exp(mv['fv5x'][0])) if mv['fv5x'][0] == mv['fv5x'][0] else '—'}、t {f(mv['fv5x'][1])}。", "",
         "| 規格 | live 段數 | 機制指標 t | 機制（Holm 家族 10%） | 非劣性：波動調整後每段差 90% 下界（門檻 > −0.05%） | 標記 |", "|---|---|---|---|---|---|"]
    for k, n, tests, mech_ok, lb, ni, flag in rows:
        ts = "、".join(f"{nm} {f(t)}" for nm, t in tests.items()) or "—（只報告非劣性）"
        mo = "—" if mech_ok is None else ("通過" if mech_ok else "未通過")
        L.append(f"| {k} | {n} | {ts} | {mo} | {'—' if lb != lb else f'{lb:+.3%}'}（{'—' if ni is None else ('通過' if ni else '未通過')}） | {flag} |")
    return "\n".join(L) + "\n"


def auto() -> bool:
    text = build()
    old = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    if text != old:
        REPORT.write_text(text, encoding="utf-8")
        return True
    return False


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    auto()
    print(REPORT.read_text(encoding="utf-8"))
