"""
Med Otdel API — API МЕД-ОТДЕЛА.
Префикс роутов задаётся в main.py: /api/med-otdel
"""
import os
import json

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from models import EvaluateRequest, FixRequest, PatternRequest

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@router.post("/evaluate")
async def evaluate(req: EvaluateRequest, db: AsyncSession = Depends(get_session)):
    """Critic оценивает последний ответ агента."""
    agent = await crud.get_agent(db, req.agent_id)
    if not agent:
        raise HTTPException(404, f"Агент '{req.agent_id}' не найден")

    messages = await crud.get_messages(db, req.agent_id)
    last_result = ""
    for msg in reversed(messages):
        if msg.role == "assistant":
            last_result = msg.content
            break

    if not last_result:
        raise HTTPException(400, "Нет результатов для оценки.")

    from med_otdel.med_core import run_evaluation
    try:
        result = await run_evaluation(
            task_result=last_result, agent_id=req.agent_id, task_description=req.task_description
        )
    except Exception as e:
        import logging
        logging.error(f"Evaluation error: {e}")
        result = {
            "passed": False,
            "score": 0,
            "feedback": f"Ошибка оценки: {str(e)[:500]}",
            "task_id": "",
            "raw_response": "",
            "fixed_result": None,
        }

    # Если Fixer исправил результат — сохраняем в историю агента
    if result.get("fixed_result"):
        try:
            import crud as crud_mod
            from datetime import datetime
            await crud_mod.add_message(db, req.agent_id, "assistant",
                f"[ИСПРАВЛЕНО FIXER'ом]\n\n{result['fixed_result'][:4000]}",
                datetime.now().isoformat())
        except Exception:
            pass

    return result


@router.post("/fix")
async def fix(req: FixRequest, db: AsyncSession = Depends(get_session)):
    """Fixer исправляет результат."""
    from med_otdel.med_core import run_fix
    fixed_result = await run_fix(req.original_result, req.critic_feedback)
    return {"fixed_result": fixed_result}


@router.get("/{agent_id}/memory")
async def get_agent_memory(agent_id: str, db: AsyncSession = Depends(get_session)):
    """Получить память агента."""
    from med_otdel.agent_memory import AgentMemory
    memory = AgentMemory(agent_id)
    return {
        "agent_id": agent_id,
        "current_version": memory.data.get("current_version", "v1"),
        "current_prompt": memory.data.get("current_prompt", ""),
        "total_failures": memory.data.get("total_failures", 0),
        "consecutive_failures": memory.get_consecutive_failures(),
        "failures": memory.data.get("failures", [])[-10:],
        "lessons": memory.data.get("lessons", [])[-5:],
        "history_versions": list(memory.data.get("history", {}).keys()),
    }


@router.post("/{agent_id}/evolve")
async def evolve_agent(agent_id: str, db: AsyncSession = Depends(get_session)):
    """Ручная эволюция агента."""
    from med_otdel.med_core import manual_evolve
    result = await manual_evolve(agent_id)
    return result


@router.get("/{agent_id}/versions")
async def get_agent_versions(agent_id: str, db: AsyncSession = Depends(get_session)):
    """Получить историю версий промптов."""
    from med_otdel.agent_memory import AgentMemory
    memory = AgentMemory(agent_id)
    return {
        "agent_id": agent_id,
        "current_version": memory.data.get("current_version", "v1"),
        "history": memory.data.get("history", {}),
    }


@router.get("/studio-health")
async def studio_health(db: AsyncSession = Depends(get_session)):
    """Здоровье всей студии."""
    from med_otdel.studio_monitor import check_studio_health
    return check_studio_health()


@router.get("/chains")
async def get_chains(db: AsyncSession = Depends(get_session)):
    """Проблемные цепочки."""
    from med_otdel.chain_analyzer import analyze_chains
    return {"chains": analyze_chains()}


@router.get("/events")
async def get_events(limit: int = 20, db: AsyncSession = Depends(get_session)):
    """Последние события."""
    events = await crud.get_events(db, limit)
    return {"events": [
        {"id": e.id, "task_id": e.task_id, "agent_id": e.agent_id, "event_type": e.event_type,
         "status": e.status, "timestamp": e.timestamp}
        for e in reversed(events)
    ]}


@router.get("/log")
async def get_med_log(limit: int = 20, db: AsyncSession = Depends(get_session)):
    """Лог МЕД-ОТДЕЛА."""
    logs = await crud.get_med_logs(db, limit)
    entries = [
        {"action": l.action, "details": l.details, "agent_id": l.agent_id, "timestamp": l.timestamp}
        for l in reversed(logs)
    ]

    # Fallback: если в БД пусто, читаем file-based med_log.json
    if not entries:
        med_file = os.path.join(PROJECT_ROOT, "memory", "med_log.json")
        try:
            if os.path.exists(med_file):
                with open(med_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                file_entries = data.get("entries", [])
                entries = list(reversed(file_entries[-limit:]))
        except Exception:
            pass

    return {"entries": entries}


@router.post("/{agent_id}/reset-error")
async def reset_error(agent_id: str, db: AsyncSession = Depends(get_session)):
    """Сбросить статус error."""
    from med_otdel.studio_monitor import reset_agent_error
    reset_agent_error(agent_id)
    return {"ok": True, "agent_id": agent_id}


@router.get("/patterns")
async def list_patterns(db: AsyncSession = Depends(get_session)):
    """Список доступных паттернов."""
    from med_otdel.rule_builder import get_available_patterns
    return {"patterns": get_available_patterns()}


@router.post("/apply-pattern")
async def apply_pattern_endpoint(req: PatternRequest, db: AsyncSession = Depends(get_session)):
    """Применить паттерн к агенту."""
    from med_otdel.rule_builder import apply_pattern
    result = apply_pattern(req.agent_id, req.pattern_key)
    if result.get("ok"):
        await crud.add_rule(db, req.agent_id, req.pattern_key)
        await crud.add_discussion(db, {
            "agent_id": "med_otdel", "content": f"[RULE_APPLIED] {req.pattern_key} -> {req.agent_id}",
            "msg_type": "med_otdel", "timestamp": __import__('datetime').datetime.now().isoformat(),
        })
    return result


@router.post("/remove-pattern")
async def remove_pattern_endpoint(req: PatternRequest, db: AsyncSession = Depends(get_session)):
    """Удалить паттерн."""
    from med_otdel.rule_builder import remove_pattern
    result = remove_pattern(req.agent_id, req.pattern_key)
    if result.get("ok"):
        await crud.remove_rule(db, req.agent_id, req.pattern_key)
    return result


@router.get("/{agent_id}/rules")
async def get_agent_rules(agent_id: str, db: AsyncSession = Depends(get_session)):
    """Получить правила агента."""
    rules = await crud.get_rules(db, agent_id)
    return {"agent_id": agent_id, "rules": [r.pattern_key for r in rules]}
