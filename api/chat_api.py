"""
Chat API — Чат с агентом через OpenRouter.
Префикс роутов задаётся в main.py: /api/chat
"""
import os
import json
import tempfile
import asyncio
from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from pypdf import PdfReader

from database import get_session
import crud
from models import ChatMessage, ChatResponse

# Import instructions helpers
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.base_agent import _load_constitution, _load_project_context, _load_instructions

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISCUSSION_FILE = os.path.join(PROJECT_ROOT, "memory", "discussion_log.json")
ATTACHMENTS_DIR = os.path.join(PROJECT_ROOT, "memory", "attachments")
MAX_ATTACHMENT_TEXT = 8000


def _extract_text_from_file(filepath: str, ext: str) -> str:
    """Извлечь текст из прикреплённого файла."""
    if not os.path.exists(filepath):
        return ""
    try:
        if ext == ".pdf":
            reader = PdfReader(filepath)
            texts = []
            for page in reader.pages[:20]:  # Макс 20 страниц
                text = page.extract_text() or ""
                texts.append(text)
                if sum(len(t) for t in texts) > MAX_ATTACHMENT_TEXT:
                    break
            result = "\n\n".join(texts)[:MAX_ATTACHMENT_TEXT]
            return result
        elif ext in (".txt", ".md"):
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()[:MAX_ATTACHMENT_TEXT]
        elif ext == ".json":
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return json.dumps(data, ensure_ascii=False, indent=2)[:MAX_ATTACHMENT_TEXT]
    except Exception as e:
        return f"[Ошибка чтения файла: {str(e)}]"
    return ""


def _build_attachment_context(attachments) -> str:
    """Собрать текст из всех прикреплённых файлов агента."""
    if not attachments:
        return ""
    texts = []
    for att in attachments:
        filename = att.filename if hasattr(att, 'filename') else att.get('filename', '')
        ext = os.path.splitext(filename)[1].lower()
        if ext in (".pdf", ".txt", ".md", ".json"):
            filepath = os.path.join(ATTACHMENTS_DIR, filename)
            text = _extract_text_from_file(filepath, ext)
            if text:
                texts.append(f"--- Файл: {filename} ---\n{text}")
    if not texts:
        return ""
    return "\n\n".join(texts)


async def _post_discussion(db: AsyncSession, agent_id: str, agent_name: str, content: str):
    """Записать сообщение агента в Discussion канал (через БД)."""
    import crud as crud_module
    entry = {
        "agent_id": agent_id,
        "content": f"[{agent_name}] {content[:500]}",
        "msg_type": "agent",
        "timestamp": datetime.now().isoformat(),
    }
    try:
        await crud_module.add_discussion(db, entry)
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

    # Извлекаем текст из прикреплённых файлов
    attachments = await crud.get_attachments(db, agent_id)
    attachment_context = _build_attachment_context(attachments)

    # Логирование: что реально передаётся агенту
    if attachment_context:
        print(f"\n[CHAT API] Agent '{agent_id}' attachment context ({len(attachment_context)} chars):")
        print(attachment_context[:500])
        print("...")
    else:
        print(f"\n[CHAT API] Agent '{agent_id}' has NO attachments")

    # Получаем историю чата
    messages = await crud.get_messages(db, agent_id)
    context = [{"role": m.role, "content": m.content} for m in messages[-10:]]

    # ВАЖНО: Текст прикреплённых файлов идёт как ПЕРВОЕ сообщение пользователя
    # перед основным запросом, чтобы LLM видел контекст ДО ответа
    if attachment_context:
        context.insert(0, {
            "role": "user",
            "content": f"[ПРИКРЕПЛЁННЫЙ ФАЙЛ — КОНТЕКСТ ПРОЕКТА]\n{attachment_context}\n\n[КОНЕЦ ФАЙЛА. Используй этот текст как основу для ответов.]"
        })

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
    await _post_discussion(db, agent_id, agent.name, f"Ответил: {reply[:200]}")

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
