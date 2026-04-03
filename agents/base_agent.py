"""
Base Agent — базовый класс для всех агентов Animation Studio v2
Интеграция с OpenRouter API, сохранение состояния и истории чата.
"""
import httpx
import json
import os
import tempfile
import threading
from datetime import datetime

from config import OPENROUTER_API_KEY

# Пути
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_PATH = os.path.join(PROJECT_ROOT, "memory")
STATE_FILE = os.path.join(MEMORY_PATH, "agents_state.json")

# Глобальная блокировка для записи в agents_state.json
_state_lock = threading.Lock()


class BaseAgent:
    """Базовый агент с чатом через OpenRouter API."""

    def __init__(self, agent_id, name, role, model, instructions, status="idle", chat_history=None, attachments=None):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.model = model
        self.instructions = instructions
        self.status = status
        self.attachments = attachments or []
        self.chat_history = chat_history or []

    async def chat(self, message):
        """Отправить сообщение агенту, получить ответ через OpenRouter."""
        self.status = "working"

        # Сохраняем сообщение пользователя
        self.chat_history.append({
            "role": "user",
            "content": message,
            "time": datetime.now().isoformat()
        })

        # Строим контекст БЕЗ дублирования последнего user message
        context = self._build_context()

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:7860",
                        "X-Title": "Animation Studio v2"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": self.instructions},
                            *context
                        ]
                    }
                )
                data = response.json()
                reply = data["choices"][0]["message"]["content"]
        except Exception as e:
            reply = f"Ошибка API: {str(e)}"

        # Сохраняем ответ
        self.chat_history.append({
            "role": "assistant",
            "content": reply,
            "time": datetime.now().isoformat()
        })

        self.status = "idle"
        self._save_state()
        return reply

    def _build_context(self):
        """Построить контекст из истории чата. Без дублирования."""
        messages = []
        for msg in self.chat_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        return messages

    def _save_state(self):
        """Атомарно сохранить состояние агента в agents_state.json."""
        with _state_lock:
            if not os.path.exists(STATE_FILE):
                return

            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

            state[self.agent_id] = {
                "name": self.name,
                "role": self.role,
                "model": self.model,
                "status": self.status,
                "instructions": self.instructions,
                "attachments": self.attachments,
                "chat_history": self.chat_history[-50:]  # Храним последние 50 сообщений
            }

            # Атомарная запись через временный файл
            dir_name = os.path.dirname(STATE_FILE)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                    json.dump(state, tmp, ensure_ascii=False, indent=2)
                os.replace(tmp_path, STATE_FILE)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

    def to_dict(self):
        """Сериализация в dict для API."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "model": self.model,
            "status": self.status,
            "instructions": self.instructions,
            "attachments": self.attachments,
            "chat_history": self.chat_history[-20:]  # Для API — последние 20
        }
