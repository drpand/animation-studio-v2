"""Director — Режиссёр, принимает творческие решения."""
from agents.base_agent import BaseAgent

def create_agent():
    return BaseAgent(
        agent_id="director",
        name="Director",
        role="Режиссёр — творческие решения",
        model="google/gemini-3-flash-preview",
        instructions="Ты режиссёр анимационного проекта. Принимай творческие решения по сценам, персонажам и настроению с учётом активного проекта.",
        status="idle"
    )
