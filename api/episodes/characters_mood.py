"""Characters, mood board, and decisions endpoints."""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from models import CharacterCreate, MoodItemCreate, DecisionCreate
from api.episodes.helpers import (
    get_active_project_id,
    get_active_project,
    now_iso,
)

router = APIRouter()


@router.get("/characters")
async def get_characters(db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        return {"characters": []}
    characters = await crud.get_characters(db, project.id)
    return {"characters": [
        {"id": c.id, "name": c.name, "description": c.description, "voice_id": c.voice_id, "relations": c.relations}
        for c in characters
    ]}


@router.post("/character")
async def create_character(req: CharacterCreate, db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    now = now_iso()
    char = await crud.create_character(db, project.id, {
        "name": req.name, "description": req.description,
        "voice_id": req.voice_id, "relations": req.relations, "created_at": now,
    })
    return {"ok": True, "character": {"id": char.id, "name": char.name}}


@router.delete("/character/{char_id}")
async def delete_character(char_id: int, db: AsyncSession = Depends(get_session)):
    await crud.delete_character(db, char_id)
    return {"ok": True}


@router.get("/mood-board")
async def get_mood_board(db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        return {"mood_board": []}
    items = await crud.get_mood_board(db, project.id)
    return {"mood_board": [{"id": m.id, "url": m.url, "description": m.description, "tags": m.tags} for m in items]}


@router.post("/mood-board")
async def add_mood_item(req: MoodItemCreate, db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    item = await crud.add_mood_item(db, project.id, {
        "url": req.url, "description": req.description, "tags": req.tags,
        "created_at": now_iso(),
    })
    return {"ok": True, "item": {"id": item.id, "url": item.url}}


@router.delete("/mood-board/{item_id}")
async def delete_mood_item(item_id: int, db: AsyncSession = Depends(get_session)):
    await crud.delete_mood_item(db, item_id)
    return {"ok": True}


@router.get("/decisions")
async def get_decisions(db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        return {"decisions": []}
    decisions = await crud.get_decisions(db, project.id)
    return {"decisions": [
        {"id": d.id, "title": d.title, "description": d.description, "agent_id": d.agent_id, "created_at": d.created_at}
        for d in decisions
    ]}


@router.post("/decision")
async def create_decision(req: DecisionCreate, db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    dec = await crud.create_decision(db, project.id, {
        "title": req.title, "description": req.description, "agent_id": req.agent_id,
        "created_at": now_iso(),
    })
    return {"ok": True, "decision": {"id": dec.id, "title": dec.title}}
