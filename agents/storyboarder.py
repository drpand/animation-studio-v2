"""Storyboarder — Раскадровщик, кадры с таймингом."""
from agents.base_agent import BaseAgent

def create_agent():
    return BaseAgent(
        agent_id="storyboarder",
        name="Storyboarder",
        role="Раскадровщик — кадры с таймингом",
        model="google/gemini-3-flash-preview",
        instructions="Ты раскадровщик аниме-сериала РОДИНА. Создавай списки кадров с таймингом, описаниями ракурсов.",
        status="idle"
    )
