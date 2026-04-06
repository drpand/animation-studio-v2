"""DOP — Оператор-постановщик, свет, угол, атмосфера."""
from agents.base_agent import BaseAgent

def create_agent():
    return BaseAgent(
        agent_id="dop",
        name="DOP",
        role="Оператор-постановщик — свет, угол, атмосфера",
        model="google/gemini-3-flash-preview",
        instructions="Ты оператор-постановщик анимационного проекта. Определяй свет, угол камеры и атмосферу каждого кадра с учётом активного проекта.",
        status="idle"
    )
