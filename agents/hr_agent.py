"""HR Agent — Создание новых агентов под задачу."""
from agents.base_agent import BaseAgent

def create_agent():
    return BaseAgent(
        agent_id="hr_agent",
        name="HR Agent",
        role="HR — создание новых агентов под задачу",
        model="google/gemini-3-flash-preview",
        instructions="Ты HR аниме-студии РОДИНА. Когда задача не решается существующими агентами — создавай нового специалиста под задачу.",
        status="idle"
    )
