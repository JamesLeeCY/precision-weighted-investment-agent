"""前瞻驗證 fv5v：fv5 的各腿改用逆標準差（1/σ）權重，與 fv5 平行記錄。

研究依據：docs/smallcap_invvol_report.md（點子卡 I033 W2；1.80 / 1.87、全期 1.83、最大回撤 −5.4% vs fv5 1.45 / 1.87、全期 1.64、−6.9%；
2023 年後略低於 fv5，事前標準未通過，依使用者決定另立平行記錄）。規格與紀錄在 forward/fv5v/。

規則（凍結於 forward/fv5v/spec.yaml）：
- 名單與 fv5 相同：直接讀 fv5 同一預測日的權重（forward/fv5/predictions.csv），所以 fv5v 必須在 fv5 預測之後執行。
- 只改各腿內的權重：w ∝ 1/σ，σ = 預測日前 60 個交易日（不含當日、至少 40 日）含息日報酬標準差，缺值用該腿中位數；
  各腿總權重不變（= fv5 該腿權重總和）；單檔上限 3 倍、下限 1/3 倍等權，超過或不足部分依比例分給其他股（迭代至收斂）。
- 放空端依新權重重算需借股數（需借 = 2 億 × 權重 ÷ 預測日收盤價），再檢查借券條件 D（同 fv5：前 60 日有借券成交、
  需借 ≤ 前一日借券賣出額度、≤ 前 60 日借券成交 × 0.10、借券費 ≤ 5%／年），不通過者剔除後其餘重新正規化（只做一輪）。
- β 與借券費沿用 fv5 同一預測日的值；三份資金錯開、結算與成本同 fv5。

用法（於專案根目錄）：
    .venv/Scripts/python forward/run_forward_fv5v.py freeze
    .venv/Scripts/python forward/run_forward_fv5v.py backfill        # 補齊 fv5 已預測、fv5v 尚未預測的日期
    .venv/Scripts/python forward/run_forward_fv5v.py resolve
    .venv/Scripts/python forward/run_forward_fv5v.py report
    （每日由 forward/run_forward.py auto 在 fv5s 之後呼叫 auto()）
研究記錄，非投資建議。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import inspect
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))

import leg_probe as lp  # noqa: E402
from forward import run_forward as fv1  # noqa: E402
from forward import run_forward_fv2 as fv2  # noqa: E402
from forward import run_forward_fv5 as fv5  # noqa: E402

DIR = ROOT / "forward" / "fv5v"
SPEC_PATH = DIR / "spec.yaml"
PREDICTIONS = DIR / "predictions.csv"
SEGMENTS = DIR / "segments.csv"
PERIODS = DIR / "periods.csv"
REPORT = DIR / "REPORT.md"
PUBLISH_FILES = [str(p.relative_to(ROOT)).replace("\\", "/") for p in (SPEC_PATH, PREDICTIONS, SEGMENTS, PERIODS, REPORT)]
VOL_WIN, VOL_MIN, POWER, CAP = 60, 40, 1, 3.0
N_TRANCHE = fv5.N_TRANCHE

PRED_COLUMNS = ["spec_version", "mode", "as_of_date", "tranche", "ticker", "sector", "score", "shortable", "fee", "beta",
                "weight_fv5", "sigma", "close", "quota", "lend60", "weight", "tranche_beta", "run_utc", "git_commit"]
SEGMENT_COLUMNS = fv5.SEGMENT_COLUMNS
PERIOD_COLUMNS = ["seg_start", "seg_end", "mode", "n_active", "book_net", "fv5_net", "diff", "resolved_utc"]


# ---------------------------------------------------------------------------
# 規則（凍結）
# ---------------------------------------------------------------------------

def capped(raw: pd.Series, total: float) -> pd.Series:
    """與 analysis/fv5_invvol.capped 相同：權重和 = total，單檔介於等權的 1/CAP ~ CAP 倍。"""
    n = len(raw)
    eq = total / n
    w = raw / raw.sum() * total
    for _ in range(50):
        lo, hi = eq / CAP, eq * CAP
        cl = w.clip(lo, hi)
        free = (cl > lo) & (cl < hi)
        excess = total - cl.sum()
        if abs(excess) < 1e-12 or not free.any():
            w = cl
            break
        cl[free] += excess * cl[free] / cl[free].sum()
        w = cl
    return w


def sigma_at(rets: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    """預測日前 VOL_WIN 個交易日（不含當日）含息日報酬標準差，至少 VOL_MIN 日。"""
    r = rets[rets.index < as_of].iloc[-VOL_WIN:]
    return r.std().where(r.notna().sum() >= VOL_MIN)


def reweight(w: pd.Series, sigma: pd.Series, g: pd.DataFrame) -> pd.Series:
    """w：fv5 權重；g：ticker、close、quota、lend60、fee。回傳各腿 1/σ 權重（放空端重新檢查借券條件 D）。"""
    x_g = g.set_index("ticker")
    out = []
    for sign in (1, -1):
        x = w[w * sign > 0].abs()
        if not len(x):
            continue
        s = sigma.reindex(x.index)
        s = s.fillna(s.median())
        nw = capped(1 / s ** POWER, float(x.sum()))
        if sign < 0:
            need = fv5.K_CAPITAL * nw / x_g["close"].reindex(nw.index)
            lend60, quota, fee = (x_g[c].reindex(nw.index) for c in ("lend60", "quota", "fee"))
            ok = (lend60 > 0) & (quota >= need) & (need <= fv5.DEPTH_FRAC * lend60) & (fee <= fv5.FEE_MAX)
            nw = nw[ok.to_numpy(bool)]
            nw = nw / nw.sum() * float(x.sum()) if len(nw) else nw
        out.append(nw * sign)
    return pd.concat(out) if out else pd.Series(dtype=float)


def frozen_sources() -> dict[str, str]:
    return {"fv5v.capped": inspect.getsource(capped), "fv5v.sigma_at": inspect.getsource(sigma_at),
            "fv5v.reweight": inspect.getsource(reweight), "fv5.segment_return": inspect.getsource(fv5.segment_return),
            "fv5v.constants": repr((VOL_WIN, VOL_MIN, POWER, CAP, N_TRANCHE, fv5.K_CAPITAL, fv5.DEPTH_FRAC, fv5.FEE_MAX, fv5.FEE_WINDOW))}


def source_hashes() -> dict[str, str]:
    return {k: hashlib.sha256(v.replace("\r\n", "\n").encode("utf-8")).hexdigest() for k, v in frozen_sources().items()}


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def load_spec() -> dict:
    if not SPEC_PATH.exists():
        raise SystemExit(f"{SPEC_PATH} 不存在；先執行 freeze。")
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    changed = [k for k, h in spec["frozen_source_sha256"].items() if source_hashes().get(k) != h]
    if changed:
        raise SystemExit("fv5v 規則程式碼已與凍結時不同：" + "、".join(changed) + "。修改規則請建立新版本。")
    return spec


# ---------------------------------------------------------------------------
# 指令
# ---------------------------------------------------------------------------

def cmd_freeze(args) -> None:
    if SPEC_PATH.exists():
        raise SystemExit(f"{SPEC_PATH} 已存在；凍結只做一次。")
    DIR.mkdir(parents=True, exist_ok=True)
    spec = {
        "spec_version": "fv5v",
        "frozen_utc": fv1.now_utc(),
        "frozen_git_commit": git_commit(),
        "rules": {
            "base": "名單、β、借券費與 fv5 完全相同，直接讀 forward/fv5/predictions.csv 同一預測日的權重",
            "weights": f"各腿內 w ∝ 1/σ，σ = 預測日前 {VOL_WIN} 個交易日（不含當日、至少 {VOL_MIN} 日）含息日報酬標準差，缺值用該腿中位數；"
                       f"各腿總權重 = fv5 該腿總和；單檔介於等權的 1/{CAP:g} ~ {CAP:g} 倍",
            "short_recheck": "放空端需借股數 = 2 億 × 新權重 ÷ 預測日收盤價，重新檢查 fv5 借券條件 D，不通過者剔除後重新正規化（一輪）",
            "portfolio": "三份資金錯開、結算與成本同 fv5",
        },
        "preregistration": {
            "primary_metric": "組合每段淨報酬（同 fv5），以及同段 fv5v − fv5 的差",
            "hypothesis": "fv5v − fv5 每段差的長期平均 > 0（主要改善在 2019–2022 與回撤）",
            "backtest_expectation": {"sharpe_2019_2022": 1.80, "sharpe_2023_2026": 1.87, "sharpe_full": 1.83, "mdd": -0.054,
                                     "fv5_sharpe_full": 1.64, "fv5_mdd": -0.069, "source": "docs/smallcap_invvol_report.md"},
            "evaluation": ["只把 mode = live 的期數算入，backfill 另列",
                           "24 個 live 期數（約 2 年）時：fv5v − fv5 平均差 ≤ 0 則維持 fv5；平均差 > 0 且 fv5v 本身 t > 2 才考慮以 fv5v 取代 fv5",
                           "回測的改善集中在 2019–2022，2023 年後與 fv5 相當，兩年的差預期不顯著；差的 t 值只作描述，另報告兩者的期間波動"],
            "notes": "I033 事前標準未通過（2023 年後 Sharpe 低於 fv5 小數第三位），依使用者決定另立平行記錄；不得依前瞻結果回頭調整規則。",
        },
        "frozen_source_sha256": source_hashes(),
    }
    SPEC_PATH.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"已凍結 fv5v 規格 → {SPEC_PATH}")


def _inputs_at(g: pd.DataFrame, as_of: pd.Timestamp) -> tuple[pd.Series, pd.DataFrame]:
    """σ（fv5 有權重者）與放空端的收盤價、借券額度、借券成交量；點時取法同 fv5.member_frame。"""
    client = fv5.snapshot(dt.date.today().strftime("%Y-%m-%d"))
    calendar = fv1.trading_calendar(client, "2025-01-01")
    prior = [d for d in calendar if d < as_of]
    prev_day, window = prior[-1], prior[-fv5.FEE_WINDOW:]
    start, end = fv5.data_start(as_of), dt.date.today().strftime("%Y-%m-%d")
    held = g[g["weight"] != 0]
    adj, close = fv5.load_prices(client, list(held["ticker"]), start, end)
    sigma = sigma_at(adj.pct_change(), as_of)
    rows = []
    for t in held.loc[held["weight"] < 0, "ticker"]:
        sid = t.split(".")[0]
        sb = client.get("TaiwanDailyShortSaleBalances", sid, start, end)
        quota = np.nan
        if not sb.empty:
            sb = sb.assign(date=pd.to_datetime(sb["date"]))
            sb = sb[sb["date"] <= prev_day]
            quota = float(sb["SBLShortSalesQuota"].astype(float).iloc[-1]) if len(sb) else np.nan
        ld = client.get("TaiwanStockSecuritiesLending", sid, start, end)
        lend60 = 0.0
        if not ld.empty:
            ld = ld.assign(date=pd.to_datetime(ld["date"]))
            lend60 = float(ld.loc[ld["date"].isin(window), "volume"].astype(float).sum() * 1000)
        rows.append({"ticker": t, "close": close[t].asof(as_of) if t in close else np.nan, "quota": quota, "lend60": lend60})
    return sigma, pd.DataFrame(rows, columns=["ticker", "close", "quota", "lend60"])


def predict(as_of: str, mode: str | None = None) -> bool:
    spec = load_spec()
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    if (preds["as_of_date"] == as_of).any():
        return False
    p5 = fv1.read_csv(fv5.PREDICTIONS, fv5.PRED_COLUMNS)
    g = p5[p5["as_of_date"] == as_of].copy()
    if g.empty:
        print(f"[fv5v] {as_of}：fv5 尚未預測，略過")
        return False
    a = pd.Timestamp(as_of)
    w5 = g.set_index("ticker")["weight"].astype(float)
    sigma, bx = _inputs_at(g, a)
    gx = g[["ticker", "fee"]].merge(bx, on="ticker", how="left")
    w = reweight(w5[w5 != 0], sigma, gx)
    beta = g.set_index("ticker")["beta"]
    b = float((w * beta.reindex(w.index).fillna(1.0)).sum())
    mode = mode or ("backfill" if as_of < spec["frozen_utc"][:10] else g["mode"].iloc[0])     # 凍結日以前的預測日一律 backfill
    bxi = bx.set_index("ticker")
    out = g.assign(spec_version=spec["spec_version"], mode=mode, weight_fv5=g["weight"], sigma=g["ticker"].map(sigma),
                   close=g["ticker"].map(bxi["close"]), quota=g["ticker"].map(bxi["quota"]), lend60=g["ticker"].map(bxi["lend60"]),
                   weight=g["ticker"].map(w).fillna(0.0), tranche_beta=b, run_utc=fv1.now_utc(), git_commit=git_commit())
    DIR.mkdir(parents=True, exist_ok=True)
    fv1.append_csv(PREDICTIONS, out, PRED_COLUMNS)
    eff = lambda v: 1 / float(((v / v.sum()) ** 2).sum()) if len(v) else float("nan")  # noqa: E731
    print(f"[fv5v {out['mode'].iloc[0]}] {as_of}：多 {(w > 0).sum()}、空 {(w < 0).sum()}（fv5 空 {(w5 < 0).sum()}），"
          f"有效檔數 多 {eff(w[w > 0]):.0f}／空 {eff(-w[w < 0]):.0f}，β {b:+.2f}")
    return True


def cmd_backfill(args) -> int:
    load_spec()
    p5 = fv1.read_csv(fv5.PREDICTIONS, fv5.PRED_COLUMNS)
    return sum(predict(a) for a in sorted(p5["as_of_date"].unique()))


def cmd_resolve(args) -> int:
    """同 fv5：每段 = 相鄰兩個預測日之間，組合 = 在場各份淨報酬加總 ÷ 3；另記同段 fv5 的組合淨報酬。"""
    load_spec()
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    if preds.empty:
        return 0
    per = fv1.read_csv(PERIODS, PERIOD_COLUMNS)
    p5per = fv1.read_csv(fv5.PERIODS, fv5.PERIOD_COLUMNS).set_index("seg_start")
    today = pd.Timestamp(dt.date.today())
    client = fv5.snapshot(today.strftime("%Y-%m-%d"))
    calendar = fv1.trading_calendar(client, "2025-01-01")
    entries = [e for _, e in fv5.scheduled(calendar)]
    done = set(per["seg_start"]) if len(per) else set()
    predicted = sorted(preds["as_of_date"].unique())
    todo = [(a, b) for a, b in zip(entries[:-1], entries[1:])
            if a.strftime("%Y-%m-%d") in predicted and a.strftime("%Y-%m-%d") not in done and b <= calendar[-1]]
    if not todo:
        return 0
    start, end = fv5.data_start(pd.Timestamp(predicted[0])), today.strftime("%Y-%m-%d")
    adj, _ = fv5.load_prices(client, sorted(set(preds["ticker"])), start, end)
    rets = adj.pct_change()
    tx = lp.tx_continuous(client, start, end)
    commit = git_commit()
    n = 0
    for a, b in todo:
        a_s = a.strftime("%Y-%m-%d")
        active = [e for e in entries if e <= a and e.strftime("%Y-%m-%d") in predicted][-N_TRANCHE:]
        seg_rows, daily = [], []
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
            r = fv5.segment_return(w, float(batch["tranche_beta"].iloc[0]), batch.set_index("ticker")["fee"], rets, tx,
                                   a, b, first=(e == a), prev_weights=prev_w, prev_beta=prev_b)
            daily.append(r["daily"])
            seg_rows.append({"as_of_date": e.strftime("%Y-%m-%d"), "tranche": k, "seg_start": a_s, "seg_end": b.strftime("%Y-%m-%d"),
                             "first_segment": int(e == a), **{x: r[x] for x in ("gross", "hedge", "borrow", "cost", "net")},
                             "resolved_utc": fv1.now_utc(), "git_commit": commit})
        book = float((1 + pd.concat(daily, axis=1).sum(axis=1) / N_TRANCHE).prod() - 1) if daily else float("nan")
        f5 = float(p5per.loc[a_s, "book_net"]) if a_s in p5per.index else float("nan")
        mode = preds.loc[preds["as_of_date"] == a_s, "mode"].iloc[0]
        fv1.append_csv(SEGMENTS, pd.DataFrame(seg_rows), SEGMENT_COLUMNS)
        fv1.append_csv(PERIODS, pd.DataFrame([{"seg_start": a_s, "seg_end": b.strftime("%Y-%m-%d"), "mode": mode, "n_active": len(active),
                                                "book_net": book, "fv5_net": f5, "diff": book - f5, "resolved_utc": fv1.now_utc()}]), PERIOD_COLUMNS)
        n += 1
        print(f"fv5v {a_s} → {b:%Y-%m-%d}：組合 {book:+.2%}（fv5 {f5:+.2%}）")
    return n


def cmd_report(args) -> None:
    spec = load_spec()
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    per = fv1.read_csv(PERIODS, PERIOD_COLUMNS)
    lines = ["# 前瞻驗證報告 fv5v：fv5 各腿改用逆標準差權重（自動產生）", "",
             f"- 規格：`fv5v`（凍結於 {spec['frozen_utc']}，git `{spec['frozen_git_commit'][:8]}`）；與 fv5 平行，研究依據 "
             "[docs/smallcap_invvol_report.md](../../docs/smallcap_invvol_report.md)。研究記錄，非投資建議。",
             f"- 預測日 {preds['as_of_date'].nunique()} 個，已結算段落 {len(per)} 個",
             "- 主要指標：組合每段淨報酬（扣交易成本、借券費，台指期對沖），以及同段 fv5v − fv5 的差。", "",
             "## 累積結果", "", "| 範圍 | fv5v 每段淨報酬 | fv5 每段淨報酬 | fv5v − fv5 |", "|---|---|---|---|"]
    for label, mode in (("live（正式）", "live"), ("backfill（凍結後回填）", "backfill")):
        sub = per[per["mode"] == mode] if len(per) else per
        if len(sub):
            lines.append(f"| {label} | {fv2.summary(sub['book_net'], True)} | {fv2.summary(sub['fv5_net'], True)} | {fv2.summary(sub['diff'], True)} |")
        else:
            lines.append(f"| {label} | 尚無資料 | | |")
    lines += ["", "## 各段", "", "| 段落 | mode | 在場資金份數 | fv5v | fv5 | 差 |", "|---|---|---|---|---|---|"]
    for r in per.itertuples():
        lines.append(f"| {r.seg_start} → {r.seg_end} | {r.mode} | {int(r.n_active)} | {r.book_net:+.2%} | {r.fv5_net:+.2%} | {r.diff:+.2%} |")
    lines += ["", "## 各預測日", "", "| 預測日 | mode | 資金份 | 做多 | 放空（fv5） | 有效檔數 多／空 | 加權年化波動 多／空（fv5） |", "|---|---|---|---|---|---|---|"]
    eff = lambda v: 1 / float(((v / v.sum()) ** 2).sum()) if len(v) and v.sum() else float("nan")  # noqa: E731
    for a, bt in preds.groupby("as_of_date"):
        w, w5, s = bt["weight"], bt["weight_fv5"], bt["sigma"] * np.sqrt(252)
        vol = lambda x: float((x.abs() / x.abs().sum() * s[x.index]).sum()) if x.abs().sum() else float("nan")  # noqa: E731
        lines.append(f"| {a} | {bt['mode'].iloc[0]} | {int(bt['tranche'].iloc[0]) + 1} | {(w > 0).sum()} | {(w < 0).sum()}（{(w5 < 0).sum()}） | "
                     f"{eff(w[w > 0]):.0f}／{eff(-w[w < 0]):.0f} | {vol(w[w > 0]):.0%}／{vol(w[w < 0]):.0%}（{vol(w5[w5 > 0]):.0%}／{vol(w5[w5 < 0]):.0%}） |")
    lines += ["", "## 事先登錄的評估方式", ""] + [f"- {e}" for e in spec["preregistration"]["evaluation"]]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"fv5v 報告 → {REPORT}")


def auto() -> bool:
    """排程用（fv5s 之後）：補上 fv5 已預測的日期、結算已過的段落；有變動回傳 True。"""
    if not SPEC_PATH.exists():
        return False
    changed = cmd_backfill(None) > 0
    changed |= cmd_resolve(None) > 0
    if changed:
        cmd_report(None)
    return changed


def main(argv=None) -> None:
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    p = argparse.ArgumentParser(description="前瞻驗證 fv5v")
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("freeze", "backfill", "resolve", "report"):
        sub.add_parser(c)
    a = p.parse_args(argv)
    {"freeze": cmd_freeze, "backfill": cmd_backfill, "resolve": cmd_resolve, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
