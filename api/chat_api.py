"""
Chat API — Чат с агентом через OpenRouter.
Префикс роутов задаётся в main.py: /api/chat
"""
import os
import json
import tempfile
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from database import get_session
import crud
from models import ChatMessage, ChatResponse

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


@router.post("/{agent_id}", response_model=ChatResponse)
async def chat(agent_id: str, body: ChatMessage, db: AsyncSession = Depends(get_session)):
    """Отправить сообщение агенту и получить ответ."""
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")

    # Сохраняем сообщение пользователя в БД
    await crud.add_message(db, agent_id, "user", body.message, datetime.now().isoformat())

    # Строим системный промпт
    from agents.base_agent import _load_constitution, _load_project_context
    constitution = _load_constitution()
    project_context = _load_project_context()

    parts = []
    if constitution:
        parts.append("[КОНСТИТУЦИЯ СТУДИИ — НЕИЗМЕНЯЕМАЯ ЧАСТЬ]")
        parts.append(constitution)
        parts.append("")
    if project_context:
        parts.append("[АКТИВНЫЙ ПРОЕКТ]")
        parts.append(project_context)
        parts.append("")
    parts.append("[ТВОЯ РОЛЬ]")
    parts.append(agent.role)
    if agent.instructions:
        parts.append("")
        parts.append("[ТВОИ ИНСТРУКЦИИ]")
        parts.append(agent.instructions)

    system_prompt = "\n".join(parts)

    # Получаем историю чата
    messages = await crud.get_messages(db, agent_id)
    context = [{"role": m.role, "content": m.content} for m in messages[-10:]]

    # Вызов OpenRouter
    import httpx
    from config import OPENROUTER_API_KEY

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
                    "model": agent.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        *context,
                        {"role": "user", "content": body.message}
                    ]
                }
            )
            data = response.json()
            if response.status_code >= 400:
                error_obj = data.get("error", {}) if isinstance(data, dict) else {}
                error_message = error_obj.get("message") or data.get("message") or response.text
                reply = f"OpenRouter {response.status_code}: {error_message}"
            elif not isinstance(data, dict) or "choices" not in data or not data.get("choices"):
                reply = f"OpenRouter: неожиданный формат ответа: {str(data)[:300]}"
            else:
                reply = data["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        reply = "OpenRouter: таймаут запроса"
    except httpx.ConnectError as e:
        reply = f"OpenRouter: ошибка соединения: {str(e)}"
    except Exception as e:
        reply = f"Ошибка API: {str(e)}"

    # Сохраняем ответ в БД
    await crud.add_message(db, agent_id, "assistant", reply, datetime.now().isoformat())

    # Обновляем статус агента
    await crud.update_agent(db, agent_id, {"status": "idle"})

    # Автозапись в Discussion канал
    _post_discussion(agent_id, f"[{agent.name}] Ответил: {reply[:200]}")

    return ChatResponse(reply=reply, agent_id=agent_id, status="idle")


@router.get("/{agent_id}/history")
async def get_history(agent_id: str, db: AsyncSession = Depends(get_session)):
    """Получить историю чата агента."""
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")
    messages = await crud.get_messages(db, agent_id)
    return {
        "agent_id": agent_id,
        "history": [{"role": m.role, "content": m.content, "time": m.time} for m in messages],
    }
