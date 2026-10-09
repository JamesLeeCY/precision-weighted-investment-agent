"""前瞻驗證（forward validation）：凍結規則、事先寫下預測、到期後才結算。

規則（規格 fv1，forward/spec_fv1.yaml）：
- 只用財報 Agent、連續輸出模式（無選股偏誤股票池上唯一有產業內排序能力的 Agent，
  docs/pit_universe_report.md、docs/ic_weighting_report.md）
- 股票池：當年的無偏誤成員（config/universe_pit_membership.csv；每年 1 月以
  build-universe 依前 60 個交易日平均成交金額取前 100 檔）
- 每月第一個交易日（as_of）預測；持有期 = as_of 收盤到之後第 20 個交易日收盤，含息總報酬
- 主要指標：產業內 IC（事先登錄於 spec 的 preregistration）

完整性：
- 凍結：spec 記錄關鍵程式碼（財報 Agent、評分、機率映射、財報公告遞延）的 SHA-256；
  程式碼被改動時拒絕預測（避免悄悄改規則後繼續累積「前瞻」紀錄）
- 只能新增：predictions.csv / outcomes.csv 只會附加；同一個 as_of 不能預測兩次
- 每筆預測記錄執行時間（UTC）、git commit、規格版本、mode（backfill / live）
- 資料快照：前瞻需要最新資料，而 data_cache/ 的快取不會過期；每次執行改用
  data_cache/forward/<抓取日期>/ 的新快取（同時保留作為稽核依據，不納入版控）

用法（於專案根目錄）：
    .venv/Scripts/python forward/run_forward.py freeze           # 只在建立規格時執行一次
    .venv/Scripts/python forward/run_forward.py schedule         # 列出預測日與各日狀態
    .venv/Scripts/python forward/run_forward.py predict --as-of 2026-11-02
    .venv/Scripts/python forward/run_forward.py resolve          # 結算所有已到期的預測
    .venv/Scripts/python forward/run_forward.py report           # 產生 forward/REPORT.md
    .venv/Scripts/python forward/run_forward.py build-universe --year 2027   # 每年 1 月
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import inspect
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents import base as agents_base  # noqa: E402
from agents import fundamentals_agent as fa  # noqa: E402
from agents.fundamentals_agent import FundamentalsAgent  # noqa: E402
from arbitrator.ic_weighting import within_sector_ic  # noqa: E402
from backtest.metrics import signal_to_probability  # noqa: E402
from data import fetch_financials as ff  # noqa: E402
from data.fetch_financials import FinMindClient, FinMindFundamentalsProvider, get_total_return_prices  # noqa: E402

FORWARD_DIR = ROOT / "forward"
SPEC_PATH = FORWARD_DIR / "spec_fv1.yaml"
PREDICTIONS = FORWARD_DIR / "predictions.csv"
OUTCOMES = FORWARD_DIR / "outcomes.csv"
REPORT = FORWARD_DIR / "REPORT.md"
SNAPSHOT_ROOT = ROOT / "data_cache" / "forward"
MEMBERSHIP = ROOT / "config" / "universe_pit_membership.csv"
CALENDAR_INDEX = "TAIEX"

PRED_COLUMNS = [
    "spec_version", "mode", "as_of_date", "ticker", "sector", "p", "rule_score", "evidence",
    "signal", "confidence", "run_utc", "git_commit", "git_dirty",
]
OUTCOME_COLUMNS = ["as_of_date", "ticker", "end_date", "forward_return", "resolved_utc", "git_commit"]


# ---------------------------------------------------------------------------
# 凍結
# ---------------------------------------------------------------------------

def frozen_sources() -> dict[str, str]:
    """決定預測結果的程式碼片段（改了就等於改規則）。"""
    return {
        "FundamentalsAgent": inspect.getsource(FundamentalsAgent),
        "fundamentals_agent.COMPONENT_KEYS": repr(fa.COMPONENT_KEYS),
        "fundamentals_agent._slope": inspect.getsource(fa._slope),
        "base.score_components": inspect.getsource(agents_base.score_components),
        "base.continuous_judgement": inspect.getsource(agents_base.continuous_judgement),
        "base.CONTINUOUS_SCALE": repr(agents_base.CONTINUOUS_SCALE),
        "FinMindFundamentalsProvider": inspect.getsource(FinMindFundamentalsProvider),
        "fetch_financials.total_return_index": inspect.getsource(ff.total_return_index),
    }


def source_hashes() -> dict[str, str]:
    return {k: hashlib.sha256(v.encode("utf-8")).hexdigest() for k, v in frozen_sources().items()}


def git_state() -> tuple[str, bool]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip())
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return "unknown", True


def load_spec(path: Path | None = None) -> dict:
    path = path or SPEC_PATH
    if not path.exists():
        raise SystemExit(f"找不到規格 {path}；請先執行 freeze")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def verify_frozen(spec: dict) -> None:
    """程式碼與凍結時不一致就中止。"""
    current = source_hashes()
    changed = [k for k, h in spec["frozen_source_sha256"].items() if current.get(k) != h]
    if changed:
        raise SystemExit(
            "規則程式碼已與凍結時不同，拒絕預測：" + "、".join(changed)
            + "。若是刻意修改規則，應建立新版本規格（例如 fv2），而不是沿用 fv1 的紀錄。"
        )


# ---------------------------------------------------------------------------
# 資料
# ---------------------------------------------------------------------------

def snapshot_client(fetch_date: str) -> FinMindClient:
    """以抓取日期為單位的新快取：前瞻需要最新資料（一般快取不會過期）。"""
    return FinMindClient(cache_dir=SNAPSHOT_ROOT / fetch_date)


def trading_calendar(client: FinMindClient, start: str) -> list[pd.Timestamp]:
    df = client.get("TaiwanStockPrice", CALENDAR_INDEX, start)
    if df.empty:
        raise SystemExit("取不到加權指數資料，無法建立交易日曆")
    df = df[df["close"].astype(float) > 0]
    return sorted(pd.to_datetime(df["date"]).unique())


def scheduled_dates(calendar: list[pd.Timestamp], start: str) -> list[pd.Timestamp]:
    """每月第一個交易日（>= start）。"""
    cal = pd.Series(calendar)
    cal = cal[cal >= pd.Timestamp(start)]
    return list(cal.groupby(cal.dt.to_period("M")).min())


def members(year: int) -> pd.DataFrame:
    m = pd.read_csv(MEMBERSHIP, dtype={"stock_id": str})
    m = m[m["year"] == year]
    if m.empty:
        raise SystemExit(f"{year} 年沒有股票池成員；請先執行 build-universe --year {year}")
    return m.assign(ticker=m["stock_id"] + ".TW")


def read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path, dtype={"ticker": str, "as_of_date": str})
    return pd.DataFrame(columns=columns)


def append_csv(path: Path, rows: pd.DataFrame, columns: list[str]) -> None:
    rows = rows[columns]
    rows.to_csv(path, mode="a", header=not (path.exists() and path.stat().st_size > 0), index=False, encoding="utf-8")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# 指令
# ---------------------------------------------------------------------------

def cmd_freeze(args) -> None:
    if SPEC_PATH.exists():
        raise SystemExit(f"{SPEC_PATH} 已存在；凍結只做一次。修改規則請建立新版本。")
    commit, dirty = git_state()
    spec = {
        "spec_version": "fv1",
        "frozen_utc": now_utc(),
        "frozen_git_commit": commit,
        "frozen_git_dirty": dirty,
        "rules": {
            "agent": "fundamentals_agent",
            "output_mode": "continuous",
            "fundamentals_history_start": "2017-01-01",
            "universe": "config/universe_pit_membership.csv 當年成員（每年 1 月 build-universe：前 60 個交易日平均成交金額前 100 檔）",
            "schedule": "每月第一個交易日（加權指數交易日）",
            "horizon_trading_days": 20,
            "return": "as_of 收盤到第 20 個交易日收盤的含息總報酬；期間下市以最後收盤價計",
            "data_cutoff": "財報 Agent 只用公告遞延後的資料（月營收 40 天、季報 75 天）",
        },
        "preregistration": {
            "primary_metric": "每個預測日的產業內 IC（各產業內 Spearman(p, 20 日含息報酬)，以股票數加權平均；產業內 >= 3 檔才計入）",
            "hypothesis": "產業內 IC 的長期平均 > 0",
            "backtest_expectation": {"mean_ic": 0.029, "sd_ic": 0.122, "source": "reports/finmind_pit（2019–2026，85 期）"},
            "evaluation": [
                "每月更新累積平均、標準誤、t 值；只把 mode = live 的期數算入正式檢定，backfill 另列",
                "24 個 live 期數（約 2 年）時檢查：平均 IC < 0 視為訊號失效的警訊（在回測預期下發生機率約 12%）",
                "73 個 live 期數（約 6 年）時正式檢定：t > 2 才算確認",
            ],
            "secondary_metrics": ["持有 p > 0.5 股票（等權）相對等權持有全部成員的每期超額報酬（未扣成本）"],
            "notes": "訊號弱（平均 IC 約為標準差的 1/4），前兩年的結果在統計上都不具決定性；不得依前瞻結果回頭調整規則，修改規則須建立新規格版本。",
        },
        "frozen_source_sha256": source_hashes(),
    }
    SPEC_PATH.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"已凍結規格 → {SPEC_PATH}（git {commit[:8]}{'，工作區有未 commit 的修改' if dirty else ''}）")


def cmd_predict(args) -> None:
    spec = load_spec()
    verify_frozen(spec)
    as_of = pd.Timestamp(args.as_of)
    today = pd.Timestamp(dt.date.today())
    if as_of > today:
        raise SystemExit("不能預測未來日期")
    mode = args.mode or ("live" if as_of >= today - pd.Timedelta(days=3) else "backfill")
    preds = read_csv(PREDICTIONS, PRED_COLUMNS)
    if (preds["as_of_date"] == as_of.strftime("%Y-%m-%d")).any():
        raise SystemExit(f"{as_of:%Y-%m-%d} 已經預測過（紀錄只能新增，不能覆寫）")
    client = snapshot_client(today.strftime("%Y-%m-%d"))
    calendar = trading_calendar(client, (as_of - pd.Timedelta(days=60)).strftime("%Y-%m-%d"))
    if as_of not in calendar and as_of < today:
        raise SystemExit(f"{as_of:%Y-%m-%d} 不是交易日")
    agent = FundamentalsAgent(
        FinMindFundamentalsProvider(client, history_start=spec["rules"]["fundamentals_history_start"]),
        output_mode=spec["rules"]["output_mode"],
    )
    commit, dirty = git_state()
    rows = []
    for m in members(as_of.year).itertuples():
        out = agent.analyze(m.ticker, as_of.strftime("%Y-%m-%d"))
        rows.append({
            "spec_version": spec["spec_version"], "mode": mode, "as_of_date": as_of.strftime("%Y-%m-%d"),
            "ticker": m.ticker, "sector": m.sector, "p": signal_to_probability(out.signal, out.confidence),
            "rule_score": out.raw_features.get("rule_score"), "evidence": out.raw_features.get("evidence"),
            "signal": out.signal, "confidence": out.confidence, "run_utc": now_utc(),
            "git_commit": commit, "git_dirty": dirty,
        })
    append_csv(PREDICTIONS, pd.DataFrame(rows), PRED_COLUMNS)
    print(f"[{mode}] {as_of:%Y-%m-%d}：{len(rows)} 檔預測已寫入 {PREDICTIONS.name}")


def cmd_resolve(args) -> None:
    spec = load_spec()
    preds = read_csv(PREDICTIONS, PRED_COLUMNS)
    outcomes = read_csv(OUTCOMES, OUTCOME_COLUMNS)
    pending = sorted(set(preds["as_of_date"]) - set(outcomes["as_of_date"]))
    if not pending:
        print("沒有待結算的預測")
        return
    today = dt.date.today().strftime("%Y-%m-%d")
    client = snapshot_client(today)
    calendar = trading_calendar(client, min(pending))
    horizon = int(spec["rules"]["horizon_trading_days"])
    commit, _ = git_state()
    # 每檔股票在這次結算中只抓一次（同一個起點、到今天），所有待結算日共用
    fetch_start = (pd.Timestamp(min(pending)) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    price_cache: dict[str, pd.Series] = {}

    def adj_closes(ticker: str) -> pd.Series:
        if ticker not in price_cache:
            px = get_total_return_prices(client, ticker, fetch_start, today)
            price_cache[ticker] = (
                px.set_index("date")["adj_close"].astype(float) if not px.empty else pd.Series(dtype=float)
            )
        return price_cache[ticker]

    for as_of in pending:
        start = pd.Timestamp(as_of)
        later = [d for d in calendar if d > start]
        if len(later) < horizon or later[horizon - 1] >= pd.Timestamp(today):
            print(f"{as_of}：尚未滿 {horizon} 個交易日（或期末收盤尚未產生），略過")
            continue
        end = later[horizon - 1]
        batch = preds[preds["as_of_date"] == as_of]
        rows = []
        for ticker in batch["ticker"]:
            s = adj_closes(ticker)
            ret = float("nan")
            if start in s.index:  # as_of 當天有成交才算進場；期間下市以最後收盤價計
                ret = float(s.asof(end) / s.loc[start] - 1.0)
            rows.append({"as_of_date": as_of, "ticker": ticker, "end_date": end.strftime("%Y-%m-%d"),
                         "forward_return": ret, "resolved_utc": now_utc(), "git_commit": commit})
        append_csv(OUTCOMES, pd.DataFrame(rows), OUTCOME_COLUMNS)
        print(f"{as_of} → {end:%Y-%m-%d}：結算 {len(rows)} 檔")


def period_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """每個預測日：產業內 IC、持有 p > 0.5 相對等權的超額報酬。"""
    rows = []
    for as_of, g in df.dropna(subset=["forward_return"]).groupby("as_of_date"):
        g = g.rename(columns={"forward_return": "ret"})
        held = g[g["p"] > 0.5]
        rows.append({
            "as_of_date": as_of, "mode": g["mode"].iloc[0], "n": len(g),
            "ic_within": within_sector_ic(g, "p"),
            "excess_long": (held["ret"].mean() - g["ret"].mean()) if len(held) else -g["ret"].mean(),
            "n_long": len(held),
        })
    return pd.DataFrame(rows)


def running_summary(values: pd.Series) -> str:
    v = values.dropna()
    if len(v) == 0:
        return "尚無資料"
    if len(v) == 1:
        return f"{v.mean():+.3f}（1 期）"
    se = v.std(ddof=1) / math.sqrt(len(v))
    return f"{v.mean():+.3f}（{len(v)} 期，標準誤 {se:.3f}，t {v.mean() / se:+.2f}）"


def cmd_report(args) -> None:
    spec = load_spec()
    preds = read_csv(PREDICTIONS, PRED_COLUMNS)
    outcomes = read_csv(OUTCOMES, OUTCOME_COLUMNS)
    df = preds.merge(outcomes, on=["as_of_date", "ticker"], how="left")
    per = period_metrics(df)
    exp = spec["preregistration"]["backtest_expectation"]
    lines = [
        "# 前瞻驗證報告（自動產生）",
        "",
        f"- 規格：`{spec['spec_version']}`（凍結於 {spec['frozen_utc']}，git `{spec['frozen_git_commit'][:8]}`）",
        f"- 產生時間：{now_utc()}",
        f"- 預測日：{preds['as_of_date'].nunique()} 個（已結算 {per['as_of_date'].nunique() if len(per) else 0} 個）",
        f"- 回測預期：產業內 IC 平均 {exp['mean_ic']:+.3f}、每期標準差 {exp['sd_ic']:.3f}",
        "",
        "## 累積結果",
        "",
        "| 範圍 | 產業內 IC | 持有 p > 0.5 相對等權（每期，未扣成本） |",
        "|---|---|---|",
    ]
    for label, sub in (("live（正式）", per[per["mode"] == "live"] if len(per) else per),
                       ("backfill（開發未用過的期間，回填）", per[per["mode"] == "backfill"] if len(per) else per)):
        lines.append(f"| {label} | {running_summary(sub['ic_within']) if len(sub) else '尚無資料'} | "
                     f"{running_summary(sub['excess_long']) if len(sub) else '尚無資料'} |")
    lines += ["", "## 各期", "", "| 預測日 | mode | 檔數 | 產業內 IC | 超額（持有 p>0.5） | 看多檔數 |", "|---|---|---|---|---|---|"]
    for r in per.itertuples():
        lines.append(f"| {r.as_of_date} | {r.mode} | {r.n} | {r.ic_within:+.3f} | {r.excess_long * 100:+.2f}% | {r.n_long} |")
    pending = sorted(set(preds["as_of_date"]) - set(per["as_of_date"] if len(per) else []))
    if pending:
        lines += ["", f"待結算：{', '.join(pending)}"]
    lines += ["", "## 事先登錄的評估方式", ""] + [f"- {e}" for e in spec["preregistration"]["evaluation"]]
    lines += [f"- {spec['preregistration']['notes']}"]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[8:12]))
    print(f"→ {REPORT}")


def cmd_schedule(args) -> None:
    client = snapshot_client(dt.date.today().strftime("%Y-%m-%d"))
    dates = scheduled_dates(trading_calendar(client, args.start), args.start)
    preds = read_csv(PREDICTIONS, PRED_COLUMNS)
    outcomes = read_csv(OUTCOMES, OUTCOME_COLUMNS)
    for d in dates:
        s = d.strftime("%Y-%m-%d")
        state = "已結算" if s in set(outcomes["as_of_date"]) else "已預測、待結算" if s in set(preds["as_of_date"]) else "未預測"
        print(f"{s}  {state}")
    nxt = (pd.Timestamp(dates[-1]) + pd.offsets.MonthBegin(1)) if dates else None
    if nxt is not None:
        print(f"下一個預測日：{nxt:%Y-%m} 的第一個交易日")


def cmd_build_universe(args) -> None:
    from data.universe import build_membership

    m = pd.read_csv(MEMBERSHIP, dtype={"stock_id": str})
    if (m["year"] == args.year).any():
        raise SystemExit(f"{args.year} 年成員已存在")
    today = dt.date.today()
    if today < dt.date(args.year, 1, 5):
        raise SystemExit(f"{args.year} 年的成員要等到該年第一個交易日之後才能建立")
    new = build_membership(snapshot_client(today.strftime("%Y-%m-%d")), range(args.year, args.year + 1), top_n=100)
    pd.concat([m, new], ignore_index=True).to_csv(MEMBERSHIP, index=False, encoding="utf-8")
    print(f"{args.year} 年：{len(new)} 檔已加入 {MEMBERSHIP.name}")


def main(argv=None) -> None:
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="前瞻驗證（規格 fv1）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze")
    p = sub.add_parser("predict")
    p.add_argument("--as-of", required=True)
    p.add_argument("--mode", choices=["live", "backfill"], default=None,
                   help="預設：as_of 在 3 天內為 live，更早為 backfill")
    sub.add_parser("resolve")
    sub.add_parser("report")
    s = sub.add_parser("schedule")
    s.add_argument("--start", default="2026-06-01")
    b = sub.add_parser("build-universe")
    b.add_argument("--year", type=int, required=True)
    args = parser.parse_args(argv)
    {"freeze": cmd_freeze, "predict": cmd_predict, "resolve": cmd_resolve, "report": cmd_report,
     "schedule": cmd_schedule, "build-universe": cmd_build_universe}[args.cmd](args)


if __name__ == "__main__":
    main()
