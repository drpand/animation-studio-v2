"""
CV Check API — проверка сгенерированного изображения через OpenRouter Vision.
Сравнивает изображение с описанием сцены через компьютерное зрение.
Префикс роутов задаётся в main.py: /api/tools
"""
import os
import json
import base64
import httpx
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from config import OPENROUTER_API_KEY, PROJECT_ROOT_CONFIG

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Модели OpenRouter с поддержкой vision
VISION_MODELS = [
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4.5",
    "google/gemini-2.5-flash",
]


class CVCheckRequest(BaseModel):
    frame_id: int
    model: str = "openai/gpt-4o"


async def _image_to_base64(image_url: str) -> str:
    """Загрузить изображение по URL и конвертировать в base64."""
    # Если локальный путь
    if image_url.startswith("/tools_cache/"):
        filename = os.path.basename(image_url)
        local_path = os.path.join(PROJECT_ROOT, "memory", "tools_cache", "images", filename)
        if os.path.exists(local_path):
            with open(local_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        return ""

    # Если внешний URL
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(image_url)
            if resp.status_code == 200:
                return base64.b64encode(resp.content).decode("utf-8")
    except Exception:
        pass
    return ""


@router.post("/cv-check")
async def cv_check(req: CVCheckRequest, db: AsyncSession = Depends(get_session)):
    """
    Проверить соответствие изображения описанию сцены через OpenRouter Vision API.
    Возвращает оценку 0-10, описание что видит модель, и что совпало/не совпало.
    """
    if not OPENROUTER_API_KEY:
        raise HTTPException(400, "OPENROUTER_API_KEY не настроен")

    # Находим кадр
    frames = await crud.get_all_scene_frames(db)
    frame = next((f for f in frames if f.id == req.frame_id), None)
    if not frame:
        raise HTTPException(404, f"Кадр {req.frame_id} не найден")

    if not frame.image_url:
        return {"ok": False, "error": "Нет изображения для проверки"}

    writer_text = frame.writer_text or frame.final_prompt or ""
    if not writer_text:
        return {"ok": False, "error": "Нет описания сцены для сравнения"}

    # Конвертируем изображение в base64
    image_b64 = await _image_to_base64(frame.image_url)
    if not image_b64:
        return {"ok": False, "error": "Не удалось загрузить изображение"}

    # Промпт для CV проверки
    system_prompt = """Ты эксперт по компьютерному зрению и аниме-производству.
Твоя задача — описать что ты видишь на изображении и сравнить с описанием сцены.

Верни СТРОГО JSON:
{
  "description": "Подробное описание что ты видишь на изображении (2-3 предложения)",
  "score": 8,
  "matched": ["элемент1", "элемент2"],
  "missing": ["элемент3", "элемент4"],
  "verdict": "Изображение соответствует описанию сцены" или "Изображение НЕ соответствует описанию"
}"""

    user_prompt = f"""Опиши что ты видишь на этом изображении и сравни с описанием сцены.

Описание сцены:
{writer_text[:2000]}

Оцени соответствие по шкале 0-10.
Укажи какие элементы совпали и какие отсутствуют."""

    # Отправляем в OpenRouter
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:7860",
                    "X-Title": "Animation Studio v2 — CV Check",
                },
                json={
                    "model": req.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{image_b64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "max_tokens": 1000,
                }
            )

            if resp.status_code != 200:
                error_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = error_data.get("error", {}).get("message", resp.text[:200])
                return {"ok": False, "error": f"OpenRouter ошибка: {error_msg}"}

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Извлекаем JSON из ответа
        cv_result = _extract_json(content)
        if not cv_result:
            cv_result = {
                "description": content[:500],
                "score": 5,
                "matched": [],
                "missing": [],
                "verdict": "Не удалось распознать ответ",
            }

        score = cv_result.get("score", 5)
        description = cv_result.get("description", "")
        matched = cv_result.get("matched", [])
        missing = cv_result.get("missing", [])
        verdict = cv_result.get("verdict", "")

        # Сохраняем результат в кадр
        frame.cv_score = score
        frame.cv_description = description
        frame.cv_details = json.dumps({
            "matched": matched,
            "missing": missing,
            "verdict": verdict,
            "model": req.model,
        }, ensure_ascii=False)

        await db.commit()

        return {
            "ok": True,
            "score": score,
            "description": description,
            "matched": matched,
            "missing": missing,
            "verdict": verdict,
            "model": req.model,
        }

    except httpx.TimeoutException:
        return {"ok": False, "error": "Таймаут запроса к OpenRouter"}
    except Exception as e:
        return {"ok": False, "error": f"Ошибка CV проверки: {str(e)[:200]}"}


def _extract_json(text: str) -> dict:
    """Извлечь JSON из ответа LLM."""
    import re
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return {}
    return {}
