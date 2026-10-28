"""MCP server：把多 Agent 研究系統包成 Claude 可呼叫的工具（官方 Python SDK 2.x 的 MCPServer）。

用法（於專案根目錄）：
    .venv/Scripts/python -m pip install "mcp>=2.3"
    .venv/Scripts/python mcp_server/server.py          # stdio transport，給 Claude Code / Claude Desktop 啟動
登錄到 Claude Code：
    claude mcp add tw-research -- D:/side_project/precision-weighted-investment-agent/.venv/Scripts/python.exe D:/side_project/precision-weighted-investment-agent/mcp_server/server.py

工具：
- analyze_stock：財報、總經/籌碼、技術面 Agent 各自判讀（規則式，不呼叫 LLM），再以仲裁層合併
- forward_portfolio：前瞻規格（fv5、fv5x…）最新預測日的多空持股
- forward_report：前瞻驗證報告（REPORT.md）
- list_ideas：點子卡清單（可依狀態篩選）

注意：
- 資料走 FinMindClient 的本地快取；未快取時會用 .env 的 FINMIND_API_TOKEN 向 FinMind 請求。
- README 的回測顯示規則式 Agent 沒有可靠的方向預測力（Brier 高於 0.25 基準），
  analyze_stock 只是展示系統架構，不是選股依據。研究記錄，非投資建議。
- 預期內的錯誤（規格不存在等）用 ToolError，訊息才會傳給模型；其他例外只顯示 Error executing tool。
- stdio transport 下 stdout 是協定通道，不能 print；Agent 內部的訊息一律導向 stderr。
"""
from __future__ import annotations

import contextlib
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DISCLAIMER = "研究記錄，非投資建議。"
AGENT_IDS = ("fundamentals_agent", "macro_agent", "technical_agent")

mcp = MCPServer("tw-research", instructions="台股多 Agent 研究系統與前瞻驗證記錄。研究記錄，非投資建議。")


def _client():
    import dotenv
    from data.fetch_financials import FinMindClient

    dotenv.load_dotenv(ROOT / ".env")
    return FinMindClient()


def _build_agent(agent_id: str, client, as_of_date: str, horizon: int):
    if agent_id == "fundamentals_agent":
        from agents.fundamentals_agent import FundamentalsAgent
        from data.fetch_financials import FinMindFundamentalsProvider

        return FundamentalsAgent(FinMindFundamentalsProvider(client, history_start="2020-01-01"), horizon_days=horizon)
    if agent_id == "macro_agent":
        from agents.macro_agent import MacroAgent
        from data.fetch_macro import FinMindMacroProvider

        return MacroAgent(FinMindMacroProvider(client, history_start="2023-01-01"), horizon_days=horizon)
    if agent_id == "technical_agent":
        from agents.technical_agent import TechnicalAgent
        from data.fetch_technical import FinMindTechnicalProvider

        # 技術指標需要約 60 個交易日暖身，價量從 as_of_date 前一年起抓
        start = (date.fromisoformat(as_of_date) - timedelta(days=365)).isoformat()
        return TechnicalAgent(FinMindTechnicalProvider(client, start, as_of_date), horizon_days=horizon)
    raise ValueError(f"未知的 agent：{agent_id}，可用：{AGENT_IDS}")


