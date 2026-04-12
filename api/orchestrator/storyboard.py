"""Storyboard and scene management endpoints."""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from api.orchestrator.helpers import extract_edit_hints, extract_prompt_parts

router = APIRouter()


@router.get("/storyboard/frames")
async def get_storyboard_frames(db: AsyncSession = Depends(get_session)):
    """Получить ВСЕ кадры storyboard для текущего проекта."""
    frames = await crud.get_all_scene_frames(db)
    return {"frames": [{
        "id": f.id, "season_num": f.season_num, "episode_num": f.episode_num,
        "scene_num": f.scene_num, "frame_num": f.frame_num,
        "status": f.status, "final_prompt": f.final_prompt or "",
        "image_url": f.image_url or "", "writer_text": f.writer_text or "",
        "director_notes": f.director_notes or "",
        "characters_json": f.characters_json or "",
        "dop_prompt": f.dop_prompt or "",
        "art_prompt": f.art_prompt or "",
        "sound_prompt": f.sound_prompt or "",
        "prompt_parts_json": f.prompt_parts_json or "",
        "prompt_parts": extract_prompt_parts(f.prompt_parts_json or ""),
        "critic_feedback": f.critic_feedback or "",
        "cv_score": f.cv_score or 0,
        "cv_description": f.cv_description or "",
        "cv_details": f.cv_details or "",
        "consistency_score": f.consistency_score or 0,
        "consistency_issues": f.consistency_issues or "",
        # Editable hints for UI (stored in user_comment as JSON envelope when available)
        "edit_hints": extract_edit_hints(f.user_comment or ""),
    } for f in frames]}


@router.get("/scene-result/{season}/{episode}/{scene}")
async def get_scene_result(season: int, episode: int, scene: int, db: AsyncSession = Depends(get_session)):
    """Получить результат конвейера сцены."""
    frames = await crud.get_scene_frames(db, season, episode, scene)
    if frames:
        frame = frames[0]
        return {
            "status": frame.status,
            "final_prompt": frame.final_prompt or "",
            "image_url": frame.image_url or "",
            "writer_text": frame.writer_text or "",
            "director_notes": frame.director_notes or "",
            "characters_json": frame.characters_json or "",
            "dop_prompt": frame.dop_prompt or "",
            "art_prompt": frame.art_prompt or "",
            "sound_prompt": frame.sound_prompt or "",
            "critic_feedback": frame.critic_feedback or "",
            "user_status": frame.user_status or "pending",
            "user_comment": frame.user_comment or "",
        }
    return {"status": "not_found"}


@router.post("/scene-action/{season}/{episode}/{scene}")
async def scene_action(season: int, episode: int, scene: int, action: dict, db: AsyncSession = Depends(get_session)):
    """Утвердить сцену или отправить на доработку."""
    frames = await crud.get_scene_frames(db, season, episode, scene)
    if frames:
        frame = frames[0]
        action_type = action.get("action")
        comment = action.get("comment", "")
        
        if action_type == "approve":
            frame.user_status = "approved"
            frame.user_comment = comment
        elif action_type == "revise":
            frame.user_status = "revision"
            frame.user_comment = comment
        
        await db.commit()
        return {"ok": True, "status": frame.user_status}
    return {"ok": False, "error": "Scene not found"}


@router.post("/revise-frame/{frame_id}")
async def revise_frame(frame_id: int, action: dict, db: AsyncSession = Depends(get_session)):
    """
    Доработка кадра: пользователь пишет что изменить → Art Director переписывает промпт → Kie.ai генерирует.
    action: {"comment": "что изменить", "edited_prompt": "отредактированный промпт (опционально)"}
    """
    frames = await crud.get_all_scene_frames(db)
    frame = next((f for f in frames if f.id == frame_id), None)
    if not frame:
        return {"ok": False, "error": "Кадр не найден"}

    user_comment = action.get("comment", "")
    edited_prompt = action.get("edited_prompt", "")

    # Если пользователь сам отредактировал промпт — используем его
    if edited_prompt.strip():
        new_prompt = edited_prompt.strip()
    else:
        # Иначе просим Art Director переписать промпт с учётом комментария
        from med_otdel.agent_memory import call_llm
        current_prompt = frame.final_prompt or ""
        system = "Ты арт-директор 2.5D аниме-студии. Перепиши промпт для Kie.ai Z-Image с учётом правок."
        user = f"""Оригинальный промпт:
{current_prompt[:2000]}

Правка от пользователя: {user_comment}

Перепиши промпт чтобы учесть правку. Сохрани стиль 2.5D аниме, кинематографичность.
Верни ТОЛЬКО новый промпт, без пояснений."""

        try:
            new_prompt, _ = await call_llm(system_prompt=system, user_prompt=user)
            new_prompt = new_prompt.strip()[:800]
        except Exception as e:
            new_prompt = current_prompt  # fallback

    # Генерация через Kie.ai
    from tools.kieai_tool import generate_image
    result = await generate_image(prompt=new_prompt[:4000], width=1024, height=576)

    if result.status != "success":
        return {"ok": False, "error": f"Kie.ai ошибка: {result.error}"}

    # Обновляем кадр
    frame.final_prompt = new_prompt[:8000]
    frame.image_url = result.result_url
    frame.user_status = "in_review"
    frame.user_comment = user_comment
    frame.status = "approved"

    await db.commit()

    return {
        "ok": True,
        "image_url": result.result_url,
        "new_prompt": new_prompt[:500],
        "message": "Кадр перегенерирован"
    }


@router.patch("/scene-frame/{season}/{episode}/{scene}")
async def patch_scene_frame(season: int, episode: int, scene: int, updates: dict, db: AsyncSession = Depends(get_session)):
    """Обновить поля кадра сцены (location, prompt, image_url и т.д.)."""
    frames = await crud.get_scene_frames(db, season, episode, scene)
    if not frames:
        return {"ok": False, "error": "Scene not found"}
    
    frame = frames[0]
    allowed_fields = {
        "writer_text", "director_notes", "characters_json",
        "dop_prompt", "art_prompt", "sound_prompt",
        "prompt_parts_json",
        "final_prompt", "image_url", "critic_feedback",
        "status", "user_status", "user_comment",
    }
    
    for field, value in updates.items():
        if field in allowed_fields and hasattr(frame, field):
            setattr(frame, field, value)
    
    await db.commit()
    return {"ok": True, "message": f"Frame {season}x{episode}:{scene} updated"}
