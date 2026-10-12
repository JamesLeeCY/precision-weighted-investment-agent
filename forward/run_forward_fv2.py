"""前瞻驗證 fv2：月營收驚奇（SUE），公告期限後進場、產業中性前 1/3 + 緩衝。

與 fv1（forward/run_forward.py，財報 Agent）完全分開：規格與紀錄在 forward/fv2/，fv1 的規格、紀錄與程式碼指紋都不受影響。

規則（凍結於 forward/fv2/spec.yaml）：
- 預測日：每月「10 日或之後第一個加權指數交易日」（營收公告期限）的下一個交易日（data/revenue_signal.py）
- 訊號：SUE =（本月營收 − 去年同月 − μ）÷ σ（過去 24 個月年差）；只採用 create_time ≤ 公告期限當日的營收資料
- 股票池：當年無偏誤成員；組合：產業內 SUE 前 1/3，已持有者產業內百分位 > 50% 續留，產業權重 = 股票池產業權重
- 持有：預測日收盤到第 20 個交易日收盤（含息總報酬）
- 主要指標：產業內 IC（SUE vs 20 日報酬）；次要：組合相對等權的超額報酬（扣成本）、50% 組合 + 50% 0050 擇時 vs 0050

用法（於專案根目錄）：
    .venv/Scripts/python forward/run_forward_fv2.py freeze
    .venv/Scripts/python forward/run_forward_fv2.py schedule
    .venv/Scripts/python forward/run_forward_fv2.py predict --as-of 2026-10-13
    .venv/Scripts/python forward/run_forward_fv2.py resolve
    .venv/Scripts/python forward/run_forward_fv2.py report
    （每日自動執行由 forward/run_forward.py auto 一併呼叫 auto()）
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import inspect
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))

import sector_neutral_portfolio as snp  # noqa: E402
from data import fetch_financials as ff  # noqa: E402
from data import revenue_signal as rsig  # noqa: E402
from data.fetch_financials import get_total_return_prices  # noqa: E402
from forward import run_forward as fv1  # noqa: E402

FV2_DIR = ROOT / "forward" / "fv2"
SPEC_PATH = FV2_DIR / "spec.yaml"
PREDICTIONS = FV2_DIR / "predictions.csv"
OUTCOMES = FV2_DIR / "outcomes.csv"
PERIODS = FV2_DIR / "periods.csv"
REPORT = FV2_DIR / "REPORT.md"
PUBLISH_FILES = [str(p.relative_to(ROOT)).replace("\\", "/") for p in (SPEC_PATH, PREDICTIONS, OUTCOMES, PERIODS, REPORT)]
HORIZON = 20
Q, KEEP = 1 / 3, 0.5
COST = snp.COST_PER_SIDE
BACKFILL_START = "2026-05-01"  # 開發時最後一個事件是 2026-04-13；之後的月份開發未使用

PRED_COLUMNS = ["spec_version", "mode", "as_of_date", "deadline_date", "ticker", "sector", "revenue_month", "sue",
                "selected", "weight", "run_utc", "git_commit", "git_dirty"]
OUTCOME_COLUMNS = ["as_of_date", "ticker", "end_date", "forward_return", "resolved_utc", "git_commit"]
PERIOD_COLUMNS = ["as_of_date", "end_date", "mode", "n_selected", "turnover", "port_net", "ew_ret", "excess_net",
                  "b0050", "timed0050", "blend", "resolved_utc"]


# ---------------------------------------------------------------------------
# 規則（以下函式與 data/revenue_signal.py 一起凍結）
# ---------------------------------------------------------------------------

def entry_for_month(calendar: list[pd.Timestamp], year: int, month: int):
    days = [d for d in calendar if d.year == year and d.month == month]
    return rsig.deadline_and_entry(days)


def build_selection(g: pd.DataFrame, held: set) -> dict:
    """g：當期成員（ticker、sector、sue）；回傳 {ticker: 權重}（產業中性前 1/3 + 緩衝）。"""
    ranked = g.dropna(subset=["sue"])
    if ranked.empty:
        return {}
    return snp.sector_neutral_weights(ranked, "sue", Q, 3, +1, held, KEEP)


def period_path(weights: dict, members_: list[str], closes: dict, b_adj: pd.Series, start, end, prev_weights: dict) -> dict:
    """期間（start 收盤 → end 收盤）內的每日路徑：組合（權重固定）、等權、0050、0050 + 每日 200 日線濾網。"""
    def daily(t):
        s = closes.get(t)
        if s is None or s.empty:
            return None
        s = s[(s.index >= start) & (s.index <= end)]
        return s.pct_change().dropna() if start in s.index else None

    rets = {t: daily(t) for t in set(members_) | set(weights)}
    idx = b_adj[(b_adj.index > start) & (b_adj.index <= end)].index
    port = pd.Series(0.0, index=idx)
    for t, w in weights.items():
        if rets.get(t) is not None:
            port = port.add(w * rets[t].reindex(idx).fillna(0.0), fill_value=0.0)
    ew_list = [rets[t].reindex(idx).fillna(0.0) for t in members_ if rets.get(t) is not None]
    ew = pd.concat(ew_list, axis=1).mean(axis=1) if ew_list else pd.Series(0.0, index=idx)
    b = b_adj.pct_change().reindex(idx).fillna(0.0)
    ma = b_adj.rolling(200, min_periods=200).mean()
    on = (b_adj > ma).astype(float).shift(1).reindex(idx).fillna(0.0)  # 第 t 日用 t−1 日收盤判斷
    switches = float(on.diff().abs().fillna(0.0).sum())
    timed = (1 + on * b).prod() - 1 - switches * COST
    turnover = snp.turnover(weights, prev_weights)
    port_net = (1 + port).prod() - 1 - turnover * COST
    return {"turnover": turnover, "port_net": float(port_net), "ew_ret": float((1 + ew).prod() - 1),
            "b0050": float((1 + b).prod() - 1), "timed0050": float(timed)}


# ---------------------------------------------------------------------------
# 凍結與完整性
# ---------------------------------------------------------------------------

def frozen_sources() -> dict[str, str]:
    return {
        "data.revenue_signal": inspect.getsource(rsig),
        "sector_neutral_portfolio.sector_neutral_weights": inspect.getsource(snp.sector_neutral_weights),
        "fetch_financials.total_return_index": inspect.getsource(ff.total_return_index),
        "fv2.entry_for_month": inspect.getsource(entry_for_month),
        "fv2.build_selection": inspect.getsource(build_selection),
        "fv2.period_path": inspect.getsource(period_path),
        "fv2.constants": repr((HORIZON, Q, KEEP, COST)),
    }


def source_hashes() -> dict[str, str]:
    return {k: hashlib.sha256(v.encode("utf-8")).hexdigest() for k, v in frozen_sources().items()}


def git_state() -> tuple[str, bool]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        excludes = [f":(exclude){p}" for p in PUBLISH_FILES[1:] + fv1.PUBLISH_FILES]
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", ".", *excludes],
                                    cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip())
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return "unknown", True


def load_spec() -> dict:
    if not SPEC_PATH.exists():
        raise SystemExit(f"找不到規格 {SPEC_PATH}；請先執行 freeze")
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def verify_frozen(spec: dict) -> None:
    current = source_hashes()
    changed = [k for k, h in spec["frozen_source_sha256"].items() if current.get(k) != h]
    if changed:
        raise SystemExit("fv2 規則程式碼已與凍結時不同，拒絕預測：" + "、".join(changed) + "。修改規則請建立新版本（fv3）。")


# ---------------------------------------------------------------------------
# 指令
# ---------------------------------------------------------------------------

def cmd_freeze(args) -> None:
    if SPEC_PATH.exists():
        raise SystemExit(f"{SPEC_PATH} 已存在；凍結只做一次。")
    FV2_DIR.mkdir(parents=True, exist_ok=True)
    commit, dirty = git_state()
    spec = {
        "spec_version": "fv2",
        "frozen_utc": fv1.now_utc(),
        "frozen_git_commit": commit,
        "frozen_git_dirty": dirty,
        "rules": {
            "signal": "月營收驚奇 SUE =（本月營收 − 去年同月 − μ）÷ σ；μ、σ 為過去 24 個月營收年差的平均與標準差（至少 12 個月）",
            "data_cutoff": "只採用 create_time ≤ 公告期限交易日的營收資料（create_time 缺值的歷史資料照常使用）",
            "schedule": "每月「10 日或之後第一個加權指數交易日」（公告期限）的下一個交易日",
            "universe": "config/universe_pit_membership.csv 當年成員",
            "portfolio": "產業內 SUE 前 1/3；已持有者產業內百分位 > 50% 續留；產業權重 = 股票池產業權重；無 SUE 者不入選",
            "horizon_trading_days": HORIZON,
            "return": "預測日收盤到第 20 個交易日收盤的含息總報酬",
            "cost_per_side": COST,
            "backfill_start": BACKFILL_START,
        },
        "preregistration": {
            "primary_metric": "每個預測日的產業內 IC（各產業內 Spearman(SUE, 20 日含息報酬)，依股票數加權；產業內 ≥ 3 檔才計入）",
            "hypothesis": "產業內 IC 的長期平均 > 0",
            "backtest_expectation": {"mean_ic": 0.0442, "sd_ic": 0.1191, "t": 3.48, "n": 88,
                                     "source": "docs/revenue_surprise_report.md（2019-01 ~ 2026-04，每月一期）"},
            "evaluation": [
                "只把 mode = live 的期數算入正式檢定，backfill 另列",
                "12 個 live 期數時檢查：平均 IC < 0 視為訊號失效的警訊",
                "30 個 live 期數（約 2.5 年）時正式檢定：t > 2 才算確認（依回測平均與標準差，約需 29 期）",
            ],
            "secondary_metrics": [
                "組合（扣成本）相對等權持有全部成員的每期超額報酬；回測平均 +0.44% / 期（標準差 1.43%）",
                "50% 組合 + 50%「0050 + 每日 200 日線濾網」相對 0050 買進持有的累積報酬與 Sharpe（回測 Sharpe 0.88 / 2.64 vs 0.75 / 2.40）",
            ],
            "notes": "SUE 是看過多個訊號後找到的（docs/revenue_surprise_report.md），前瞻結果才是乾淨的驗證；不得依前瞻結果回頭調整規則。",
        },
        "frozen_source_sha256": source_hashes(),
    }
    SPEC_PATH.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"已凍結 fv2 規格 → {SPEC_PATH}（git {commit[:8]}{'，工作區有未 commit 的修改' if dirty else ''}）")


def scheduled(calendar: list[pd.Timestamp], start: str = BACKFILL_START) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    out = []
    months = sorted({(d.year, d.month) for d in calendar if d >= pd.Timestamp(start)})
    for y, m in months:
        de = entry_for_month(calendar, y, m)
        if de is not None:
            out.append(de)
    return out


def cmd_predict(args) -> None:
    spec = load_spec()
    verify_frozen(spec)
    as_of = pd.Timestamp(args.as_of)
    today = pd.Timestamp(dt.date.today())
    if as_of > today:
        raise SystemExit("不能預測未來日期")
    mode = args.mode or ("live" if as_of >= today - pd.Timedelta(days=3) else "backfill")
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    if (preds["as_of_date"] == as_of.strftime("%Y-%m-%d")).any():
        raise SystemExit(f"{as_of:%Y-%m-%d} 已經預測過（紀錄只能新增）")
    client = fv1.snapshot_client(today.strftime("%Y-%m-%d"))
    calendar = fv1.trading_calendar(client, (as_of - pd.Timedelta(days=40)).strftime("%Y-%m-%d"))
    de = entry_for_month(calendar, as_of.year, as_of.month)
    if de is None or de[1] != as_of:
        raise SystemExit(f"{as_of:%Y-%m-%d} 不是 fv2 的預測日（應為 {de[1]:%Y-%m-%d}）" if de else f"{as_of:%Y-%m} 交易日不足")
    deadline = de[0]
    mem = fv1.members(as_of.year)
    avail = as_of.to_period("M").to_timestamp()
    rows = []
    for m in mem.itertuples():
        rev = client.get("TaiwanStockMonthRevenue", m.stock_id, "2017-01-01")
        sue = np.nan
        if not rev.empty:
            s = rsig.revenue_surprise(rev, cutoff=deadline).set_index("avail_month")
            if avail in s.index:
                sue = s.loc[avail, "sue"]
        rows.append({"ticker": m.ticker, "sector": m.sector, "sue": sue})
    g = pd.DataFrame(rows)
    prev = preds[preds["as_of_date"] == preds["as_of_date"].max()] if len(preds) else preds
    held = set(prev.loc[prev["selected"] == 1, "ticker"]) if len(prev) else set()
    weights = build_selection(g, held)
    commit, dirty = git_state()
    g = g.assign(spec_version=spec["spec_version"], mode=mode, as_of_date=as_of.strftime("%Y-%m-%d"),
                 deadline_date=deadline.strftime("%Y-%m-%d"), revenue_month=(avail - pd.offsets.MonthBegin(1)).strftime("%Y-%m"),
                 selected=g["ticker"].map(lambda t: int(t in weights)), weight=g["ticker"].map(lambda t: weights.get(t, 0.0)),
                 run_utc=fv1.now_utc(), git_commit=commit, git_dirty=dirty)
    FV2_DIR.mkdir(parents=True, exist_ok=True)
    fv1.append_csv(PREDICTIONS, g, PRED_COLUMNS)
    print(f"[fv2 {mode}] {as_of:%Y-%m-%d}：{len(g)} 檔（SUE 有值 {g['sue'].notna().sum()}，入選 {len(weights)}）已寫入 {PREDICTIONS.name}")


def cmd_resolve(args) -> int:
    load_spec()
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    outcomes = fv1.read_csv(OUTCOMES, OUTCOME_COLUMNS)
    pending = sorted(set(preds["as_of_date"]) - set(outcomes["as_of_date"]))
    if not pending:
        print("fv2：沒有待結算的預測")
        return 0
    today = dt.date.today().strftime("%Y-%m-%d")
    client = fv1.snapshot_client(today)
    calendar = fv1.trading_calendar(client, min(pending))
    commit, _ = git_state()
    fetch_start = (pd.Timestamp(min(pending)) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    cache: dict[str, pd.Series] = {}

    def adj(t: str, start: str = fetch_start) -> pd.Series:
        key = f"{t}|{start}"
        if key not in cache:
            px = get_total_return_prices(client, t, start, today)
            cache[key] = px.set_index("date")["adj_close"].astype(float) if not px.empty else pd.Series(dtype=float)
        return cache[key]

    b_adj = adj("0050.TW", (pd.Timestamp(min(pending)) - pd.Timedelta(days=420)).strftime("%Y-%m-%d"))
    resolved = 0
    for as_of in pending:
        start = pd.Timestamp(as_of)
        later = [d for d in calendar if d > start]
        if len(later) < HORIZON or later[HORIZON - 1] >= pd.Timestamp(today):
            print(f"fv2 {as_of}：尚未滿 {HORIZON} 個交易日，略過")
            continue
        end = later[HORIZON - 1]
        batch = preds[preds["as_of_date"] == as_of]
        closes = {t: adj(t) for t in batch["ticker"]}
        rows = []
        for t in batch["ticker"]:
            s = closes[t]
            ret = float(s.asof(end) / s.loc[start] - 1.0) if start in s.index else float("nan")
            rows.append({"as_of_date": as_of, "ticker": t, "end_date": end.strftime("%Y-%m-%d"),
                         "forward_return": ret, "resolved_utc": fv1.now_utc(), "git_commit": commit})
        fv1.append_csv(OUTCOMES, pd.DataFrame(rows), OUTCOME_COLUMNS)
        weights = dict(zip(batch.loc[batch["selected"] == 1, "ticker"], batch.loc[batch["selected"] == 1, "weight"]))
        earlier = preds[preds["as_of_date"] < as_of]
        prev_batch = earlier[earlier["as_of_date"] == earlier["as_of_date"].max()] if len(earlier) else earlier
        prev_w = dict(zip(prev_batch.loc[prev_batch["selected"] == 1, "ticker"], prev_batch.loc[prev_batch["selected"] == 1, "weight"])) if len(prev_batch) else {}
        path = period_path(weights, list(batch["ticker"]), closes, b_adj, start, end, prev_w)
        prow = {"as_of_date": as_of, "end_date": end.strftime("%Y-%m-%d"), "mode": batch["mode"].iloc[0],
                "n_selected": len(weights), **path, "excess_net": path["port_net"] - path["ew_ret"],
                "blend": 0.5 * path["port_net"] + 0.5 * path["timed0050"], "resolved_utc": fv1.now_utc()}
        fv1.append_csv(PERIODS, pd.DataFrame([prow]), PERIOD_COLUMNS)
        resolved += 1
        print(f"fv2 {as_of} → {end:%Y-%m-%d}：結算 {len(rows)} 檔")
    return resolved


def ic_of(g: pd.DataFrame) -> float:
    vals, w = [], []
    for _, s in g.dropna(subset=["sue", "forward_return"]).groupby("sector"):
        if len(s) >= 3 and s["sue"].nunique() > 1:
            vals.append(s["sue"].rank().corr(s["forward_return"].rank()))
            w.append(len(s))
    return float(np.average(vals, weights=w)) if vals else float("nan")


def summary(x: pd.Series, pct=False) -> str:
    x = x.dropna()
    if len(x) == 0:
        return "尚無資料"
    f = (lambda v: f"{v * 100:+.2f}%") if pct else (lambda v: f"{v:+.3f}")
    if len(x) == 1:
        return f"{f(x.mean())}（1 期）"
    se = x.std(ddof=1) / math.sqrt(len(x))
    return f"{f(x.mean())}（{len(x)} 期，t {x.mean() / se:+.2f}）"


def cmd_report(args) -> None:
    spec = load_spec()
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    outcomes = fv1.read_csv(OUTCOMES, OUTCOME_COLUMNS)
    periods = fv1.read_csv(PERIODS, PERIOD_COLUMNS)
    df = preds.merge(outcomes, on=["as_of_date", "ticker"], how="inner")
    ics = df.groupby("as_of_date").apply(ic_of).rename("ic")
    per = periods.set_index("as_of_date").join(ics, how="left") if len(periods) else pd.DataFrame(columns=["ic", "mode"])
    exp = spec["preregistration"]["backtest_expectation"]
    lines = ["# 前瞻驗證報告 fv2：月營收驚奇（自動產生）", "",
             f"- 規格：`fv2`（凍結於 {spec['frozen_utc']}，git `{spec['frozen_git_commit'][:8]}`）；產生時間 {fv1.now_utc()}",
             f"- 預測日 {preds['as_of_date'].nunique()} 個，已結算 {len(per)} 個",
             f"- 主要指標：產業內 IC（SUE 排名與之後 20 個交易日報酬排名的相關係數，−1～1，0 = 無預測力）；回測預期平均 {exp['mean_ic']:+.3f}、每期標準差 {exp['sd_ic']:.3f}",
             "", "## 累積結果", "",
             "| 範圍 | 產業內 IC | 組合 − 等權（每期、扣成本） | 50% 組合 + 50% 0050 擇時（每期） | 0050（每期） |", "|---|---|---|---|---|"]
    for label, mode in (("live（正式）", "live"), ("backfill（凍結後回填）", "backfill")):
        sub = per[per["mode"] == mode] if len(per) else per
        if len(sub):
            lines.append(f"| {label} | {summary(sub['ic'])} | {summary(sub['excess_net'], True)} | {summary(sub['blend'], True)} | {summary(sub['b0050'], True)} |")
        else:
            lines.append(f"| {label} | 尚無資料 | | | |")
    lines += ["", "## 各期", "", "| 預測日 | mode | 結算日 | 入選檔數 | 產業內 IC | 組合（扣成本） | 等權 | 組合 − 等權 | 0050 | 0050 擇時 | 50/50 |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for a, r in per.iterrows():
        lines.append(f"| {a} | {r['mode']} | {r['end_date']} | {int(r['n_selected'])} | {r['ic']:+.3f} | {r['port_net'] * 100:+.2f}% | "
                     f"{r['ew_ret'] * 100:+.2f}% | {r['excess_net'] * 100:+.2f}% | {r['b0050'] * 100:+.2f}% | {r['timed0050'] * 100:+.2f}% | {r['blend'] * 100:+.2f}% |")
    pending = sorted(set(preds["as_of_date"]) - set(per.index))
    if pending:
        lines += ["", f"待結算：{', '.join(pending)}"]
    lines += ["", "## 事先登錄的評估方式", ""] + [f"- {e}" for e in spec["preregistration"]["evaluation"]]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"fv2 報告 → {REPORT}")


def cmd_schedule(args) -> None:
    client = fv1.snapshot_client(dt.date.today().strftime("%Y-%m-%d"))
    calendar = fv1.trading_calendar(client, BACKFILL_START)
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    done = set(preds["as_of_date"])
    for deadline, entry in scheduled(calendar):
        print(f"{entry:%Y-%m-%d}（期限 {deadline:%Y-%m-%d}）{'已預測' if entry.strftime('%Y-%m-%d') in done else '未預測'}")


def auto() -> bool:
    """排程用（由 forward/run_forward.py auto 呼叫）：預測當月（若已過預測日）、結算到期者；有變動回傳 True。"""
    today = pd.Timestamp(dt.date.today())
    client = fv1.snapshot_client(today.strftime("%Y-%m-%d"))
    calendar = fv1.trading_calendar(client, (today - pd.Timedelta(days=40)).strftime("%Y-%m-%d"))
    changed = False
    de = entry_for_month(calendar + ([today] if today not in calendar and today.weekday() < 5 else []), today.year, today.month)
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    if de is not None and de[1] <= today and de[1] in calendar:
        if de[1].strftime("%Y-%m-%d") not in set(preds["as_of_date"]):
            cmd_predict(argparse.Namespace(as_of=de[1].strftime("%Y-%m-%d"), mode=None))
            changed = True
    changed |= cmd_resolve(argparse.Namespace()) > 0
    if changed:
        cmd_report(argparse.Namespace())
    return changed


def main(argv=None) -> None:
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="前瞻驗證 fv2（月營收驚奇）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze")
    sub.add_parser("schedule")
    p = sub.add_parser("predict")
    p.add_argument("--as-of", required=True)
    p.add_argument("--mode", choices=["live", "backfill"], default=None)
    sub.add_parser("resolve")
    sub.add_parser("report")
    args = ap.parse_args(argv)
    {"freeze": cmd_freeze, "schedule": cmd_schedule, "predict": cmd_predict, "resolve": cmd_resolve,
     "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    main()
