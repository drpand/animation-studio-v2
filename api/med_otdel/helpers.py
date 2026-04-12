"""Shared helpers for med_otdel API endpoints."""
import os
import json
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def get_last_agent_result(db, agent_id: str) -> str:
    """Get last assistant message from agent."""
    import crud
    messages = await crud.get_messages(db, agent_id)
    for msg in reversed(messages):
        if msg.role == "assistant":
            return msg.content
    return ""


def read_med_log_file(limit: int = 20) -> list:
    """Read med_log.json file as fallback."""
    med_file = os.path.join(PROJECT_ROOT, "memory", "med_log.json")
    try:
        if os.path.exists(med_file):
            with open(med_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            file_entries = data.get("entries", [])
            return list(reversed(file_entries[-limit:]))
    except Exception:
        pass
    return []
