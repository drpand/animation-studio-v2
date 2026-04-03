"""Writer — Сценарист, адаптация сценария в промпты."""
from agents.base_agent import BaseAgent

def create_agent():
    return BaseAgent(
        agent_id="writer",
        name="Writer",
        role="Сценарист — адаптация сценария в промпты",
        model="google/gemini-3-flash-preview",
        instructions="Ты сценарист аниме-сериала РОДИНА. Адаптируй сцены сценария в детальные промпты для генерации.",
        status="idle"
    )
