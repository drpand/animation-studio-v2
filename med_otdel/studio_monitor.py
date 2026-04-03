"""
Studio Monitor — мониторинг здоровья всей студии.
Проверяет % агентов в статусе error. Если >= 50% → studio_alert.
"""
import os
import json
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_STATE_FILE = os.path.join(PROJECT_ROOT, "memory", "agents_state.json")
TASKS_FILE = os.path.join(PROJECT_ROOT, "memory", "tasks.json")


def _load_agents_state() -> dict:
    if not os.path.exists(AGENTS_STATE_FILE):
        return {}
    with open(AGENTS_STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_tasks() -> dict:
    if not os.path.exists(TASKS_FILE):
        return {"studio_status": "ok"}
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_tasks(data: dict):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def check_studio_health() -> dict:
    """
    Проверить здоровье всей студии.
    
    Возвращает:
    {
        "status": "ok" | "warning" | "critical",
        "total_agents": 10,
        "error_agents": 2,
        "error_percentage": 20.0,
        "agents_health": {
            "director": {"status": "idle", "version": "v1", "consecutive_fails": 0},
            ...
        },
        "alert_message": "" | "СТУДИЯ НА ПАУЗЕ: 50%+ агентов в error"
    }
    """
    state = _load_agents_state()
    tasks = _load_tasks()
    
    total = len(state)
    error_count = 0
    agents_health = {}
    
    for agent_id, data in state.items():
        status = data.get("status", "idle")
        if status == "error":
            error_count += 1
        
        agents_health[agent_id] = {
            "status": status,
            "name": data.get("name", agent_id),
            "model": data.get("model", ""),
            "version": "v1",  # Будет обновлено из agent_memory
            "consecutive_fails": 0,  # Будет обновлено из agent_memory
        }
    
    error_pct = (error_count / total * 100) if total > 0 else 0
    
    # Определяем статус студии
    if error_pct >= 50:
        studio_status = "critical"
        alert_message = f"СТУДИЯ НА ПАУЗЕ: {error_count}/{total} агентов в error ({error_pct:.0f}%)"
    elif error_pct >= 25:
        studio_status = "warning"
        alert_message = f"ВНИМАНИЕ: {error_count}/{total} агентов в error ({error_pct:.0f}%)"
    else:
        studio_status = "ok"
        alert_message = ""
    
    # Сохраняем статус студии
    tasks["studio_status"] = studio_status
    _save_tasks(tasks)
    
    return {
        "status": studio_status,
        "total_agents": total,
        "error_agents": error_count,
        "error_percentage": round(error_pct, 1),
        "agents_health": agents_health,
        "alert_message": alert_message,
    }


def set_agent_error(agent_id: str):
    """Установить статус агента в error."""
    state = _load_agents_state()
    if agent_id in state:
        state[agent_id]["status"] = "error"
        with open(AGENTS_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)


def reset_agent_error(agent_id: str):
    """Сбросить статус агента из error в idle."""
    state = _load_agents_state()
    if agent_id in state:
        state[agent_id]["status"] = "idle"
        with open(AGENTS_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
