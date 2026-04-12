"""Med Otdel agent memory and evolution endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud

router = APIRouter()


@router.get("/{agent_id}/memory")
async def get_agent_memory(agent_id: str, db: AsyncSession = Depends(get_session)):
    """Get agent memory."""
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
    """Manual agent evolution."""
    from med_otdel.med_core import manual_evolve
    result = await manual_evolve(agent_id)
    return result


@router.get("/{agent_id}/versions")
async def get_agent_versions(agent_id: str, db: AsyncSession = Depends(get_session)):
    """Get agent prompt version history."""
    from med_otdel.agent_memory import AgentMemory
    memory = AgentMemory(agent_id)
    return {
        "agent_id": agent_id,
        "current_version": memory.data.get("current_version", "v1"),
        "history": memory.data.get("history", {}),
    }


@router.post("/{agent_id}/reset-error")
async def reset_error(agent_id: str, db: AsyncSession = Depends(get_session)):
    """Reset agent error status."""
    from med_otdel.studio_monitor import reset_agent_error
    reset_agent_error(agent_id)
    return {"ok": True, "agent_id": agent_id}
