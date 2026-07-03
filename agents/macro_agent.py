"""總經/籌碼 Agent（規格 3.5）— Phase 2，MVP 階段為佔位。

設計方向（Phase 2 實作時）：
- 輸入：利率、匯率、半導體庫存週期指標、三大法人買賣超
  （FinMind: TaiwanStockInstitutionalInvestorsBuySell / TaiwanExchangeRate）
- 可先用純量化規則（非 LLM）產生 signal，再視需要加入 LLM 解讀層
"""
from __future__ import annotations

from agents.base import AgentOutput, BaseAgent


class MacroAgent(BaseAgent):
    agent_id = "macro_agent"

    def analyze(self, ticker: str, as_of_date: str) -> AgentOutput:
        raise NotImplementedError("macro_agent 為 Phase 2 範圍，MVP 未實作")
