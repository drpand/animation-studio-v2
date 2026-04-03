"""
Discussion API — Общий канал обсуждения студии.
Префикс роутов задаётся в main.py: /api/discussion
"""
import os
import json
import tempfile
import threading
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISCUSSION_FILE = os.path.join(PROJECT_ROOT, "memory", "discussion_log.json")
MAX_MESSAGES = 100

_disc_lock = threading.Lock()


def _load_discussion() -> dict:
    if not os.path.exists(DISCUSSION_FILE):
        return {"messages": []}
    with open(DISCUSSION_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_discussion(data: dict):
    # Ограничиваем количество сообщений
    if len(data.get("messages", [])) > MAX_MESSAGES:
        data["messages"] = data["messages"][-MAX_MESSAGES:]
    dir_name = os.path.dirname(DISCUSSION_FILE)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, DISCUSSION_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


router = APIRouter()


class DiscussionMessage(BaseModel):
    agent_id: str = "user"
    content: str
    msg_type: str = "user"  # user, agent, critic, med_otdel, system


@router.get("/")
async def get_discussion(limit: int = 50):
    """Получить последние сообщения из общего канала."""
    data = _load_discussion()
    messages = data.get("messages", [])
    return {"messages": messages[-limit:]}


@router.post("/")
async def post_message(msg: DiscussionMessage):
    """Добавить сообщение в общий канал."""
    with _disc_lock:
        data = _load_discussion()
        entry = {
            "agent_id": msg.agent_id,
            "content": msg.content,
            "msg_type": msg.msg_type,
            "timestamp": datetime.now().isoformat(),
        }
        data["messages"].append(entry)
        _save_discussion(data)
    return {"ok": True, "message": entry}


@router.post("/system")
async def post_system_message(agent_id: str = "", content: str = "", msg_type: str = "system"):
    """Добавить системное сообщение (из МЕД-ОТДЕЛА, Критика и т.д.)."""
    with _disc_lock:
        data = _load_discussion()
        entry = {
            "agent_id": agent_id or "system",
            "content": content,
            "msg_type": msg_type,
            "timestamp": datetime.now().isoformat(),
        }
        data["messages"].append(entry)
        _save_discussion(data)
    return {"ok": True, "message": entry}


@router.delete("/")
async def clear_discussion():
    """Очистить канал обсуждения."""
    with _disc_lock:
        _save_discussion({"messages": []})
    return {"ok": True}
