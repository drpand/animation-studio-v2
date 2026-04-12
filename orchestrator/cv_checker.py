"""
CV Checker — автоматическая проверка изображений через Gemini Vision.
Вынесено из orchestrator/executor.py для улучшения поддерживаемости.
"""
import os
import re
import json
import base64
import httpx

from config import OPENROUTER_API_KEY

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Импортируем утилиты из prompt_builder
from orchestrator.prompt_builder import _extract_json, _safe_text, _safe_text_list
from orchestrator.executor_helpers import _post_discussion


async def _load_image_as_base64(image_url: str) -> str:
    """
    Загрузить изображение и вернуть base64 строку.
    Поддерживает локальные пути /tools_cache/ и внешние URL.
    """
    image_b64 = ""
    if image_url.startswith("/tools_cache/"):
        filename = os.path.basename(image_url)
        candidate_paths = [
            os.path.join(PROJECT_ROOT, "memory", "tools_cache", "images", filename),
            os.path.join(PROJECT_ROOT, "memory", "tools_cache", filename),
        ]
        for local_path in candidate_paths:
            if os.path.exists(local_path):
                with open(local_path, "rb") as f:
                    image_b64 = base64.b64encode(f.read()).decode("utf-8")
                break
    else:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(image_url)
                if resp.status_code == 200:
                    image_b64 = base64.b64encode(resp.content).decode("utf-8")
        except Exception:
            pass
    return image_b64


