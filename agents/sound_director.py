"""Sound Director — Музыка, голоса, лейтмотивы."""
from agents.base_agent import BaseAgent

def create_agent():
    return BaseAgent(
        agent_id="sound_director",
        name="Sound Director",
        role="Звуковой директор — музыка, голоса, лейтмотивы",
        model="google/gemini-3-flash-preview",
        instructions="Ты звуковой директор аниме-сериала РОДИНА. Определяй музыкальное оформление, голоса персонажей, лейтмотивы (включая Пёрсел).",
        status="idle"
    )
