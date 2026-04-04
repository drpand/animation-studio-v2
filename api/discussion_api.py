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


class DiscussionMessage(BaseModel):
    agent_id: str = "user"
    content: str
    msg_type: str = "user"


@router.get("/")
async def get_discussion(limit: int = 50, db: AsyncSession = Depends(get_session)):
    messages = await crud.get_discussions(db, limit)
    return {"messages": [
        {"agent_id": m.agent_id, "content": m.content, "msg_type": m.msg_type, "timestamp": m.timestamp}
        for m in reversed(messages)
    ]}


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
    return {"ok": True}
