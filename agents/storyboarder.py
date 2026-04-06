"""Storyboarder — Раскадровщик, кадры с таймингом."""
from agents.base_agent import BaseAgent

def create_agent():
    return BaseAgent(
        agent_id="storyboarder",
        name="Storyboarder",
        role="Раскадровщик — кадры с таймингом",
        model="google/gemini-3-flash-preview",
        instructions="Ты раскадровщик анимационного проекта. Создавай списки кадров с таймингом и описаниями ракурсов, соблюдая требования активного проекта.",
        status="idle"
    )
