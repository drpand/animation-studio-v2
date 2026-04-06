"""
CV Check API — проверка сгенерированного изображения через OpenRouter Vision.
"""
import os
import json
import base64
import httpx
import sys
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from config import OPENROUTER_API_KEY, PROJECT_ROOT_CONFIG
from utils.logger import info, error

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
    model: str = "google/gemini-3.1-flash-lite-preview"


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

    # Очищаем writer_text от Unicode спецсимволов
    writer_text = writer_text.replace("\u2014", "-").replace("\u2013", "-").replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')

    # Конвертируем изображение в base64 data URL для OpenRouter
    image_b64 = await _image_to_base64(frame.image_url)
    if not image_b64:
        return {"ok": False, "error": "Не удалось загрузить изображение"}

    image_data_url = f"data:image/png;base64,{image_b64}"

    # Промпт для CV проверки
    system_prompt = """You are a computer vision expert and anime production specialist.
Describe what you see in the image and compare it with the scene description.

Return STRICTLY JSON:
{
  "description": "Detailed description of what you see (2-3 sentences)",
  "score": 8,
  "matched": ["element1", "element2"],
  "missing": ["element3", "element4"],
  "verdict": "Image matches scene description" or "Image does not match"
}"""

    user_prompt = f"""Describe what you see in this image and compare with the scene description.

Scene description:
{writer_text[:2000]}

Rate match from 0-10.
List matched and missing elements."""

    # Отправляем в OpenRouter
    try:
        info(f"[CV] Sending to OpenRouter, model={req.model}, image_b64_len={len(image_b64)}")

        request_body = json.dumps({
            "model": req.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url}}
                    ]
                }
            ],
            "max_tokens": 1000,
        }, ensure_ascii=True)

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:7860",
                    "X-Title": "Animation Studio v2 - CV Check",
                },
                content=request_body.encode("utf-8"),
            )

            if resp.status_code != 200:
                error_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = error_data.get("error", {}).get("message", resp.text[:200])
                return {"ok": False, "error": f"OpenRouter ошибка: {error_msg}"}

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"[CV] Got response, content len={len(content)}", file=sys.stderr)

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

        print(f"[CV] Parsed: score={cv_result.get('score')}, desc_len={len(str(cv_result.get('description','')))}", file=sys.stderr)

        score = cv_result.get("score", 5)
        # Полная ASCII очистка — заменяем все non-ASCII
        def _to_ascii(s):
            if not s:
                return ""
            return str(s).encode("ascii", errors="replace").decode("ascii")

        description = _to_ascii(cv_result.get("description", ""))
        matched = [_to_ascii(m) for m in cv_result.get("matched", [])]
        missing = [_to_ascii(m) for m in cv_result.get("missing", [])]
        verdict = _to_ascii(cv_result.get("verdict", ""))

        # Сохраняем результат в кадр
        frame.cv_score = score
        frame.cv_description = description
        frame.cv_details = json.dumps({
            "matched": matched,
            "missing": missing,
            "verdict": verdict,
            "model": req.model,
        }, ensure_ascii=False)

        print(f"[CV] Before commit: desc={description[:100]!r}", file=sys.stderr)

        await db.commit()
        print(f"[CV] Commit successful", file=sys.stderr)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        # Логируем полную ошибку
        error_str = str(e).encode("ascii", errors="replace").decode("ascii")
        info(f"CV CHECK ERROR: {error_str}")
        info(tb)
        # Попробуем определить где именно ошибка
        return {"ok": False, "error": f"CV error: {error_str}"}

    return {
        "ok": True,
        "score": score,
        "description": description,
        "matched": matched,
        "missing": missing,
        "verdict": verdict,
        "model": req.model,
    }


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


# ============================================
# CV AUTO-FIX: CV → Critic → Fixer → Kie.ai цикл
# ============================================

async def _call_llm(system_prompt: str, user_prompt: str, model: str = "google/gemini-3.1-flash-preview") -> str:
    """Вызвать LLM через OpenRouter."""
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 2000,
    }, ensure_ascii=True)

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:7860",
                "X-Title": "Animation Studio v2 - AutoFix",
            },
            content=body.encode("utf-8"),
        )
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")


async def _run_critic_review(writer_text: str, cv_description: str, cv_score: int, missing: list) -> str:
    """Critic анализирует CV результат и пишет что исправить."""
    system = "You are a strict art critic for anime production. Analyze image vs scene description."
    user = f"""The generated image scored {cv_score}/10 in computer vision check.

Scene description:
{writer_text[:1500]}

What the CV model saw in the image:
{cv_description[:1000]}

Missing elements according to CV:
{', '.join(missing) if missing else 'None reported'}

What specific changes should be made to the image generation prompt to improve accuracy?
Be specific about composition, elements, colors, lighting.
Return ONLY the critique, no JSON."""

    return await _call_llm(system, user)


async def _run_fixer_rewrite(original_prompt: str, writer_text: str, critic_feedback: str, cv_description: str) -> str:
    """Fixer переписывает промпт для Kie.ai на основе замечаний Critic и CV результата."""
    system = "You are an expert AI image generation prompt engineer. Rewrite prompts to be more precise."
    user = f"""Rewrite this image generation prompt to fix the issues identified by the critic.

Original prompt:
{original_prompt[:2000]}

Scene description (for context):
{writer_text[:1000]}

Critic feedback on what's wrong:
{critic_feedback[:1000]}

What CV model actually saw:
{cv_description[:500]}

Write a NEW prompt optimized for anime image generation.
Focus on: correct composition, all required elements present, proper lighting and mood.
Return ONLY the new prompt text, no explanations, no JSON."""

    return await _call_llm(system, user)


