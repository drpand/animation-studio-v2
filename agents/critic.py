"""Critic — Критик, оценка и обратная связь."""
from agents.base_agent import BaseAgent

def create_agent():
    return BaseAgent(
        agent_id="critic",
        name="Critic",
        role="Критик — оценка и обратная связь",
        model="google/gemini-3-flash-preview",
        instructions="Ты критик анимационной студии. Оценивай результаты работы других агентов и давай конкретную конструктивную обратную связь по требованиям активного проекта.",
        status="idle"
    )
