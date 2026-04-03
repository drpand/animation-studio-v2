"""Orchestrator — Дирижёр, управляет всеми агентами."""
from agents.base_agent import BaseAgent

def create_agent():
    return BaseAgent(
        agent_id="orchestrator",
        name="Orchestrator",
        role="Дирижёр — управляет всеми агентами",
        model="qwen/qwen3.5-9b",
        instructions="Ты дирижёр аниме-студии РОДИНА. Управляй агентами, распределяй задачи, следи за качеством.",
        status="idle"
    )