@router.post("/cv-auto-fix/{frame_id}")
async def cv_auto_fix(frame_id: int, db: AsyncSession = Depends(get_session)):
    """
    Авто-исправление кадра: CV check → если score < 8 → Critic → Fixer → Kie.ai → повтор.
    Максимум 3 цикла. Возвращает историю всех попыток.
    """
    if not OPENROUTER_API_KEY:
        raise HTTPException(400, "OPENROUTER_API_KEY not configured")

    frames = await crud.get_all_scene_frames(db)
    frame = next((f for f in frames if f.id == frame_id), None)
    if not frame:
        return {"ok": False, "error": "Frame not found"}
    if not frame.image_url or not frame.final_prompt:
        return {"ok": False, "error": "No image or prompt to fix"}

    writer_text = frame.writer_text or frame.final_prompt or ""
    history = []
    best_score = frame.cv_score or 0
    best_image_url = frame.image_url
    best_prompt = frame.final_prompt

    for attempt in range(1, 4):  # Макс 3 попытки
        info(f"[AUTO-FIX] Attempt {attempt}/3 for frame {frame_id}")

        # Шаг 1: CV check
        cv_result = await _run_cv_check(frame, writer_text, "google/gemini-3.1-flash-lite-preview")
        score = cv_result.get("score", 0)
        cv_description = cv_result.get("description", "")
        missing = cv_result.get("missing", [])

        history.append({
            "attempt": attempt,
            "cv_score": score,
            "cv_description": cv_description[:300],
            "missing": missing,
        })

        info(f"[AUTO-FIX] Attempt {attempt}: CV score={score}")

        if score >= 8:
            info(f"[AUTO-FIX] Score {score} >= 8, done!")
            frame.cv_score = score
            frame.cv_description = cv_description
            frame.cv_details = json.dumps({
                "history": history,
                "attempts": attempt,
                "final_score": score,
            }, ensure_ascii=False)
            await db.commit()
            return {"ok": True, "score": score, "attempts": attempt, "history": history}

        # Запоминаем лучший результат
        if score > best_score:
            best_score = score
            best_image_url = frame.image_url
            best_prompt = frame.final_prompt

        # Шаг 2: Critic анализирует
        info(f"[AUTO-FIX] Running critic review...")
        critic_feedback = await _run_critic_review(writer_text, cv_description, score, missing)
        info(f"[AUTO-FIX] Critic feedback: {critic_feedback[:200]}...")

        # Шаг 3: Fixer переписывает промпт
        info(f"[AUTO-FIX] Running fixer rewrite...")
        new_prompt = await _run_fixer_rewrite(
            frame.final_prompt or "", writer_text, critic_feedback, cv_description
        )
        new_prompt = new_prompt.strip()[:800]
        info(f"[AUTO-FIX] New prompt: {new_prompt[:200]}...")

        # Шаг 4: Kie.ai генерирует
        info(f"[AUTO-FIX] Generating new image via Kie.ai...")
        from tools.kieai_tool import generate_image
        result = await generate_image(prompt=new_prompt[:4000], width=1024, height=576)

        if result.status != "success":
            info(f"[AUTO-FIX] Kie.ai failed: {result.error}")
            history[-1]["kieai_error"] = result.error
            break

        # Обновляем кадр
        frame.final_prompt = new_prompt
        frame.image_url = result.result_url

    # После цикла — возвращаем лучший результат
    frame.cv_score = best_score
    frame.cv_description = f"Auto-fix completed after {len(history)} attempts. Best score: {best_score}/10"
    frame.cv_details = json.dumps({
        "history": history,
        "attempts": len(history),
        "final_score": best_score,
        "best_image_url": best_image_url,
    }, ensure_ascii=False)

    # Если лучший результат лучше текущего — откатываем
    if best_score > (frame.cv_score or 0):
        frame.image_url = best_image_url
        frame.final_prompt = best_prompt

    await db.commit()

    return {
        "ok": True,
        "final_score": best_score,
        "attempts": len(history),
        "history": history,
        "message": f"Auto-fix completed. Best score: {best_score}/10"
    }


async def _run_cv_check(frame, writer_text: str, model: str) -> dict:
    """Внутренняя CV проверка без сохранения в БД."""
    image_b64 = await _image_to_base64(frame.image_url)
    if not image_b64:
        return {"score": 0, "description": "Failed to load image", "matched": [], "missing": []}

    image_data_url = f"data:image/png;base64,{image_b64}"
    writer_text_clean = writer_text.replace("\u2014", "-").replace("\u2013", "-").replace("\u2018", "'").replace("\u2019", "'")

    system_prompt = """You are a computer vision expert. Describe what you see and compare with scene description.
Return STRICTLY JSON: {"description": "...", "score": 0-10, "matched": [...], "missing": [...]}"""

    user_prompt = f"""Describe this image and compare with scene description.
Scene: {writer_text_clean[:1500]}
Rate match 0-10. List matched and missing elements."""

    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": image_data_url}}
        ]}],
        "max_tokens": 1000,
    }, ensure_ascii=True)

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:7860",
                "X-Title": "Animation Studio v2 - CV",
            },
            content=body.encode("utf-8"),
        )
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    cv_result = _extract_json(content)
    if not cv_result:
        cv_result = {"score": 5, "description": content[:500], "matched": [], "missing": []}

    def _to_ascii(s):
        if not s: return ""
        return str(s).encode("ascii", errors="replace").decode("ascii")

    return {
        "score": cv_result.get("score", 5),
        "description": _to_ascii(cv_result.get("description", "")),
        "matched": [_to_ascii(m) for m in cv_result.get("matched", [])],
        "missing": [_to_ascii(m) for m in cv_result.get("missing", [])],
    }
