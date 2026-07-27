from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage
import logging

from .state import CriticState
from .quality_critic import QualityCritic
from backend.app.agents.teacher_agent.utils.llm_utils import get_llm # Reuse LLM getter

logger = logging.getLogger(__name__)

# --- Nodes ---
from .nodes import (
    fact_critic_node,
    quality_critic_node,
    aggregate_feedback_node
)

# --- Graph ---

critic_workflow = StateGraph(CriticState)

critic_workflow.add_node("fact_critic", fact_critic_node)
critic_workflow.add_node("quality_critic", quality_critic_node)
critic_workflow.add_node("aggregate_feedback", aggregate_feedback_node)

# Parallel execution
critic_workflow.set_entry_point("fact_critic") # Start with Fact
critic_workflow.add_edge("fact_critic", "quality_critic") # Currently sequential for simplicity in LangGraph 
# To do parallel: 
# critic_workflow.set_entry_point("start_node")
# critic_workflow.add_edge("start_node", "fact_critic")
# critic_workflow.add_edge("start_node", "quality_critic")
# But we need a start node. 
# For now, sequential is fine: Fact -> Quality -> Aggregate.
# Or better: use a fan-out pattern if latency is critical. 
# Given the async nature, sequential nodes with async calls inside are still blocking.
# Let's keep it simple: Fact -> Quality -> Aggregate.

critic_workflow.add_edge("quality_critic", "aggregate_feedback")
critic_workflow.add_edge("aggregate_feedback", END)

critic_app = critic_workflow.compile()
