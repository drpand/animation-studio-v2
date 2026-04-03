"""Director — Режиссёр, принимает творческие решения."""
from agents.base_agent import BaseAgent

def create_agent():
    return BaseAgent(
        agent_id="director",
        name="Director",
        role="Режиссёр — творческие решения",
        model="google/gemini-3-flash-preview",
        instructions="Ты режиссёр аниме-сериала РОДИНА. Принимай творческие решения по сценам, персонажам, настроению.",
        status="idle"
    )