async def _cv_auto_check(image_url: str, writer_text: str, final_prompt: str, task_id: str) -> dict:
    """
    Автоматическая CV проверка изображения через Gemini Vision.
    Вызывается после генерации Kie.ai.
    Если score < 8 — запускает авто-исправление (до 3 попыток).
    Возвращает: {"score": int, "description": str, "matched": [], "missing": [], "attempts": int}
    """
    CV_MODEL = "google/gemini-3.1-flash-lite-preview"
    MAX_ATTEMPTS = 3
    CV_PASS_SCORE = 8

    current_image_url = image_url
    current_prompt = final_prompt
    history = []

    for attempt in range(1, MAX_ATTEMPTS + 1):
        await _post_discussion(f"[CV-AUTO] Попытка {attempt}/{MAX_ATTEMPTS}: проверка изображения...", "system", "orchestrator")

        # Шаг 1: Загружаем изображение и конвертируем в base64
        image_b64 = await _load_image_as_base64(current_image_url)

        if not image_b64:
            await _post_discussion("[CV-AUTO] Не удалось загрузить изображение", "system", "orchestrator")
            return {"score": 0, "description": "Failed to load image", "matched": [], "missing": [], "attempts": attempt, "history": history}

        image_data_url = f"data:image/png;base64,{image_b64}"

        # Шаг 2: Отправляем в Gemini Vision
        system_prompt = """You are an expert anime art critic. Analyze images for anime production.

This is ANIME ART (2.5D), not photography. Stylization is expected.
Do NOT penalize: artistic silhouettes, symbolic reflections, exaggerated colors, non-photorealistic rendering.

Analyze the image against the scene description. Check if KEY ELEMENTS are VISIBLE (even if stylized).

Respond ONLY with valid JSON:
{"description":"what you see in English","score":7,"matched":["element1"],"missing":[],"mood":"good"}

Score: 8-10 if key elements visible and mood matches. 6-7 if mostly there. 4-5 if missing key things."""

        user_prompt = f"""Check if this anime image matches the scene description.

Scene description:
{writer_text[:1500]}

Image generation prompt:
{current_prompt[:800]}

Are the key visual elements present? Is the mood/atmosphere right?
Return JSON only."""

        body = json.dumps({
            "model": CV_MODEL,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": image_data_url}}
            ]}],
            "max_tokens": 500,
            "temperature": 0.1,
        }, ensure_ascii=True)

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:7860",
                        "X-Title": "Animation Studio v2 - Auto CV",
                    },
                    content=body.encode("utf-8"),
                )
                data = resp.json()
                raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if isinstance(raw_content, list):
                    content = "\n".join(
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in raw_content
                    )
                elif isinstance(raw_content, dict):
                    content = raw_content.get("text", "") or json.dumps(raw_content, ensure_ascii=False)
                else:
                    content = str(raw_content)
        except Exception as e:
            await _post_discussion(f"[CV-AUTO] Ошибка OpenRouter: {str(e)[:200]}", "system", "orchestrator")
            return {"score": 0, "description": f"CV API error: {str(e)[:200]}", "matched": [], "missing": [], "attempts": attempt, "history": history}

        # Парсим JSON
        cv_result = _extract_json(content)
        if not cv_result:
            cv_result = {"score": 5, "description": content[:500], "matched": [], "missing": []}

        # Базовые поля
        score = cv_result.get("score", 5)
        description = _safe_text(cv_result.get("description", ""))
        matched = _safe_text_list(cv_result.get("matched", []))
        missing = _safe_text_list(cv_result.get("missing", []))

        # Гибкий парсинг nested Gemini-структур
        analysis = cv_result.get("match_analysis", cv_result.get("analysis", {}))
        if isinstance(analysis, dict) and analysis:
            elements = analysis.get("key_visual_elements",
                      analysis.get("key_elements_present",
                      analysis.get("elements", {})))
            if isinstance(elements, dict):
                for k, v in elements.items():
                    key_clean = _safe_text(k).replace("_", " ")
                    v_text = _safe_text(v).lower()
                    if v is True or v_text.startswith("captured") or v_text.startswith("present") or v_text.startswith("yes"):
                        if key_clean and key_clean not in matched:
                            matched.append(key_clean)
                    elif v is False or v_text.startswith("missing") or v_text.startswith("absent") or v_text.startswith("no"):
                        if key_clean and key_clean not in missing:
                            missing.append(key_clean)

                if "score" not in cv_result and "overall_score" not in cv_result:
                    present = sum(1 for v in elements.values() if (v is True) or _safe_text(v).lower().startswith(("captured", "present", "yes")))
                    total = len(elements)
                    if total > 0:
                        score = min(10, max(1, int((present / total) * 10)))

        # Альтернативный score (например overall_score)
        if not isinstance(score, (int, float)):
            score = cv_result.get("overall_score", cv_result.get("score", 5))
        if isinstance(score, str):
            m = re.search(r"(\d+(?:\.\d+)?)", score)
            score = float(m.group(1)) if m else 5
        if isinstance(score, float):
            score = int(round(score))
        score = max(0, min(10, int(score)))

        if not description:
            description = _safe_text(cv_result.get("summary", cv_result.get("overall_assessment", content[:500])))

        await _post_discussion(f"[CV-AUTO] Попытка {attempt}: score={score}/10, matched={len(matched)}, missing={len(missing)}", "system", "orchestrator")

        history.append({
            "attempt": attempt,
            "cv_score": score,
            "cv_description": description[:300],
            "matched": matched,
            "missing": missing,
        })

        # Если прошли — возвращаем результат
        if score >= CV_PASS_SCORE:
            await _post_discussion(f"[CV-AUTO] ✅ PASS (score={score}/10) за {attempt} попыток", "system", "orchestrator")
            return {
                "score": score,
                "description": description,
                "matched": matched,
                "missing": missing,
                "attempts": attempt,
                "history": history,
                "image_url": current_image_url,
                "final_prompt": current_prompt,
            }

        # Если последняя попытка — возвращаем что есть
        if attempt >= MAX_ATTEMPTS:
            await _post_discussion(f"[CV-AUTO] ⚠️ MAX ATTEMPTS. Best score: {score}/10", "system", "orchestrator")
            return {
                "score": score,
                "description": description,
                "matched": matched,
                "missing": missing,
                "attempts": attempt,
                "history": history,
                "image_url": current_image_url,
                "final_prompt": current_prompt,
            }

        # Шаг 3: Critic анализирует что исправить
        await _post_discussion(f"[CV-AUTO] Запуск Critic для анализа ошибок...", "system", "orchestrator")
        critic_system = "You are a strict art critic for anime production. Analyze image vs scene description."
        critic_user = f"""The generated image scored {score}/10 in computer vision check.

Scene description:
{writer_text[:1500]}

What the CV model saw:
{description[:1000]}

Missing elements:
{', '.join(missing) if missing else 'None reported'}

What specific changes should be made to the image generation prompt to improve accuracy?
Be specific about composition, elements, colors, lighting.
Return ONLY the critique, no JSON."""

        try:
            import asyncio
            from med_otdel.agent_memory import call_llm
            critic_feedback, _ = await asyncio.wait_for(
                call_llm(system_prompt=critic_system, user_prompt=critic_user, model="deepseek/deepseek-v3.2"),
                timeout=120
            )
        except Exception as e:
            critic_feedback = f"Critic error: {str(e)[:200]}"

        # Шаг 4: Fixer переписывает промпт
        await _post_discussion(f"[CV-AUTO] Запуск Fixer для переписывания промпта...", "system", "orchestrator")
        fixer_system = "You are an expert AI image generation prompt engineer. Rewrite prompts to be more precise."
        fixer_user = f"""Rewrite this image generation prompt to fix the issues identified by the critic.

Original prompt:
{current_prompt[:2000]}

Scene description (for context):
{writer_text[:1000]}

Critic feedback on what is wrong:
{critic_feedback[:1000]}

What CV model actually saw:
{description[:500]}

Write a NEW prompt optimized for anime image generation.
Focus on: correct composition, all required elements present, proper lighting and mood.
Return ONLY the new prompt text, no explanations, no JSON."""

        try:
            import asyncio
            from med_otdel.agent_memory import call_llm
            new_prompt, _ = await asyncio.wait_for(
                call_llm(system_prompt=fixer_system, user_prompt=fixer_user, model="deepseek/deepseek-v3.2"),
                timeout=120
            )
            # Очищаем от markdown
            new_prompt = new_prompt.strip()
            if new_prompt.startswith("```"):
                lines = new_prompt.split("\n")
                new_prompt = "\n".join(lines[1:-1]) if len(lines) > 2 else new_prompt
            new_prompt = new_prompt.strip()[:800]
        except Exception as e:
            new_prompt = current_prompt

        if not new_prompt or len(new_prompt) < 20:
            new_prompt = current_prompt

        # Шаг 5: Kie.ai генерирует новое изображение
        await _post_discussion(f"[CV-AUTO] Генерация нового изображения через Kie.ai...", "system", "orchestrator")
        from tools.kieai_tool import generate_image
        gen_result = await generate_image(prompt=new_prompt[:4000], width=1024, height=576)

        if gen_result.status != "success":
            await _post_discussion(f"[CV-AUTO] Kie.ai ошибка: {gen_result.error}", "system", "orchestrator")
            history[-1]["kieai_error"] = gen_result.error
            break

        current_image_url = gen_result.result_url
        current_prompt = new_prompt

    return {
        "score": history[-1]["cv_score"] if history else 0,
        "description": history[-1]["cv_description"] if history else "",
        "matched": history[-1].get("matched", []),
        "missing": history[-1].get("missing", []),
        "attempts": len(history),
        "history": history,
        "image_url": current_image_url,
        "final_prompt": current_prompt,
    }


