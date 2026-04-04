"""
HR Init API — API инициализации проекта.
Префикс роутов задаётся в main.py: /api/hr/init
"""
import os
import json
import tempfile
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT_STATE_FILE = os.path.join(PROJECT_ROOT, "memory", "init_state.json")


class InitStartRequest(BaseModel):
    project_description: str = ""


class ApproveRequest(BaseModel):
    approvals: dict
    project_description: str = ""


@router.post("/start")
async def start_init(req: InitStartRequest, db: AsyncSession = Depends(get_session)):
    """Начать инициализацию."""
    from med_otdel.meta_critic import initialize_project
    result = await initialize_project(req.project_description)
    return result


@router.get("/candidates")
async def get_candidates(db: AsyncSession = Depends(get_session)):
    """Получить кандидатов с оценками."""
    from med_otdel.meta_critic import CANDIDATES_DIR, EVALUATION_CRITERIA
    roles = ["writer", "director", "dop", "critic", "sound_director"]
    all_candidates = {}
    for role in roles:
        candidates_file = os.path.join(CANDIDATES_DIR, f"{role}.json")
        if os.path.exists(candidates_file):
            with open(candidates_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            all_candidates[role] = {
                "candidates": data.get("candidates", []),
                "evaluations": [
                    {
                        "id": c.get("id"), "name": c.get("name"), "source": c.get("source", ""),
                        "score": c.get("meta_critic_evaluation", {}).get("total", 0),
                        "max_score": c.get("meta_critic_evaluation", {}).get("max_total", 40),
                        "feedback": c.get("meta_critic_evaluation", {}).get("feedback", ""),
                    }
                    for c in data.get("candidates", [])
                ],
            }
    return {
        "criteria": {k: {"label": v["label"], "description": v["description"], "max_score": v["max_score"]}
                     for k, v in EVALUATION_CRITERIA.items()},
        "roles": all_candidates,
    }


@router.post("/approve")
async def approve_candidates(req: ApproveRequest, db: AsyncSession = Depends(get_session)):
    """Утвердить промпты."""
    from med_otdel.meta_critic import approve_and_apply
    result = await approve_and_apply(req.approvals, req.project_description)
    return result


@router.get("/status")
async def init_status(db: AsyncSession = Depends(get_session)):
    """Статус инициализации."""
    state = await crud.get_init_state(db)
    if state:
        return {"status": state.status, "project_description": state.project_description, "initialized_at": state.initialized_at}
    return {"status": "not_started"}


@router.get("/constitution")
async def get_constitution(db: AsyncSession = Depends(get_session)):
    """Получить конституцию."""
    from agents.base_agent import _load_constitution
    return {"constitution": _load_constitution()}