@mcp.tool()
def analyze_stock(
    ticker: str,
    as_of_date: str,
    agents: list[str] | None = None,
    horizon_days: int = 20,
) -> dict:
    """對單一台股在指定日期執行多 Agent 判讀並合併。

    Args:
        ticker: 股票代號，例如 "2330.TW" 或 "2330"
        as_of_date: 判讀日期 YYYY-MM-DD（Agent 只用這天以前的資料）
        agents: 要啟用的 Agent，預設全部（fundamentals_agent、macro_agent、technical_agent）
        horizon_days: 預測期間（交易日）

    回傳各 Agent 的 signal / confidence / rationale，以及等精度合併後的看多機率。
    """
    from arbitrator.merge import merge

    ticker = ticker if "." in ticker else f"{ticker}.TW"
    agent_ids = list(agents or AGENT_IDS)
    client = _client()
    outputs, errors = [], {}
    with contextlib.redirect_stdout(sys.stderr):
        for a in agent_ids:
            try:
                outputs.append(_build_agent(a, client, as_of_date, horizon_days).analyze(ticker, as_of_date))
            except Exception as e:  # 單一 Agent 失敗不影響其他 Agent
                errors[a] = f"{type(e).__name__}: {e}"
    result: dict = {"ticker": ticker, "as_of_date": as_of_date, "disclaimer": DISCLAIMER}
    result["agents"] = [
        {k: o.to_dict()[k] for k in ("agent_id", "signal", "confidence", "rationale", "evidence_refs")} for o in outputs
    ]
    if outputs:
        # 沒有歷史精度可用，各 Agent 等精度（= 簡單平均 baseline）
        m = merge(outputs, {o.agent_id: 1.0 for o in outputs})
        result["merged"] = {
            "signal": m.signal,
            "probability_bullish": round(m.probability_bullish, 4),
            "final_score": round(m.final_score, 4),
            "uncertainty": round(m.uncertainty, 4),
            "weighting": "等精度（各 Agent precision = 1）",
        }
    if errors:
        result["errors"] = errors
    return result


def _spec_dir(spec: str) -> Path:
    d = ROOT / "forward" / spec
    if not spec.isidentifier() or not d.is_dir():
        avail = sorted(p.name for p in (ROOT / "forward").iterdir() if (p / "REPORT.md").exists())
        raise ToolError(f"找不到前瞻規格 {spec!r}，可用：{avail}")
    return d


@mcp.tool()
def forward_portfolio(spec: str = "fv5x", as_of_date: str | None = None, top_n: int = 10) -> dict:
    """前瞻規格在某個預測日的多空持股（預設最新預測日）。

    Args:
        spec: 前瞻規格名稱，例如 "fv5"、"fv5x"
        as_of_date: 預測日 YYYY-MM-DD；省略時取最新一日
        top_n: 多方與空方各回傳權重最大的幾檔
    """
    df = pd.read_csv(_spec_dir(spec) / "predictions.csv", dtype={"ticker": str})
    dates = sorted(df["as_of_date"].unique())
    d = as_of_date or dates[-1]
    if d not in dates:
        raise ToolError(f"{spec} 沒有 {d} 的預測，可用預測日：{dates}")
    x = df[df["as_of_date"] == d]
    wcol = "weight" if "weight" in x.columns else [c for c in x.columns if c.startswith("weight")][0]
    x = x[x[wcol] != 0]
    cols = [c for c in ("ticker", "sector", wcol, "score", "beta") if c in x.columns]

    def legs(sub: pd.DataFrame) -> list[dict]:
        return sub[cols].round(5).to_dict("records")

    return {
        "spec": spec,
        "as_of_date": d,
        "mode": x["mode"].iloc[0] if "mode" in x.columns and len(x) else None,
        "tranche": int(x["tranche"].iloc[0]) if "tranche" in x.columns and len(x) else None,
        "n_long": int((x[wcol] > 0).sum()),
        "n_short": int((x[wcol] < 0).sum()),
        "top_long": legs(x.nlargest(top_n, wcol)),
        "top_short": legs(x.nsmallest(top_n, wcol)),
        "weight_column": wcol,
        "disclaimer": DISCLAIMER,
    }


@mcp.tool()
def forward_report(spec: str = "fv5x") -> str:
    """讀取前瞻驗證報告（forward/<spec>/REPORT.md，Markdown）。"""
    return (_spec_dir(spec) / "REPORT.md").read_text(encoding="utf-8")


@mcp.tool()
def list_ideas(status: str | None = None) -> list[dict]:
    """列出研究點子卡。

    Args:
        status: 依狀態篩選的關鍵字，例如 "待確認"、"已測"、"通過"；省略時全部列出
    """
    df = pd.read_csv(ROOT / "research" / "ideas.csv", dtype=str).fillna("")
    if status:
        df = df[df["status"].str.contains(status, regex=False)]
    return df[["id", "title", "status", "priority", "test_type", "path"]].to_dict("records")


if __name__ == "__main__":
    mcp.run()