async def _check_character_consistency(image_url: str, characters_data: list, writer_text: str) -> dict:
    """
    Проверить консистентность персонажей на изображении.
    Сравнивает описание каждого персонажа с тем что видно на изображении.
    Возвращает: {"score": int, "issues": [], "characters_checked": int}
    """
    if not characters_data or not image_url:
        return {"score": 10, "issues": [], "characters_checked": 0}

    CV_MODEL = "google/gemini-3.1-flash-lite-preview"

    # Загружаем изображение (используем общую функцию)
    image_b64 = await _load_image_as_base64(image_url)

    if not image_b64:
        return {"score": 0, "issues": ["Failed to load image"], "characters_checked": 0}

    image_data_url = f"data:image/png;base64,{image_b64}"

    # Формируем описания персонажей
    char_descriptions = []
    for char in characters_data:
        name = char.get("name", "?")
        appearance = char.get("appearance", "")
        clothing = char.get("clothing", "")
        desc = f"- {name}: внешность={appearance}, одежда={clothing}"
        char_descriptions.append(desc)

    chars_text = "\n".join(char_descriptions)

    system_prompt = """You are a character consistency expert. Analyze if characters in the image match their descriptions.

Focus on KEY distinguishing features:
- Hair color and style
- Clothing
- Age/gender
- Unique features (glasses, scars, accessories)

Respond ONLY with valid JSON:
{"score": 8, "checks": [{"name": "character_name", "present": true, "matches": true, "issues": "description of mismatch or 'ok'"}]}

Score: 10 = all characters match perfectly. 8-9 = minor differences. 6-7 = noticeable differences. <6 = wrong characters."""

    user_prompt = f"""Analyze this image and check if the characters match their descriptions.

Characters expected in this scene:
{chars_text}

Scene context:
{writer_text[:1000]}

For each character:
1. Is the character present in the image?
2. Does their appearance match the description?
3. List any inconsistencies.

Return JSON only."""

    body = json.dumps({
        "model": CV_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": image_data_url}}
        ]}],
        "max_tokens": 800,
        "temperature": 0.1,
    }, ensure_ascii=True)

    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:7860",
                    "X-Title": "Animation Studio v2 - Character Consistency",
                },
                content=body.encode("utf-8"),
            )
            data = resp.json()
            raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if isinstance(raw_content, list):
                content = "\n".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in raw_content
                )
            elif isinstance(raw_content, dict):
                content = raw_content.get("text", "") or json.dumps(raw_content, ensure_ascii=False)
            else:
                content = str(raw_content)
    except Exception as e:
        await _post_discussion(f"[CONSISTENCY] Ошибка OpenRouter: {str(e)[:200]}", "system", "orchestrator")
        return {"score": 5, "issues": [f"API error: {str(e)[:200]}"], "characters_checked": len(characters_data)}

    from orchestrator.prompt_builder import _extract_json
    result = _extract_json(content)
    if not result:
        return {"score": 5, "issues": [f"Failed to parse CV response: {content[:200]}"], "characters_checked": len(characters_data)}

    score = result.get("score", 5)
    checks = result.get("checks", [])
    issues = []

    for check in checks:
        if not check.get("matches", True) or not check.get("present", True):
            issues.append(f"{check.get('name', '?')}: {check.get('issues', 'mismatch')}")

    await _post_discussion(
        f"[CONSISTENCY] Проверено {len(checks)} персонажей, score={score}/10, проблем={len(issues)}",
        "system", "orchestrator"
    )

    return {
        "score": score,
        "issues": issues,
        "characters_checked": len(checks),
        "checks": checks,
    }
