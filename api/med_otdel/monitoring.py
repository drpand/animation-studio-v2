"""Med Otdel monitoring and diagnostics endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from models import PatternRequest
from api.med_otdel.helpers import read_med_log_file

router = APIRouter()


@router.get("/studio-health")
async def studio_health(db: AsyncSession = Depends(get_session)):
    """Get studio health status."""
    from med_otdel.studio_monitor import check_studio_health
    return check_studio_health()


@router.get("/chains")
async def get_chains(db: AsyncSession = Depends(get_session)):
    """Get problematic chains."""
    from med_otdel.chain_analyzer import analyze_chains
    return {"chains": analyze_chains()}


@router.get("/events")
async def get_events(limit: int = 20, db: AsyncSession = Depends(get_session)):
    """Get recent events."""
    events = await crud.get_events(db, limit)
    return {"events": [
        {"id": e.id, "task_id": e.task_id, "agent_id": e.agent_id, "event_type": e.event_type,
         "status": e.status, "timestamp": e.timestamp}
        for e in reversed(events)
    ]}


@router.get("/log")
async def get_med_log(limit: int = 20, db: AsyncSession = Depends(get_session)):
    """Get med_otdel log."""
    logs = await crud.get_med_logs(db, limit)
    entries = [
        {"action": l.action, "details": l.details, "agent_id": l.agent_id, "timestamp": l.timestamp}
        for l in reversed(logs)
    ]

    # Fallback: if DB is empty, read file-based med_log.json
    if not entries:
        entries = read_med_log_file(limit)

    return {"entries": entries}


@router.get("/patterns")
async def list_patterns(db: AsyncSession = Depends(get_session)):
    """List available patterns."""
    from med_otdel.rule_builder import get_available_patterns
    return {"patterns": get_available_patterns()}


@router.post("/apply-pattern")
async def apply_pattern_endpoint(req: PatternRequest, db: AsyncSession = Depends(get_session)):
    """Apply pattern to agent."""
    from med_otdel.rule_builder import apply_pattern
    from datetime import datetime
    result = apply_pattern(req.agent_id, req.pattern_key)
    if result.get("ok"):
        await crud.add_rule(db, req.agent_id, req.pattern_key)
        await crud.add_discussion(db, {
            "agent_id": "med_otdel", "content": f"[RULE_APPLIED] {req.pattern_key} -> {req.agent_id}",
            "msg_type": "med_otdel", "timestamp": datetime.now().isoformat(),
        })
    return result


@router.post("/remove-pattern")
async def remove_pattern_endpoint(req: PatternRequest, db: AsyncSession = Depends(get_session)):
    """Remove pattern from agent."""
    from med_otdel.rule_builder import remove_pattern
    result = remove_pattern(req.agent_id, req.pattern_key)
    if result.get("ok"):
        await crud.remove_rule(db, req.agent_id, req.pattern_key)
    return result


@router.get("/{agent_id}/rules")
async def get_agent_rules(agent_id: str, db: AsyncSession = Depends(get_session)):
    """Get agent rules."""
    rules = await crud.get_rules(db, agent_id)
    return {"agent_id": agent_id, "rules": [r.pattern_key for r in rules]}
