"""
Chat API — Чат с агентом через OpenRouter.
Префикс роутов задаётся в main.py: /api/chat
"""
import os
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.base_agent import BaseAgent, STATE_FILE

router = APIRouter()


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
