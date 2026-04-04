"""
Discussion API — общий канал обсуждения студии.
Префикс роутов задаётся в main.py: /api/discussion
"""
import os
import json
import tempfile
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from database import get_session
import crud

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISCUSSION_FILE = os.path.join(PROJECT_ROOT, "memory", "discussion_log.json")


class DiscussionMessage(BaseModel):
    agent_id: str = "user"
    content: str
    msg_type: str = "user"


def _load_discussion_json() -> list:
    """Загрузить сообщения из JSON файла."""
    if not os.path.exists(DISCUSSION_FILE):
        return []
    try:
        with open(DISCUSSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("messages", [])
    except Exception:
        return []


@router.get("/")
async def get_discussion(limit: int = 50, db: AsyncSession = Depends(get_session)):
    """Получить сообщения из БД и JSON файла, объединить и отсортировать."""
    # Из БД
    db_messages = await crud.get_discussions(db, limit)
    db_list = [
        {"agent_id": m.agent_id, "content": m.content, "msg_type": m.msg_type, "timestamp": m.timestamp}
        for m in db_messages
    ]
    # Из JSON
    json_list = _load_discussion_json()
    
    # Объединяем и сортируем по timestamp
    all_messages = db_list + json_list
    all_messages.sort(key=lambda m: m.get("timestamp", ""))
    
    return {"messages": all_messages[-limit:]}


@router.post("/")
async def post_message(msg: DiscussionMessage, db: AsyncSession = Depends(get_session)):
    entry = await crud.add_discussion(db, {
        "agent_id": msg.agent_id, "content": msg.content[:500],
        "msg_type": msg.msg_type, "timestamp": datetime.now().isoformat(),
    })
    return {"ok": True, "message": {"id": entry.id, **msg.model_dump()}}


@router.delete("/")
async def clear_discussion(db: AsyncSession = Depends(get_session)):
    from sqlalchemy import delete
    from database import Discussion
    await db.execute(delete(Discussion))
    await db.commit()
    # Также очистить JSON
    if os.path.exists(DISCUSSION_FILE):
        with open(DISCUSSION_FILE, "w", encoding="utf-8") as f:
            json.dump({"messages": []}, f, ensure_ascii=False, indent=2)
    return {"ok": True}
