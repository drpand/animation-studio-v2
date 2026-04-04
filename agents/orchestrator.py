"""Orchestrator — Дирижёр, управляет всеми агентами."""
from agents.base_agent import BaseAgent


def create_agent():
    return BaseAgent(
        agent_id="orchestrator",
        name="Orchestrator",
        role="Дирижёр — управляет всеми агентами, строит цепочки задач",
        model="qwen/qwen3.5-9b",
        instructions=(
            "Ты дирижёр аниме-студии РОДИНА. "
            "Твоя задача — анализировать запросы пользователя, определять какие агенты нужны, "
            "строить цепочку выполнения и управлять процессом. "
            "Следуй Конституции Студии РОДИНА."
        ),
        status="idle"
    )
