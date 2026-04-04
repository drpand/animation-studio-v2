"""
Chat API — Чат с агентом через OpenRouter.
Префикс роутов задаётся в main.py: /api/chat
"""
import os
import json
import tempfile
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.base_agent import BaseAgent, STATE_FILE

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISCUSSION_FILE = os.path.join(PROJECT_ROOT, "memory", "discussion_log.json")


def _post_discussion(agent_id: str, content: str):
    """Записать сообщение агента в Discussion канал."""
    entry = {
        "agent_id": agent_id,
        "content": content[:500],
        "msg_type": "agent",
        "timestamp": datetime.now().isoformat(),
    }
    try:
        if os.path.exists(DISCUSSION_FILE):
            with open(DISCUSSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"messages": []}
        data["messages"].append(entry)
        if len(data["messages"]) > 200:
            data["messages"] = data["messages"][-200:]
        dir_name = os.path.dirname(DISCUSSION_FILE)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, DISCUSSION_FILE)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    except Exception:
        pass


def _load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _create_agent_from_state(agent_id: str) -> BaseAgent:
    """Создать BaseAgent из сохранённого состояния (с историей чата)."""
    state = _load_state()
    if agent_id not in state:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")

    data = state[agent_id]
    return BaseAgent(
        agent_id=agent_id,
        name=data.get("name", agent_id),
        role=data.get("role", ""),
        model=data.get("model", ""),
        instructions=data.get("instructions", ""),
        status=data.get("status", "idle"),
        attachment_objects=data.get("attachment_objects", []),
        attachments=data.get("attachments", []),
        chat_history=data.get("chat_history", []),
    )


class ChatMessage(BaseModel):
    message: str


@router.post("/{agent_id}")
async def chat(agent_id: str, body: ChatMessage):
    """Отправить сообщение агенту и получить ответ."""
    agent = _create_agent_from_state(agent_id)
    reply = await agent.chat(body.message)

    # Автозапись в Discussion канал
    _post_discussion(agent_id, f"[{agent.name}] Ответил: {reply[:200]}")

    return {
        "reply": reply,
        "agent_id": agent_id,
        "status": agent.status,
    }


@router.get("/{agent_id}/history")
async def get_history(agent_id: str):
    """Получить историю чата агента."""
    state = _load_state()
    if agent_id not in state:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")
    return {
        "agent_id": agent_id,
        "history": state[agent_id].get("chat_history", []),
    }
