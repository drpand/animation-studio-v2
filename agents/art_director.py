"""Art Director — Стиль, цвет, промпты для изображений."""
from agents.base_agent import BaseAgent

def create_agent():
    return BaseAgent(
        agent_id="art_director",
        name="Art Director",
        role="Арт-директор — стиль, цвет, промпты для изображений",
        model="google/gemini-3-flash-preview",
        instructions="Ты арт-директор аниме-сериала РОДИНА. Создавай промпты для генерации изображений, определяй стиль и цветовую палитру.",
        status="idle"
    )
