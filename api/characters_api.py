"""
Characters API — CRUD персонажей.
Префикс роутов задаётся в main.py: /api/characters
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List

from database import get_session
import crud

router = APIRouter()


class CharacterCreate(BaseModel):
    name: str
    age: int = 0
    appearance: str = ""
    clothing: str = ""
    speech: str = ""
    voice_id: str = ""
    relations: str = ""


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    appearance: Optional[str] = None
    clothing: Optional[str] = None
    speech: Optional[str] = None
    voice_id: Optional[str] = None
    relations: Optional[str] = None


@router.get("/")
async def get_characters(db: AsyncSession = Depends(get_session)):
    """Получить всех персонажей."""
    # Get from project_id=1 (default)
    characters = await crud.get_characters(db, 1)
    return {
        "characters": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "voice_id": c.voice_id,
                "relations": c.relations,
                "created_at": c.created_at,
            }
            for c in characters
        ]
    }


@router.post("/")
async def create_character(req: CharacterCreate, db: AsyncSession = Depends(get_session)):
    """Создать персонажа."""
    description = f"Возраст: {req.age}. Внешность: {req.appearance}. Одежда: {req.clothing}. Манера речи: {req.speech}"
    char = await crud.create_character(db, 1, {
        "name": req.name,
        "description": description,
        "voice_id": req.voice_id,
        "relations": req.relations,
        "created_at": __import__('datetime').datetime.now().isoformat(),
    })
    return {
        "ok": True,
        "character": {
            "id": char.id,
            "name": char.name,
            "description": char.description,
        }
    }


@router.put("/{char_id}")
async def update_character(char_id: int, update: CharacterUpdate, db: AsyncSession = Depends(get_session)):
    """Обновить персонажа."""
    from database import Character
    result = await db.execute(
        __import__('sqlalchemy').select(Character).where(Character.id == char_id)
    )
    char = result.scalars().first()
    if not char:
        raise HTTPException(404, f"Персонаж '{char_id}' не найден")

    data = {k: v for k, v in update.model_dump().items() if v is not None}
    if "appearance" in data or "clothing" in data or "speech" in data or "age" in data:
        # Rebuild description
        desc_parts = []
        if update.age is not None:
            desc_parts.append(f"Возраст: {update.age}")
        if update.appearance:
            desc_parts.append(f"Внешность: {update.appearance}")
        if update.clothing:
            desc_parts.append(f"Одежда: {update.clothing}")
        if update.speech:
            desc_parts.append(f"Манера речи: {update.speech}")
        if desc_parts:
            char.description = ". ".join(desc_parts)

    if update.name:
        char.name = update.name
    if update.voice_id:
        char.voice_id = update.voice_id
    if update.relations:
        char.relations = update.relations

    await db.commit()
    await db.refresh(char)
    return {"ok": True, "character": {"id": char.id, "name": char.name}}


@router.delete("/{char_id}")
async def delete_character(char_id: int, db: AsyncSession = Depends(get_session)):
    """Удалить персонажа."""
    await crud.delete_character(db, char_id)
    return {"ok": True}
