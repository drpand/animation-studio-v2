"""
HR Init API — API инициализации проекта.
Префикс роутов задаётся в main.py: /api/hr/init
"""
import os
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from med_otdel.meta_critic import (
    initialize_project,
    approve_and_apply,
    _load_constitution,
)

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT_STATE_FILE = os.path.join(PROJECT_ROOT, "memory", "init_state.json")


class InitStartRequest(BaseModel):
    project_description: str = ""


class ApproveRequest(BaseModel):
    approvals: dict  # {writer: "candidate_id", director: "candidate_id", ...}
    project_description: str = ""


@router.post("/start")
async def start_init(req: InitStartRequest):
    """Начать инициализацию: оценить всех кандидатов."""
    result = await initialize_project(req.project_description)
    return result


@router.get("/candidates")
async def get_candidates():
    """Получить всех кандидатов с оценками Meta-Critic."""
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
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "source": c.get("source", ""),
                        "score": c.get("meta_critic_evaluation", {}).get("total", 0),
                        "max_score": c.get("meta_critic_evaluation", {}).get("max_total", 40),
                        "feedback": c.get("meta_critic_evaluation", {}).get("feedback", ""),
                    }
                    for c in data.get("candidates", [])
                ],
            }

    return {
        "criteria": {
            k: {"label": v["label"], "description": v["description"], "max_score": v["max_score"]}
            for k, v in EVALUATION_CRITERIA.items()
        },
        "roles": all_candidates,
    }


@router.post("/approve")
async def approve_candidates(req: ApproveRequest):
    """Утвердить промпты и применить к агентам."""
    result = await approve_and_apply(req.approvals, req.project_description)
    return result


@router.get("/status")
async def init_status():
    """Статус инициализации."""
    if os.path.exists(INIT_STATE_FILE):
        with open(INIT_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"status": "not_started"}


@router.get("/constitution")
async def get_constitution():
    """Получить текст конституции."""
    return {"constitution": _load_constitution()}
