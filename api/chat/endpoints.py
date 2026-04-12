"""Chat endpoints."""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from models import ChatMessage, ChatResponse
from agents.base_agent import _load_constitution, _load_project_context, _load_instructions
from api.chat.helpers import build_attachment_context, post_discussion

router = APIRouter()


@router.post("/{agent_id}", response_model=ChatResponse)
async def chat(agent_id: str, body: ChatMessage, db: AsyncSession = Depends(get_session)):
    """Send message to agent and get response."""
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")

    # Save user message to DB
    await crud.add_message(db, agent_id, "user", body.message, datetime.now().isoformat())

    # Build system prompt
    constitution = _load_constitution()
    project_context = _load_project_context()
    instructions = _load_instructions()
    agent_instructions = instructions.get(agent_id, agent.instructions)

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
    if agent_instructions:
        parts.append("")
        parts.append("[ТВОИ ИНСТРУКЦИИ]")
        parts.append(agent_instructions)

    system_prompt = "\n".join(parts)

    # Extract text from attached files
    attachments = await crud.get_attachments(db, agent_id)
    attachment_context = build_attachment_context(attachments)

    # Get chat history
    messages = await crud.get_messages(db, agent_id)
    context = [{"role": m.role, "content": m.content} for m in messages[-10:]]

    # Attached file text goes as FIRST user message before main request
    if attachment_context:
        context.insert(0, {
            "role": "user",
            "content": f"[ПРИКРЕПЛЁННЫЙ ФАЙЛ — КОНТЕКСТ ПРОЕКТА]\n{attachment_context}\n\n[КОНЕЦ ФАЙЛА. Используй этот текст как основу для ответов.]"
        })

    # Call OpenRouter
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

    # Save response to DB
    await crud.add_message(db, agent_id, "assistant", reply, datetime.now().isoformat())

    # Update agent status
    await crud.update_agent(db, agent_id, {"status": "idle"})

    # Auto-post to discussion channel
    await post_discussion(db, agent_id, agent.name, f"Ответил: {reply[:200]}")

    return ChatResponse(reply=reply, agent_id=agent_id, status="idle")


@router.get("/{agent_id}/history")
async def get_history(agent_id: str, db: AsyncSession = Depends(get_session)):
    """Get agent chat history."""
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")
    messages = await crud.get_messages(db, agent_id)
    return {
        "agent_id": agent_id,
        "history": [{"role": m.role, "content": m.content, "time": m.time} for m in messages],
    }
