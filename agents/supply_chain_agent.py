"""供應鏈 Agent（規格 3.4）— Phase 2，MVP 階段為佔位。

設計方向（Phase 2 實作時）：
- 維護簡化知識圖譜（客戶-供應商-替代品關係），初期以手動整理的
  CSV/JSON 起步（例如 config/supply_chain_graph.json）
- LLM 任務：給定上游/下游事件（如 hyperscaler 資本支出上調），
  推論對目標個股的傳導效應與時間遞延
"""
from __future__ import annotations

from agents.base import AgentOutput, BaseAgent


class SupplyChainAgent(BaseAgent):
    agent_id = "supply_chain_agent"

    def analyze(self, ticker: str, as_of_date: str) -> AgentOutput:
        raise NotImplementedError("supply_chain_agent 為 Phase 2 範圍，MVP 未實作")
