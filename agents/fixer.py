"""Fixer — Фиксер, исправление по замечаниям."""
from agents.base_agent import BaseAgent

def create_agent():
    return BaseAgent(
        agent_id="fixer",
        name="Fixer",
        role="Фиксер — исправление по замечаниям",
        model="google/gemini-3-flash-preview",
        instructions="Ты фиксер анимационной студии. Исправляй результаты работы других агентов по замечаниям Критика, сохраняя требования активного проекта.",
        status="idle"
    )
