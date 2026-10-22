"""前瞻驗證 fv5x：fv5e、fv5s、fv5v 三項修改同時使用的合併規格，與 fv5 平行記錄。

研究依據：docs/fv5_family_report.md（點子卡 I051；回測 1.91 / 2.22、全期 2.05 vs fv5 1.45 / 1.87、全期 1.64；
三項邊際貢獻 E +0.04、S +0.13、V +0.24；三項修改都是看過結果後定的，回測含選擇偏誤）。規格與紀錄在 forward/fv5x/。

規則（凍結於 forward/fv5x/spec.yaml；各步驟直接呼叫 fv5e、fv5s、fv5v 的規則函式，三者的原始碼雜湊一併凍結）：
- 讀 fv5 同一預測日的成員資料（forward/fv5/predictions.csv），所以必須在 fv5 之後執行。
- E：金融股若有已知 ESUE，依 fv5e.override_scores 取代分數。
- S：分數 = fv5s.composite（0.75 × 上一步分數產業內百分位 + 0.25 × 借券餘額 ts_rank S1 產業內百分位，S1 缺值 0.5）。
- 名單：fv5s.tranche_weights（產業內前／後 1/3 等權、只放空 fv5 可借者、不含緩衝）。
- V：fv5v.reweight（各腿 1/σ、單檔 1/3 ~ 3 倍等權，放空端重查條件 D）。
- β、借券費沿用 fv5；三份資金錯開、結算與成本同 fv5。

用法（於專案根目錄）：
    .venv/Scripts/python forward/run_forward_fv5x.py freeze
    .venv/Scripts/python forward/run_forward_fv5x.py backfill
    .venv/Scripts/python forward/run_forward_fv5x.py resolve
    .venv/Scripts/python forward/run_forward_fv5x.py report
    （每日由 forward/run_forward.py auto 在 fv5v 之後呼叫 auto()）
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
from forward import run_forward_fv5e as fv5e  # noqa: E402
from forward import run_forward_fv5s as fv5s  # noqa: E402
from forward import run_forward_fv5v as fv5v  # noqa: E402

DIR = ROOT / "forward" / "fv5x"
SPEC_PATH = DIR / "spec.yaml"
PREDICTIONS = DIR / "predictions.csv"
SEGMENTS = DIR / "segments.csv"
PERIODS = DIR / "periods.csv"
REPORT = DIR / "REPORT.md"
PUBLISH_FILES = [str(p.relative_to(ROOT)).replace("\\", "/") for p in (SPEC_PATH, PREDICTIONS, SEGMENTS, PERIODS, REPORT)]
N_TRANCHE = fv5.N_TRANCHE

PRED_COLUMNS = ["spec_version", "mode", "as_of_date", "tranche", "ticker", "sector", "score_fv5", "esue", "s1", "score", "shortable", "fee", "beta",
                "weight_fv5", "weight_ew", "sigma", "weight", "tranche_beta", "run_utc", "git_commit"]
SEGMENT_COLUMNS = fv5.SEGMENT_COLUMNS
PERIOD_COLUMNS = ["seg_start", "seg_end", "mode", "n_active", "book_net", "fv5_net", "diff", "resolved_utc"]


# ---------------------------------------------------------------------------
# 規則（凍結）
# ---------------------------------------------------------------------------

def combine(g: pd.DataFrame, k: pd.DataFrame, s1: pd.Series) -> tuple[pd.Series, pd.Series]:
    """g：fv5 當日成員；k：已知 ESUE；s1：S1 分數。回傳（合成分數、等權名單權重）。"""
    score_e = fv5e.override_scores(g, k)
    comp = fv5s.composite(g.assign(score=g["ticker"].map(score_e)), s1)
    return comp, fv5s.tranche_weights(g, comp)


def frozen_sources() -> dict[str, str]:
    out = {f"fv5e:{k}": v for k, v in fv5e.frozen_sources().items()}
    out.update({f"fv5s:{k}": v for k, v in fv5s.frozen_sources().items()})
    out.update({f"fv5v:{k}": v for k, v in fv5v.frozen_sources().items()})
    out["fv5x.combine"] = inspect.getsource(combine)
    return out


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
        raise SystemExit("fv5x 規則程式碼已與凍結時不同：" + "、".join(changed) + "。修改規則請建立新版本。")
    return spec


# ---------------------------------------------------------------------------
# 指令
# ---------------------------------------------------------------------------

def cmd_freeze(args) -> None:
    if SPEC_PATH.exists():
        raise SystemExit(f"{SPEC_PATH} 已存在；凍結只做一次。")
    DIR.mkdir(parents=True, exist_ok=True)
    spec = {
        "spec_version": "fv5x",
        "frozen_utc": fv1.now_utc(),
        "frozen_git_commit": git_commit(),
        "rules": {
            "base": "讀 forward/fv5/predictions.csv 同一預測日的成員資料（產業、SUE 分數、可借、借券費、β）",
            "E": "fv5e.override_scores：金融股有已知 ESUE 者，以 ESUE 百分位取全體分數同分位數值",
            "S": "fv5s.composite：0.75 × 分數產業內百分位 + 0.25 × S1（借券賣出餘額比 ts_rank）產業內百分位",
            "list": "fv5s.tranche_weights：產業內前／後 1/3 等權、只放空可借者",
            "V": "fv5v.reweight：各腿 1/σ（60 日）、單檔 1/3 ~ 3 倍等權，放空端重查條件 D",
            "portfolio": "三份資金錯開、結算與成本同 fv5",
        },
        "preregistration": {
            "primary_metric": "組合每段淨報酬（同 fv5），以及同段 fv5x − fv5 的差",
            "backtest_expectation": {"sharpe_2019_2022": 1.91, "sharpe_2023_2026": 2.22, "sharpe_full": 2.05,
                                     "fv5_sharpe_full": 1.64, "source": "docs/fv5_family_report.md"},
            "evaluation": ["只把 mode = live 的期數算入，backfill 另列",
                           "與 fv5e、fv5s、fv5v 一起依 docs/forward_validation.md 的前瞻採用規則比較",
                           "回測每段報酬差的檢定力很低（fv5x 波動較低，每段平均報酬差為負），另報告兩者的期間 Sharpe 與波動"],
            "notes": "三項修改都是看過結果後才定的，回測含選擇偏誤；不得依前瞻結果回頭調整規則。",
        },
        "frozen_source_sha256": source_hashes(),
    }
    SPEC_PATH.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"已凍結 fv5x 規格 → {SPEC_PATH}")


def predict(as_of: str, mode: str | None = None) -> bool:
    spec = load_spec()
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    if (preds["as_of_date"] == as_of).any():
        return False
    p5 = fv1.read_csv(fv5.PREDICTIONS, fv5.PRED_COLUMNS)
    g = p5[p5["as_of_date"] == as_of].copy()
    if g.empty:
        print(f"[fv5x] {as_of}：fv5 尚未預測，略過")
        return False
    a = pd.Timestamp(as_of)
    client = fv5.snapshot(dt.date.today().strftime("%Y-%m-%d"))
    k = fv5e.known_esue(fv5e._esue_before(a), fv1.trading_calendar(client, "2025-01-01"), a)
    s1 = fv5s._s1_at(g, a)
    comp, w_ew = combine(g, k, s1)
    ge = g.assign(weight=g["ticker"].map(w_ew).fillna(0.0))
    sigma, bx = fv5v._inputs_at(ge, a)
    w = fv5v.reweight(w_ew[w_ew != 0], sigma, g[["ticker", "fee"]].merge(bx, on="ticker", how="left"))
    b = float((w * g.set_index("ticker")["beta"].reindex(w.index).fillna(1.0)).sum())
    mode = mode or ("backfill" if as_of < spec["frozen_utc"][:10] else g["mode"].iloc[0])     # 凍結日以前的預測日一律 backfill
    km = k.set_index("ticker")
    out = g.assign(spec_version=spec["spec_version"], mode=mode, score_fv5=g["score"], weight_fv5=g["weight"],
                   esue=g["ticker"].map(km["esue"]) if len(km) else np.nan, s1=g["ticker"].map(s1), score=g["ticker"].map(comp),
                   weight_ew=g["ticker"].map(w_ew).fillna(0.0), sigma=g["ticker"].map(sigma),
                   weight=g["ticker"].map(w).fillna(0.0), tranche_beta=b, run_utc=fv1.now_utc(), git_commit=git_commit())
    DIR.mkdir(parents=True, exist_ok=True)
    fv1.append_csv(PREDICTIONS, out, PRED_COLUMNS)
    diff = int((np.sign(out["weight"]) != np.sign(out["weight_fv5"])).sum())
    print(f"[fv5x {out['mode'].iloc[0]}] {as_of}：多 {(w > 0).sum()}、空 {(w < 0).sum()}，方向與 fv5 不同 {diff} 檔，β {b:+.2f}")
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
        print(f"fv5x {a_s} → {b:%Y-%m-%d}：組合 {book:+.2%}（fv5 {f5:+.2%}）")
    return n


def cmd_report(args) -> None:
    spec = load_spec()
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    per = fv1.read_csv(PERIODS, PERIOD_COLUMNS)
    lines = ["# 前瞻驗證報告 fv5x：fv5e + fv5s + fv5v 合併規格（自動產生）", "",
             f"- 規格：`fv5x`（凍結於 {spec['frozen_utc']}，git `{spec['frozen_git_commit'][:8]}`）；與 fv5 平行，研究依據 "
             "[docs/fv5_family_report.md](../../docs/fv5_family_report.md)。研究記錄，非投資建議。",
             f"- 預測日 {preds['as_of_date'].nunique()} 個，已結算段落 {len(per)} 個",
             "- 主要指標：組合每段淨報酬（扣交易成本、借券費，台指期對沖），以及同段 fv5x − fv5 的差。", "",
             "## 累積結果", "", "| 範圍 | fv5x 每段淨報酬 | fv5 每段淨報酬 | fv5x − fv5 |", "|---|---|---|---|"]
    for label, mode in (("live（正式）", "live"), ("backfill（凍結後回填）", "backfill")):
        sub = per[per["mode"] == mode] if len(per) else per
        if len(sub):
            lines.append(f"| {label} | {fv2.summary(sub['book_net'], True)} | {fv2.summary(sub['fv5_net'], True)} | {fv2.summary(sub['diff'], True)} |")
        else:
            lines.append(f"| {label} | 尚無資料 | | |")
    lines += ["", "## 各段", "", "| 段落 | mode | 在場資金份數 | fv5x | fv5 | 差 |", "|---|---|---|---|---|---|"]
    for r in per.itertuples():
        lines.append(f"| {r.seg_start} → {r.seg_end} | {r.mode} | {int(r.n_active)} | {r.book_net:+.2%} | {r.fv5_net:+.2%} | {r.diff:+.2%} |")
    lines += ["", "## 各預測日", "", "| 預測日 | mode | 資金份 | 做多 | 放空 | 方向與 fv5 不同 | 金融股有 ESUE | S1 有值 |", "|---|---|---|---|---|---|---|---|"]
    for a, bt in preds.groupby("as_of_date"):
        diff = int((np.sign(bt["weight"]) != np.sign(bt["weight_fv5"])).sum())
        lines.append(f"| {a} | {bt['mode'].iloc[0]} | {int(bt['tranche'].iloc[0]) + 1} | {(bt['weight'] > 0).sum()} | {(bt['weight'] < 0).sum()} | "
                     f"{diff} | {int(bt['esue'].notna().sum())} | {int(bt['s1'].notna().sum())} |")
    lines += ["", "## 事先登錄的評估方式", ""] + [f"- {e}" for e in spec["preregistration"]["evaluation"]]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"fv5x 報告 → {REPORT}")


def auto() -> bool:
    """排程用（fv5v 之後）：補上 fv5 已預測的日期、結算已過的段落；有變動回傳 True。"""
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
    p = argparse.ArgumentParser(description="前瞻驗證 fv5x")
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("freeze", "backfill", "resolve", "report"):
        sub.add_parser(c)
    a = p.parse_args(argv)
    {"freeze": cmd_freeze, "backfill": cmd_backfill, "resolve": cmd_resolve, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
