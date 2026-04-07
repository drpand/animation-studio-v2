"""
Orchestrator Executor — ядро выполнения цепочки задач.
Выполняет: agent → summarize → critic → fixer цикл.
"""
import re
import asyncio
import json
import os
from datetime import datetime

from config import PROJECT_NAME

from config import OPENROUTER_API_KEY
from orchestrator.task_chain import TaskChain, AgentStep
from orchestrator.progress_tracker import tracker
from med_otdel.agent_memory import call_llm
from med_otdel.med_core import write_event, run_evaluation, log_med_action
from med_otdel.studio_monitor import set_agent_error, reset_agent_error

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_FILE = os.path.join(PROJECT_ROOT, "orchestrator", "agent_registry.json")
PATTERNS_FILE = os.path.join(PROJECT_ROOT, "med_otdel", "patterns.json")
PROJECT_MEMORY_FILE = os.path.join(PROJECT_ROOT, "memory", "project_memory.json")


def _load_full_project_context() -> str:
    """Загружает полный контекст активного проекта из project_memory.json."""
    if not os.path.exists(PROJECT_MEMORY_FILE):
        return ""
    try:
        with open(PROJECT_MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        project = data.get("active_project", {})
        if not project or not project.get("name"):
            return ""
        
        parts = []
        parts.append(f"Название проекта: {project.get('name', '')}")
        if project.get("description"):
            parts.append(f"Описание: {project['description']}")
        if project.get("visual_style"):
            parts.append(f"Визуальный стиль: {project['visual_style']}")
        if project.get("color_palette"):
            parts.append(f"Цветовая палитра: {project['color_palette']}")
        if project.get("music_reference"):
            parts.append(f"Музыкальный референс: {project['music_reference']}")
        
        season = project.get("current_season", 1)
        episode = project.get("current_episode", 1)
        parts.append(f"Текущий эпизод: Сезон {season}, Эпизод {episode}")
        
        return "\n".join(parts)
    except Exception:
        return ""


# ============================================
# CV АВТОМАТИЧЕСКАЯ ПРОВЕРКА ПОСЛЕ ГЕНЕРАЦИИ
# ============================================

async def _cv_auto_check(image_url: str, writer_text: str, final_prompt: str, task_id: str) -> dict:
    """
    Автоматическая CV проверка изображения через Gemini Vision.
    Вызывается после генерации Kie.ai.
    Если score < 8 — запускает авто-исправление (до 3 попыток).
    Возвращает: {"score": int, "description": str, "matched": [], "missing": [], "attempts": int}
    """
    import base64
    import httpx

    CV_MODEL = "google/gemini-3.1-flash-lite-preview"
    MAX_ATTEMPTS = 3
    CV_PASS_SCORE = 8

    current_image_url = image_url
    current_prompt = final_prompt
    history = []

    for attempt in range(1, MAX_ATTEMPTS + 1):
        await _post_discussion(f"[CV-AUTO] Попытка {attempt}/{MAX_ATTEMPTS}: проверка изображения...", "system", "orchestrator")

        # Шаг 1: Загружаем изображение и конвертируем в base64
        image_b64 = ""
        if current_image_url.startswith("/tools_cache/"):
            filename = os.path.basename(current_image_url)
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
                    resp = await client.get(current_image_url)
                    if resp.status_code == 200:
                        image_b64 = base64.b64encode(resp.content).decode("utf-8")
            except Exception:
                pass

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
            critic_feedback, _ = await asyncio.wait_for(
                call_llm(system_prompt=critic_system, user_prompt=critic_user, model="deepseek/deepseek-v3.2"),
                timeout=60
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
            new_prompt, _ = await asyncio.wait_for(
                call_llm(system_prompt=fixer_system, user_prompt=fixer_user, model="deepseek/deepseek-v3.2"),
                timeout=60
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


# ============================================
# CV ПРОВЕРКА КОНСИСТЕНТНОСТИ ПЕРСОНАЖЕЙ
# ============================================

async def _check_character_consistency(image_url: str, characters_data: list, writer_text: str) -> dict:
    """
    Проверить консистентность персонажей на изображении.
    Сравнивает описание каждого персонажа с тем что видно на изображении.
    Возвращает: {"score": int, "issues": [], "characters_checked": int}
    """
    import base64
    import httpx

    if not characters_data or not image_url:
        return {"score": 10, "issues": [], "characters_checked": 0}

    CV_MODEL = "google/gemini-3.1-flash-lite-preview"

    # Загружаем изображение
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


def _load_registry() -> list:
    if os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _get_agent_timeout(agent_id: str) -> int:
    registry = _load_registry()
    for agent in registry:
        if agent.get("id") == agent_id:
            return agent.get("timeout", 90)
    return 90


def _get_agent_model(agent_id: str) -> str:
    registry = _load_registry()
    for agent in registry:
        if agent.get("id") == agent_id:
            return agent.get("model", "deepseek/deepseek-v3.2")
    return "deepseek/deepseek-v3.2"


async def _post_discussion(content: str, msg_type: str = "system", agent_id: str = ""):
    """Записать сообщение в Discussion канал."""
    discussion_file = os.path.join(PROJECT_ROOT, "memory", "discussion_log.json")
    entry = {
        "agent_id": agent_id or "orchestrator",
        "content": content,
        "msg_type": msg_type,
        "timestamp": datetime.now().isoformat(),
    }
    try:
        if os.path.exists(discussion_file):
            with open(discussion_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"messages": []}
        data["messages"].append(entry)
        if len(data["messages"]) > 200:
            data["messages"] = data["messages"][-200:]
        dir_name = os.path.dirname(discussion_file)
        import tempfile
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, discussion_file)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    except Exception:
        pass


async def _summarize_for_next_agent(text: str, next_agent_role: str, task_id: str) -> str:
    """Суммаризировать результат для следующего агента."""
    if not text or len(text) < 500:
        return text

    system = "Ты эксперт по суммаризации. Извлеки только то, что нужно следующему специалисту."
    user = f"""Извлеки из этого результата только то, что нужно агенту "{next_agent_role}" для работы.
Игнорируй всё остальное. Максимум 2000 символов.

Результат:
{text[:4000]}

Верни только суммаризированный текст."""

    try:
        result, _ = await asyncio.wait_for(
            call_llm(system_prompt=system, user_prompt=user),
            timeout=60
        )
        return result.strip()[:2000]
    except Exception:
        return text[:2000]


async def _run_agent_step(agent_id: str, input_text: str, task_id: str) -> tuple[str, bool]:
    """
    Запустить агента с таймаутом и проверкой отмены.
    Возвращает (output, success).
    """
    if tracker.is_cancelled(task_id):
        return "", False

    model = _get_agent_model(agent_id)
    timeout = _get_agent_timeout(agent_id)

    await _post_discussion(
        f"[{agent_id.upper()}] Начало работы. Модель: {model}",
        "agent",
        agent_id
    )

    try:
        # Импортируем BaseAgent здесь чтобы избежать циклических импортов
        from agents.base_agent import BaseAgent, _load_constitution

        constitution = _load_constitution()
        project_context = _load_full_project_context()
        
        system_prompt = ""
        if constitution:
            system_prompt += f"[КОНСТИТУЦИЯ СТУДИИ]\n{constitution}\n\n"
        
        if project_context:
            system_prompt += f"[КОНТЕКСТ ПРОЕКТА]\n{project_context}\n\n"
        
        system_prompt += f"[РОЛЬ]\nТы {agent_id} анимационной студии. Работай по правилам Конституции и строго следуй контексту активного проекта (визуальный стиль, цветовая палитра, музыкальный референс).\n\n[ЗАДАЧА]\n{input_text}"

        async def _call_openrouter():
            import httpx
            async with httpx.AsyncClient(timeout=timeout + 30) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:7860",
                        "X-Title": "Animation Studio v2"
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": input_text[:8000]}
                        ]
                    }
                )
                data = resp.json()
                if resp.status_code >= 400:
                    error_obj = data.get("error", {}) if isinstance(data, dict) else {}
                    error_msg = error_obj.get("message") or data.get("message") or resp.text
                    raise Exception(f"OpenRouter {resp.status_code}: {error_msg}")
                if not isinstance(data, dict) or "choices" not in data or not data.get("choices"):
                    raise Exception(f"OpenRouter: неожиданный формат ответа")
                return data["choices"][0]["message"]["content"]

        result = await asyncio.wait_for(_call_openrouter(), timeout=timeout)

        if tracker.is_cancelled(task_id):
            return "", False

        await _post_discussion(
            f"[{agent_id.upper()}] Завершил работу. Результат: {len(result)} символов",
            "agent",
            agent_id
        )
        return result, True

    except asyncio.TimeoutError:
        await _post_discussion(
            f"[{agent_id.upper()}] Таймаут ({timeout} сек)",
            "system",
            agent_id
        )
        return f"[ТАЙМАУТ] Агент {agent_id} не ответил за {timeout} сек", False
    except Exception as e:
        await _post_discussion(
            f"[{agent_id.upper()}] Ошибка: {str(e)[:200]}",
            "system",
            agent_id
        )
        return f"[ОШИБКА] {str(e)[:500]}", False


async def _run_critic(text: str, task_id: str, agent_id: str = "") -> tuple[bool, str]:
    """Запустить Critic для оценки текста."""
    if tracker.is_cancelled(task_id):
        return False, "Задача отменена"

    project_context = _load_full_project_context()
    context_note = f"\n\nКонтекст проекта:\n{project_context}" if project_context else ""
    
    system = f"Ты строгий критик анимационной студии. Оценивай результаты объективно, учитывая требования проекта.{context_note}"
    user = f"""Оцени результат работы агента.

Текст:
{text[:4000]}

Оцени по шкале 1-10. Если >= 7 — PASS, иначе FAIL.
Дай конкретную обратную связь.

Формат:
SCORE: <число>
PASS/FAIL
FEEDBACK: <текст>"""

    try:
        result, _ = await asyncio.wait_for(
            call_llm(system_prompt=system, user_prompt=user),
            timeout=60
        )

        passed = "PASS" in result.upper() and "FAIL" not in result.upper().replace("PASS", "")
        feedback = ""
        for line in result.split("\n"):
            if line.strip().upper().startswith("FEEDBACK:"):
                feedback = line.strip()[len("FEEDBACK:"):].strip()
                break

        status_text = "PASS" if passed else "FAIL"
        await _post_discussion(
            f"[CRITIC] Оценка: {status_text}. {feedback[:200]}",
            "critic",
            "critic"
        )
        return passed, feedback
    except Exception as e:
        await _post_discussion(f"[CRITIC] Ошибка: {str(e)[:200]}", "system", "critic")
        return False, str(e)


async def _run_fixer(original_text: str, critic_feedback: str, task_id: str) -> str:
    """Запустить Fixer для исправления текста."""
    if tracker.is_cancelled(task_id):
        return original_text

    project_context = _load_full_project_context()
    context_note = f"\n\nКонтекст проекта:\n{project_context}" if project_context else ""
    
    system = f"Ты фиксер анимационной студии. Исправляй результаты по замечаниям критика, строго соблюдая требования активного проекта (визуальный стиль, цветовая палитра, музыкальный референс).{context_note}"
    user = f"""Исправь результат по замечаниям критика.

Оригинал:
{original_text[:4000]}

Замечания:
{critic_feedback[:1000]}

Верни исправленный результат."""

    try:
        result, _ = await asyncio.wait_for(
            call_llm(system_prompt=system, user_prompt=user),
            timeout=120
        )
        await _post_discussion(
            f"[FIXER] Исправил результат. {len(result)} символов",
            "agent",
            "fixer"
        )
        return result
    except Exception as e:
        await _post_discussion(f"[FIXER] Ошибка: {str(e)[:200]}", "system", "fixer")
        return original_text


async def execute_chain(chain: TaskChain):
    """
    Выполнить всю цепочку задачи.
    """
    chain.status = "running"
    tracker.update_task(chain)

    await _post_discussion(
        f"[ORCHESTRATOR] Задача '{chain.description}' запущена. Шагов: {len(chain.steps)}",
        "system",
        "orchestrator"
    )

    previous_output = ""

    for i, step in enumerate(chain.steps):
        if tracker.is_cancelled(chain.task_id):
            chain.status = "cancelled"
            chain.completed_at = datetime.now().isoformat()
            tracker.update_task(chain)
            await _post_discussion(
                f"[ORCHESTRATOR] Задача отменена пользователем на шаге {i+1}",
                "system",
                "orchestrator"
            )
            return

        chain.current_step = i
        step.status = "running"
        step.started_at = datetime.now().isoformat()
        tracker.update_task(chain)

        # Определяем следующего агента для суммаризации
        next_agent_id = chain.steps[i + 1].agent_id if i + 1 < len(chain.steps) else ""

        # Суммаризация входных данных (кроме первого шага)
        input_text = step.input
        if previous_output and i > 0:
            if next_agent_id and next_agent_id != "critic":
                # Суммаризируем для следующего агента
                input_text = await _summarize_for_next_agent(previous_output, next_agent_id, chain.task_id)
            else:
                # Critic получает полный результат
                input_text = previous_output

        step.input = input_text

        # Запуск агента
        output, success = await _run_agent_step(step.agent_id, input_text, chain.task_id)
        step.output = output

        if not success:
            step.status = "failed"
            step.completed_at = datetime.now().isoformat()
            chain.status = "failed"
            chain.result = output
            chain.completed_at = datetime.now().isoformat()
            tracker.update_task(chain)
            await _post_discussion(
                f"[ORCHESTRATOR] Шаг {i+1} ({step.agent_id}) провален. Задача остановлена.",
                "system",
                "orchestrator"
            )
            return

        # Critic после каждого агента (кроме Critic и Fixer)
        if step.agent_id not in ("critic", "fixer"):
            passed, feedback = await _run_critic(output, chain.task_id, step.agent_id)
            step.critic_passed = passed
            step.critic_feedback = feedback

            if not passed:
                # Fixer цикл (макс 3 попытки)
                original_output = output
                for fix_attempt in range(3):
                    if tracker.is_cancelled(chain.task_id):
                        chain.status = "cancelled"
                        chain.completed_at = datetime.now().isoformat()
                        tracker.update_task(chain)
                        return

                    step.fix_attempts = fix_attempt + 1
                    fixed_output = await _run_fixer(output, feedback, chain.task_id)

                    # Повторная оценка
                    passed, feedback = await _run_critic(fixed_output, chain.task_id, step.agent_id)
                    step.critic_passed = passed
                    step.critic_feedback = feedback

                    if passed:
                        output = fixed_output
                        step.output = output
                        break
                    else:
                        output = fixed_output

                if not passed:
                    # Degraded fallback
                    step.status = "degraded"
                    step.output = original_output
                    await _post_discussion(
                        f"[ORCHESTRATOR] Шаг {i+1} ({step.agent_id}) выполнен с ошибками (degraded). Fixer не смог исправить 3 раза.",
                        "system",
                        "orchestrator"
                    )
                    # Уровень 3: МЕД-ОТДЕЛ — логируем провал
                    try:
                        from database import async_session
                        import crud
                        async with async_session() as db:
                            await crud.add_med_log(db, {
                                "action": "critic_fixer_failed",
                                "details": f"Agent {step.agent_id} failed critic after 3 fix attempts. Task: {chain.task_id}",
                                "agent_id": step.agent_id,
                                "timestamp": datetime.now().isoformat(),
                            })
                    except Exception:
                        pass
                    # Уровень 3: МЕД-ОТДЕЛ — логируем провал
                    try:
                        from database import async_session
                        import crud
                        async with async_session() as db:
                            await crud.add_med_log(db, {
                                "action": "critic_fixer_failed",
                                "details": f"Agent {step.agent_id} failed critic after 3 fix attempts. Task: {chain.task_id}",
                                "agent_id": step.agent_id,
                                "timestamp": datetime.now().isoformat(),
                            })
                    except Exception:
                        pass
                else:
                    step.status = "completed"
            else:
                step.status = "completed"
        else:
            step.status = "completed"

        step.completed_at = datetime.now().isoformat()
        previous_output = step.output
        tracker.update_task(chain)

    # Задача завершена
    chain.status = "completed"
    chain.result = previous_output
    chain.completed_at = datetime.now().isoformat()
    tracker.update_task(chain)

    await _post_discussion(
        f"[ORCHESTRATOR] Задача '{chain.description}' завершена успешно.",
        "system",
        "orchestrator"
    )


# ============================================
# ПРОИЗВОДСТВЕННЫЙ КОНВЕЙЕР (Раздел 16)
# ============================================

def _extract_json(text: str) -> dict:
    """Извлечь JSON из ответа LLM (игнорируя маркдаун и лишний текст)."""
    if not text:
        return {}
    
    # Сначала ищем JSON внутри markdown-блока
    md_match = re.search(r'```(?:json)?\s*\n(.*?)```', text, re.DOTALL)
    if md_match:
        try:
            result = json.loads(md_match.group(1).strip())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
    
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return {}
    return {}


def _extract_json_array(text: str) -> list:
    """Извлечь JSON массив из ответа LLM."""
    if not text:
        return []
    
    # Если текст начинается с кавычки, это может быть JSON-строка с экранированным массивом
    if text.strip().startswith('"'):
        try:
            text = json.loads(text)
        except json.JSONDecodeError:
            pass
    
    # Сначала ищем JSON внутри markdown-блока ```json ... ```
    md_match = re.search(r'```(?:json)?\s*\n(.*?)```', text, re.DOTALL)
    if md_match:
        try:
            result = json.loads(md_match.group(1).strip())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    
    # Ищем JSON массив в тексте
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return []
    return []


def _extract_names_to_remove(feedback: str) -> list:
    """Извлечь имена персонажей для удаления из feedback Critic."""
    names = []
    for line in feedback.split('\n'):
        line = line.strip()
        if any(kw in line.lower() for kw in ['галлюцин', 'удал', 'нет в тексте', 'не упоминается', 'выдуман']):
            # Ищем имена в кавычках или после тире
            quoted = re.findall(r'["«"]([^"»"]+)["»"]', line)
            names.extend(quoted)
    return names


def _safe_text(value) -> str:
    """Безопасно привести значение к строке для логов/промптов."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def _safe_text_list(values) -> list:
    """Нормализовать список значений в список строк (без пустых)."""
    if not isinstance(values, list):
        return []
    result = []
    for v in values:
        text = _safe_text(v).strip()
        if text:
            result.append(text)
    return result


def _sanitize_image_text(text: str) -> str:
    """Очистить текст от видео-таймингов и motion-терминов для статичного image prompt."""
    t = _safe_text(text)
    if not t:
        return ""

    # Таймкоды и явные длительности
    t = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\b\d+\s*(секунд|сек|seconds?|s|fps)\b", " ", t, flags=re.IGNORECASE)

    # Термины движения камеры/монтажа (ru/en)
    motion_terms = [
        "dolly", "dolly in", "dolly out", "pan", "tilt", "zoom", "tracking", "truck",
        "crane", "orbit", "whip pan", "camera movement", "camera move", "transition",
        "cut to", "crossfade", "montage", "sequence", "shot-reverse-shot",
        "долли", "панорама", "панорамирование", "наклон камеры", "зум", "наезд", "отъезд",
        "треккинг", "кран", "орбита", "монтаж", "переход", "склейка", "последовательность",
        "кадр за кадром", "тайминг", "хронометраж"
    ]
    for term in motion_terms:
        t = re.sub(rf"\b{re.escape(term)}\b", " ", t, flags=re.IGNORECASE)

    # Нормализация пробелов/пунктуации
    t = re.sub(r"\s+", " ", t).strip(" ,.;:-")
    return t


def _pick_visual_phrase(parts: dict, keys: list, default: str = "") -> str:
    """Взять первое валидное визуальное поле из списка ключей."""
    for k in keys:
        v = parts.get(k)
        if v is None:
            continue
        if isinstance(v, (dict, list)):
            continue
        s = _sanitize_image_text(str(v))
        if s:
            return s
    return default


def _build_strict_image_parts(parts: dict) -> dict:
    """Собрать структурные image-поля (карточка кадра) из решений цехов."""
    subject = _pick_visual_phrase(parts, ["character", "subject"], "adult human protagonist")
    location = _pick_visual_phrase(parts, ["location", "environment", "background"], "night exterior")
    lighting = _pick_visual_phrase(parts, ["lighting"], "cinematic low-key lighting")
    style = _pick_visual_phrase(parts, ["style"], "cinematic illustration, detailed textures")
    palette = _pick_visual_phrase(parts, ["palette", "color_palette"], "cold muted contrast")
    # Mood может приходить от sound_director (не подходит для image prompt),
    # поэтому читаем только визуальную атмосферу.
    mood = _pick_visual_phrase(parts, ["atmosphere", "visual_mood"], "tense dramatic mood")
    composition = _pick_visual_phrase(parts, ["shot", "composition", "framing"], "single static composition")
    return {
        "subject": subject,
        "location": location,
        "lighting": lighting,
        "style": style,
        "palette": palette,
        "mood": mood,
        "composition": composition,
        "constraints": [
            "aspect ratio 16:9",
            "single still frame",
            "no camera movement",
            "no transitions",
            "no sequence",
            "no storyboard panels",
            "no subtitles",
            "no text",
            "no watermark",
        ],
    }


def _compose_image_prompt(parts: dict) -> str:
    """Собрать строковый image prompt из структурных полей карточки кадра."""
    strict_parts = [
        f"subject: {_safe_text(parts.get('subject', 'adult human protagonist'))}",
        f"location: {_safe_text(parts.get('location', 'night exterior'))}",
        f"lighting: {_safe_text(parts.get('lighting', 'cinematic low-key lighting'))}",
        f"style: {_safe_text(parts.get('style', 'cinematic illustration, detailed textures'))}",
        f"palette: {_safe_text(parts.get('palette', 'cold muted contrast'))}",
        f"mood: {_safe_text(parts.get('mood', 'tense dramatic mood'))}",
        f"composition: {_safe_text(parts.get('composition', 'single static composition'))}",
    ]
    constraints = parts.get("constraints", [])
    if isinstance(constraints, list):
        strict_parts.extend([_safe_text(c) for c in constraints if _safe_text(c)])
    prompt = ", ".join([p for p in strict_parts if p])
    return prompt[:800]


def _build_strict_image_prompt(parts: dict) -> str:
    """Backward-compatible wrapper: принимает сырые части, возвращает image-only prompt."""
    return _compose_image_prompt(_build_strict_image_parts(parts))


def _contains_panda(text: str) -> bool:
    t = _safe_text(text).lower()
    return ("panda" in t) or ("панда" in t)


def _sanitize_subject_leakage(subject: str, context: dict) -> str:
    """Очистка subject от утечек сущностей, которых нет в текущей сцене."""
    s = _safe_text(subject)
    writer_text = _safe_text(context.get("writer_text", ""))
    task_text = _safe_text(context.get("task_text", ""))
    hr_text = _safe_text(context.get("hr_text", ""))
    full_context = f"{writer_text}\n{task_text}\n{hr_text}".lower()
    panda_allowed = ("panda" in full_context) or ("панда" in full_context)
    if not panda_allowed and _contains_panda(s):
        s = re.sub(r"\bsamurai panda\b", "adult human protagonist", s, flags=re.IGNORECASE)
        s = re.sub(r"\bpanda samurai\b", "adult human protagonist", s, flags=re.IGNORECASE)
        s = re.sub(r"\bpanda\b", "adult human", s, flags=re.IGNORECASE)
        s = re.sub(r"панда[-\s]?самурай", "взрослый человек", s, flags=re.IGNORECASE)
        s = re.sub(r"панда", "взрослый человек", s, flags=re.IGNORECASE)
    return s[:300]


def _sanitize_entity_leakage(prompt: str, context: dict) -> str:
    """Убирает утечку сущностей (например, panda), если их нет в текущем контексте задачи."""
    p = _safe_text(prompt)
    # Контекст текущей сцены
    writer_text = _safe_text(context.get("writer_text", ""))
    task_text = _safe_text(context.get("task_text", ""))
    hr_text = _safe_text(context.get("hr_text", ""))
    full_context = f"{writer_text}\n{task_text}\n{hr_text}".lower()

    panda_allowed = ("panda" in full_context) or ("панда" in full_context)
    if not panda_allowed and _contains_panda(p):
        # Жёстко заменяем panda-сущности на нейтрального персонажа
        p = re.sub(r"\bsamurai panda\b", "adult human protagonist", p, flags=re.IGNORECASE)
        p = re.sub(r"\bpanda samurai\b", "adult human protagonist", p, flags=re.IGNORECASE)
        p = re.sub(r"\bpanda\b", "adult human", p, flags=re.IGNORECASE)
        p = re.sub(r"панда[-\s]?самурай", "взрослый человек", p, flags=re.IGNORECASE)
        p = re.sub(r"панда", "взрослый человек", p, flags=re.IGNORECASE)

    return p[:800]


def _build_kieai_prompt(parts: dict) -> str:
    """Собрать финальный промпт из JSON частей цехов для Z-Image Turbo.
    Kie.ai Z-Image имеет лимит ~800 символов — собираем компактно."""
    # Жёсткая image-only сборка: только визуальные поля и строгие ограничения.
    return _build_strict_image_prompt(parts)

async def run_step_with_critic(agent_id: str, task: str, context: dict, task_id: str = "pipeline") -> dict:
    """
    Выполнить один шаг с Critic/Fixer циклом (макс 3 круга).
    Возвращает: {"status": "approved"|"needs_review"|"failed", "result": str, "rounds": int}
    """
    # Формируем входной текст из контекста
    input_parts = []
    for key, value in context.items():
        if value:
            if isinstance(value, (dict, list)):
                try:
                    value_text = json.dumps(value, ensure_ascii=False)
                except Exception:
                    value_text = str(value)
            else:
                value_text = str(value)
            input_parts.append(f"[{key.upper()}]\n{value_text}")
    input_parts.append(f"[ЗАДАЧА]\n{task}")
    input_text = "\n\n".join(input_parts)

    # Шаг 1: Агент выполняет задачу
    result, success = await _run_agent_step(agent_id, input_text, task_id)
    # Пишем событие выполнения шага в шину МЕД-ОТДЕЛА
    try:
        write_event(
            agent_id=agent_id,
            event_type="task_completed",
            result=_safe_text(result),
            status="success" if success else "fail",
            task_id=task_id,
        )
    except Exception:
        pass

    if not success:
        try:
            set_agent_error(agent_id)
            log_med_action("pipeline_step_failed", f"{agent_id} step failed before critic", agent_id)
        except Exception:
            pass
        return {"status": "failed", "result": result, "rounds": 0}

    # Critic/Fixer цикл (макс 3 круга)
    for round_num in range(3):
        passed, feedback = await _run_critic(result, task_id, agent_id)
        # Пишем событие оценки в шину МЕД-ОТДЕЛА
        try:
            write_event(
                agent_id="critic",
                event_type="evaluation",
                result=_safe_text(feedback),
                status="pass" if passed else "fail",
                task_id=task_id,
                target_agent_id=agent_id,
            )
        except Exception:
            pass
        if passed:
            try:
                reset_agent_error(agent_id)
            except Exception:
                pass
            await _post_discussion(
                f"[CONVEYOR] {agent_id}: APPROVED (round {round_num + 1})",
                "system",
                agent_id
            )
            return {"status": "approved", "result": result, "rounds": round_num + 1}

        if round_num < 2:
            result = await _run_fixer(result, feedback, task_id)
        else:
            # 3 круга — отправляем на ручную проверку
            await _post_discussion(
                f"[CONVEYOR] {agent_id}: NEEDS REVIEW после 3 кругов Critic/Fixer",
                "system",
                agent_id
            )
            try:
                set_agent_error(agent_id)
                # Запускаем МЕД-ОТДЕЛ оценку/эволюцию по последнему результату
                await run_evaluation(
                    task_result=_safe_text(result),
                    agent_id=agent_id,
                    task_description=_safe_text(task)[:500],
                )
            except Exception:
                pass
            return {"status": "needs_review", "result": result, "rounds": 3, "critique": feedback}

    return {"status": "approved", "result": result, "rounds": 3}


async def run_casting(pdf_context: str, task_id: str, db=None) -> dict:
    """
    Этап Кастинга: HR извлекает персонажей из PDF → Critic сверяет с текстом → Fixer исправляет галлюцинации.
    Возвращает список персонажей и сохраняет в БД.
    """
    import crud
    from database import async_session

    await _post_discussion("[CASTING] Начало кастинга — извлечение персонажей из сценария...", "system", "orchestrator")

    # 1. HR извлекает персонажей из PDF (БЕЗ run_step_with_critic — чтобы сохранить JSON)
    hr_prompt = (
        "Извлеки ВСЕХ персонажей из текста сценария. ВАЖНО: создавай карточки ТОЛЬКО для персонажей "
        "которые реально появляются в тексте. НЕ выдумывай персонажей.\n\n"
        "Верни СТРОГО JSON массив, НИЧЕГО кроме JSON:\n"
        "[{\"name\":\"Имя\",\"age\":\"возраст\",\"appearance\":\"внешность\","
        "\"clothing\":\"одежда\",\"voice\":\"манера речи\",\"role\":\"роль\","
        "\"kieai_description\":\"English description for AI image generation\"}]\n\n"
        f"Текст сценария:\n{pdf_context[:6000]}"
    )

    hr_result, hr_success = await _run_agent_step("hr_agent", hr_prompt, task_id)

    if not hr_success:
        await _post_discussion("[CASTING] HR не смог извлечь персонажей", "system", "orchestrator")
        return {"status": "failed", "characters": []}

    # Извлекаем JSON
    characters_data = _extract_json_array(hr_result)

    await _post_discussion(
        f"[CASTING] HR вернул {len(hr_result)} chars, извлечено {len(characters_data)} персонажей",
        "system", "orchestrator")

    if characters_data:
        for c in characters_data:
            await _post_discussion(f"[CASTING] Персонаж: {c.get('name', '?')}", "system", "orchestrator")

    if not characters_data:
        await _post_discussion("[CASTING] HR вернул пустой список персонажей — продолжаем без кастинга для этой сцены", "system", "orchestrator")
        await _post_discussion(f"[CASTING] HR output: {hr_result[:500]}", "system", "orchestrator")
        return {
            "status": "approved",
            "characters": [],
            "saved_count": 0,
            "critic_passed": True,
            "critic_feedback": "",
            "result": "[]",
        }

    # 2. Critic сверяет персонажей с PDF — отклоняет галлюцинации
    critic_passed = False
    critic_feedback = ""

    await _post_discussion("[CASTING] Critic сверяет персонажей с PDF сценария...", "system", "orchestrator")

    char_list = "\n".join(
        f"- {c.get('name', '?')}: {c.get('appearance', '')[:100]}"
        for c in characters_data
    )

    passed, feedback = await _run_critic(
        ("Проверь: эти персонажи реально есть в тексте сценария? Отклони тех кого НЕТ в тексте.\n\n"
         "Персонажи от HR:\n{chars}\n\n"
         "Оригинальный текст сценария:\n{pdf}\n\n"
         "Если персонаж НЕ упоминается в тексте — это ГАЛЛЮЦИНАЦИЯ. Отклоняй безжалостно.\n"
         "Формат:\nSCORE: <число>\nPASS/FAIL\nFEEDBACK: <текст>").format(
            chars=char_list, pdf=pdf_context[:4000]),
        task_id, "critic")

    if passed:
        critic_passed = True
        await _post_discussion(f"[CASTING] Critic: PASS. Все {len(characters_data)} персонажей подтверждены.", "system", "orchestrator")
    else:
        critic_feedback = feedback
        await _post_discussion(f"[CASTING] Critic: FAIL. {feedback[:200]}", "system", "orchestrator")

        # Удаляем галлюцинированных персонажей из списка
        names_to_remove = _extract_names_to_remove(feedback)
        if names_to_remove:
            original_count = len(characters_data)
            characters_data = [c for c in characters_data if c.get("name", "") not in names_to_remove]
            await _post_discussion(
                f"[CASTING] Удалено {original_count - len(characters_data)} галлюцинированных персонажей: {', '.join(names_to_remove)}",
                "system", "orchestrator")

            if characters_data:
                critic_passed = True
                await _post_discussion(f"[CASTING] Осталось {len(characters_data)} подтверждённых персонажей", "system", "orchestrator")

    # 3. Сохраняем персонажей в БД
    saved_count = 0

    if characters_data and db:
        for char_data in characters_data:
            name = char_data.get("name", "")
            if not name:
                continue
            try:
                await crud.create_character(db, 1, {
                    "name": name,
                    "description": f"Возраст: {char_data.get('age', '')}. Внешность: {char_data.get('appearance', '')}. Одежда: {char_data.get('clothing', '')}. Голос: {char_data.get('voice', '')}",
                    "voice_id": char_data.get("voice", ""),
                    "relations": char_data.get("role", ""),
                    "created_at": datetime.now().isoformat(),
                })
                saved_count += 1
                await _post_discussion(f"[CASTING] Персонаж сохранён: {name}", "system", "hr_agent")
            except Exception as e:
                await _post_discussion(f"[CASTING] Ошибка сохранения {name}: {str(e)[:100]}", "system", "hr_agent")
        await db.commit()

    # 4. Создаём паттерн character_consistency
    if saved_count > 0:
        await _create_character_pattern(hr_result, db)

    await _post_discussion(f"[CASTING] Кастинг завершён: {saved_count} персонажей сохранено", "system", "orchestrator")

    return {
        "status": "approved" if critic_passed else "needs_review",
        "characters": characters_data,
        "saved_count": saved_count,
        "critic_passed": critic_passed,
        "critic_feedback": critic_feedback,
    }


async def run_full_casting(pdf_context: str, db) -> list:
    """
    Полный кастинг для всего сценария — извлекает всех персонажей.
    Возвращает список всех найденных персонажей.
    """
    import crud
    from database import async_session

    await _post_discussion("[FULL_CASTING] Начало полного кастинга — извлечение всех персонажей из сценария...", "system", "orchestrator")

    # 1. HR извлекает всех персонажей из всего сценария
    hr_prompt = (
        "Извлеки ВСЕХ персонажей из текста сценария. ВАЖНО: создавай карточки ТОЛЬКО для персонажей "
        "которые реально появляются в тексте. НЕ выдумывай персонажей.\n\n"
        "Верни СТРОГО JSON массив, НИЧЕГО кроме JSON:\n"
        "[{\"name\":\"Имя\",\"age\":\"возраст\",\"appearance\":\"внешность\","
        "\"clothing\":\"одежда\",\"voice\":\"манера речи\",\"role\":\"роль\","
        "\"kieai_description\":\"English description for AI image generation\"}]\n\n"
        f"Текст сценария:\n{pdf_context[:15000]}"
    )

    hr_result, hr_success = await _run_agent_step("hr_agent", hr_prompt, "full_casting_task")

    if not hr_success:
        await _post_discussion("[FULL_CASTING] HR не смог извлечь персонажей", "system", "orchestrator")
        return []

    # Извлекаем JSON
    characters_data = _extract_json_array(hr_result)

    await _post_discussion(
        f"[FULL_CASTING] HR вернул {len(hr_result)} символов, извлечено {len(characters_data)} персонажей",
        "system", "orchestrator")

    if not characters_data:
        await _post_discussion("[FULL_CASTING] Не удалось извлечь JSON из ответа HR", "system", "orchestrator")
        await _post_discussion(f"[FULL_CASTING] HR output: {hr_result[:500]}", "system", "orchestrator")
        return []

    # 2. Critic сверяет персонажей с PDF — отклоняет галлюцинации
    critic_passed = False
    critic_feedback = ""
    characters_to_save = characters_data

    await _post_discussion("[FULL_CASTING] Critic сверяет персонажей с PDF сценария...", "system", "orchestrator")

    char_list = "\n".join(
        f"- {c.get('name', '?')}: {c.get('appearance', '')[:100]}"
        for c in characters_data
    )

    # Проверка через Critic
    passed, feedback = await _run_critic(
        ("Проверь: эти персонажи реально есть в тексте сценария? Отклони тех кого НЕТ в тексте.\n\n"
         "Персонажи от HR:\n{chars}\n\n"
         "Оригинальный текст сценария:\n{pdf}\n\n"
         "Если персонаж НЕ упоминается в тексте — это ГАЛЛЮЦИНАЦИЯ. Отклоняй безжалостно.\n"
         "Формат:\nSCORE: <число>\nPASS/FAIL\nFEEDBACK: <текст>").format(
            chars=char_list, pdf=pdf_context[:4000]),
        "full_casting_task", "critic")

    if passed:
        critic_passed = True
        await _post_discussion(f"[FULL_CASTING] Critic: PASS. Все {len(characters_data)} персонажей подтверждены.", "system", "orchestrator")
    else:
        critic_feedback = feedback
        await _post_discussion(f"[FULL_CASTING] Critic: FAIL. {feedback[:200]}", "system", "orchestrator")

        # Удаляем галлюцинированных персонажей из списка
        names_to_remove = _extract_names_to_remove(feedback)
        if names_to_remove:
            original_count = len(characters_data)
            characters_to_save = [c for c in characters_data if c.get("name", "") not in names_to_remove]
            await _post_discussion(
                f"[FULL_CASTING] Удалено {original_count - len(characters_to_save)} галлюцинированных персонажей: {', '.join(names_to_remove)}",
                "system", "orchestrator")

            if characters_to_save:
                critic_passed = True
                await _post_discussion(f"[FULL_CASTING] Осталось {len(characters_to_save)} подтверждённых персонажей", "system", "orchestrator")

    # 3. Сохраняем персонажей в БД
    saved_count = 0

    if characters_to_save and db:
        for char_data in characters_to_save:
            name = char_data.get("name", "")
            if not name:
                # Log warning about empty name
                await _post_discussion(f"[FULL_CASTING] WARNING: Character with empty name skipped: {char_data}", "system", "orchestrator")
                continue
            
            # Debug logging
            await _post_discussion(f"[FULL_CASTING] Saving character: name='{name}' (type: {type(name)}, length: {len(name)})", "system", "orchestrator")
            
            try:
                # Create character with all required fields
                character_data = {
                    "name": str(name).strip(),  # Ensure it's a string
                    "description": f"Возраст: {char_data.get('age', '')}. Внешность: {char_data.get('appearance', '')}. Одежда: {char_data.get('clothing', '')}. Голос: {char_data.get('voice', '')}",
                    "voice_id": char_data.get("voice", ""),
                    "relations": char_data.get("role", ""),
                    "created_at": datetime.now().isoformat(),
                }
                
                await _post_discussion(f"[FULL_CASTING] Character data: {character_data}", "system", "orchestrator")
                
                char = await crud.create_character(db, 1, character_data)
                saved_count += 1
                await _post_discussion(f"[FULL_CASTING] Персонаж сохранён: {name} (ID: {char.id})", "system", "hr_agent")
            except Exception as e:
                await _post_discussion(f"[FULL_CASTING] Ошибка сохранения '{name}': {str(e)}", "system", "hr_agent")
                import traceback
                await _post_discussion(f"[FULL_CASTING] Traceback: {traceback.format_exc()[:500]}", "system", "hr_agent")
        await db.commit()

    await _post_discussion(f"[FULL_CASTING] Полный кастинг завершён: {saved_count} персонажей сохранено", "system", "orchestrator")

    return characters_to_save


async def run_scene_pipeline(season: int, episode: int, scene_num: int, pdf_context: str, db=None, progress_callback=None):
    """
    Полный конвейер одной сцены:
    1. Writer → 2. Director → 3. HR Casting → 4. DOP+Art+Sound (параллельно)
    → 5. Storyboarder → 6. Art Director → Kie.ai → 7. Storyboarder финал
    
    progress_callback: optional async callable(step_name: str, progress: int)
    """
    import crud
    from database import async_session

    task_id = f"scene_{season}_{episode}_{scene_num}"
    pipeline_result = {
        "task_id": task_id,
        "season": season,
        "episode": episode,
        "scene": scene_num,
        "status": "running",
        "steps": {},
        "frames": [],
    }

    await _post_discussion(f"[CONVEYOR] Запуск конвейера: Сцена {season}x{episode}:{scene_num}", "system", "orchestrator")
    try:
        write_event(
            agent_id="orchestrator",
            event_type="pipeline_start",
            result=f"scene={season}x{episode}:{scene_num}",
            status="success",
            task_id=task_id,
        )
    except Exception:
        pass
    if progress_callback:
        await progress_callback("Кастинг персонажей...", 5)

    # Этап 0: Кастинг — создаём свою сессию если db не передан
    casting_db = db
    if casting_db is None:
        casting_db_session = async_session()
        casting_db = casting_db_session
    else:
        casting_db_session = None

    casting_result = await run_casting(pdf_context, task_id, casting_db)

    if casting_db_session:
        await casting_db_session.close()

    pipeline_result["steps"]["casting"] = casting_result
    
    if casting_result["status"] == "failed":
        await _post_discussion(
            f"[CONVEYOR] FAIL на кастинге: {str(casting_result.get('result') or casting_result.get('critic_feedback') or '')[:300]}",
            "system", "orchestrator"
        )
        pipeline_result["status"] = "failed"
        try:
            write_event(
                agent_id="orchestrator",
                event_type="pipeline_step",
                result="casting_failed",
                status="fail",
                task_id=task_id,
                target_agent_id="hr_agent",
            )
        except Exception:
            pass
        return pipeline_result

    # Шаг 1: Writer описывает сцену
    await _post_discussion("[CONVEYOR] Шаг 1: Writer описывает сцену", "system", "orchestrator")
    if progress_callback:
        await progress_callback("Writer описывает сцену...", 15)
    writer_result = await run_step_with_critic("writer",
        f"Опиши сцену {scene_num} из PDF-сценария. Детально: диалоги, действия, атмосфера.",
        {"pdf_context": pdf_context}, task_id)
    pipeline_result["steps"]["writer"] = writer_result

    if writer_result["status"] == "failed":
        await _post_discussion(
            f"[CONVEYOR] FAIL на Writer: {str(writer_result.get('result') or '')[:300]}",
            "system", "orchestrator"
        )
        pipeline_result["status"] = "failed"
        try:
            write_event(
                agent_id="orchestrator",
                event_type="pipeline_step",
                result="writer_failed",
                status="fail",
                task_id=task_id,
                target_agent_id="writer",
            )
        except Exception:
            pass
        return pipeline_result

    # Шаг 2: Director — творческое решение
    await _post_discussion("[CONVEYOR] Шаг 2: Director — режиссёрское решение", "system", "orchestrator")
    if progress_callback:
        await progress_callback("Director принимает режиссёрское решение...", 30)
    director_result = await run_step_with_critic("director",
        f"Режиссёрское решение для сцены {scene_num}. Ракурсы, эмоции, ритм.",
        {"writer_output": writer_result.get("result", "")}, task_id)
    pipeline_result["steps"]["director"] = director_result

    # Шаг 3: HR — кастинг персонажей
    await _post_discussion("[CONVEYOR] Шаг 3: HR — кастинг персонажей", "system", "orchestrator")
    if progress_callback:
        await progress_callback("HR кастинг персонажей...", 40)
    hr_result = await run_step_with_critic("hr_agent",
        f"Создай карточки персонажей сцены {scene_num}. Для каждого: имя, возраст, внешность, одежда, манера речи. Верни СТРОГО JSON массив: [{{\"name\": \"...\", \"age\": 20, \"appearance\": \"...\", \"clothing\": \"...\", \"speech\": \"...\"}}]",
        {"writer_output": writer_result.get("result", "")}, task_id)
    pipeline_result["steps"]["hr_casting"] = hr_result

    # Сохраняем персонажей в БД
    if hr_result["status"] in ("approved", "needs_review"):
        hr_text = hr_result.get("result", "")
        characters_data = _extract_json_array(hr_text)
        if characters_data and db:
            for char_data in characters_data:
                try:
                    await crud.create_character(db, {
                        "project_id": 1,  # Default project
                        "name": char_data.get("name", ""),
                        "description": f"Возраст: {char_data.get('age', '')}. Внешность: {char_data.get('appearance', '')}. Одежда: {char_data.get('clothing', '')}. Манера речи: {char_data.get('speech', '')}",
                        "voice_id": "",
                        "relations": "",
                        "created_at": datetime.now().isoformat(),
                    })
                    await _post_discussion(f"[CONVEYOR] Персонаж сохранён: {char_data.get('name', '')}", "system", "hr_agent")
                except Exception:
                    pass
            await db.commit()

    # Авто-паттерн character_consistency
    if hr_result["status"] == "approved":
        await _create_character_pattern(hr_result.get("result", ""), db)

    # Шаг 4: Параллельно DOP + Art Director + Sound Director (JSON output)
    await _post_discussion("[CONVEYOR] Шаг 4: Параллельная работа цехов (JSON)", "system", "orchestrator")
    if progress_callback:
        await progress_callback("DOP, Art Director, Sound Director работают...", 55)
    
    json_context = f"""
    WRITER OUTPUT: {writer_result.get('result', '')}
    DIRECTOR NOTES: {director_result.get('result', '')}
    CHARACTERS: {hr_result.get('result', '')}
    """

    # Задачи — последовательные вызовы (asyncio.gather вызывал deadlock)
    dop_res = await run_step_with_critic("dop",
        "Опиши свет, камеру и локацию. Верни СТРОГО JSON: {\"shot\": \"...\", \"location\": \"...\", \"lighting\": \"...\"}",
        {"context": json_context}, task_id)
    art_res = await run_step_with_critic("art_director",
        "Опиши стиль и палитру. Верни СТРОГО JSON: {\"style\": \"...\", \"palette\": \"...\"}",
        {"context": json_context}, task_id)
    sound_res = await run_step_with_critic("sound_director",
        "Опиши звук. Верни СТРОГО JSON: {\"mood\": \"...\"}",
        {"context": json_context}, task_id)

    # Извлекаем JSON
    dop_json = _extract_json(dop_res.get("result", "") if isinstance(dop_res, dict) else "")
    art_json = _extract_json(art_res.get("result", "") if isinstance(art_res, dict) else "")
    sound_json = _extract_json(sound_res.get("result", "") if isinstance(sound_res, dict) else "")

    # Извлекаем персонажей из HR результата
    hr_characters = _extract_json_array(hr_result.get("result", "") if isinstance(hr_result, dict) else "")
    
    # Формируем описание персонажей для промпта
    character_description = ""
    if hr_characters:
        # Берем первого персонажа (главного)
        main_char = hr_characters[0]
        char_parts = []
        if main_char.get("name"):
            char_parts.append(main_char["name"])
        if main_char.get("appearance"):
            char_parts.append(main_char["appearance"])
        if main_char.get("clothing"):
            char_parts.append(f"одежда: {main_char['clothing']}")
        character_description = ", ".join(char_parts) if char_parts else "adult human protagonist"
    
    # Объединяем JSON части, добавляя персонажей
    combined_parts = {**dop_json, **art_json, **sound_json}
    if character_description:
        combined_parts["character"] = character_description

    pipeline_result["steps"]["dop"] = dop_res if not isinstance(dop_res, Exception) else {"status": "failed"}
    pipeline_result["steps"]["art_director"] = art_res if not isinstance(art_res, Exception) else {"status": "failed"}
    pipeline_result["steps"]["sound_director"] = sound_res if not isinstance(sound_res, Exception) else {"status": "failed"}

    # Шаг 5: Storyboarder собирает JSON в промпт
    await _post_discussion("[CONVEYOR] Шаг 5: Storyboarder собирает промпт", "system", "orchestrator")
    if progress_callback:
        await progress_callback("Storyboarder собирает промпт...", 70)
    context_guard = {
        "writer_text": writer_result.get("result", "") if isinstance(writer_result, dict) else "",
        "task_text": pdf_context,
        "hr_text": hr_result.get("result", "") if isinstance(hr_result, dict) else "",
    }

    # Структурная карточка кадра (source of truth)
    prompt_parts = _build_strict_image_parts(combined_parts)
    prompt_parts["subject"] = _sanitize_subject_leakage(prompt_parts.get("subject", ""), context_guard)
    prompt_parts["source"] = {
        "dop": dop_json,
        "art": art_json,
        "sound": sound_json,
    }

    final_prompt = _compose_image_prompt(prompt_parts)
    final_prompt = _sanitize_entity_leakage(final_prompt, context_guard)
    
    # Добавляем промпт в результат
    pipeline_result["final_prompt"] = final_prompt
    pipeline_result["prompt_parts"] = prompt_parts

    # Шаг 6: Art Director → Kie.ai → изображение → CV авто-проверка
    await _post_discussion("[CONVEYOR] Шаг 6: Генерация изображений (Z-Image Turbo)", "system", "orchestrator")
    if progress_callback:
        await progress_callback("Kie.ai генерирует изображение...", 80)
    image_result = await _generate_and_review(final_prompt, task_id)
    pipeline_result["steps"]["image_generation"] = image_result

    # Шаг 6.5: CV авто-проверка через Gemini Vision
    if image_result.get("status") == "approved" and image_result.get("image_url"):
        await _post_discussion("[CONVEYOR] Шаг 6.5: CV авто-проверка изображения...", "system", "orchestrator")
        if progress_callback:
            await progress_callback("CV проверка изображения...", 85)
        
        cv_result = await _cv_auto_check(
            image_url=image_result["image_url"],
            writer_text=writer_result.get("result", ""),
            final_prompt=final_prompt,
            task_id=task_id,
        )
        
        pipeline_result["cv_check"] = cv_result
        
        # Если CV улучшил изображение — используем его
        if cv_result.get("image_url") and cv_result["image_url"] != image_result.get("image_url"):
            image_result["image_url"] = cv_result["image_url"]
            final_prompt = cv_result.get("final_prompt", final_prompt)
            await _post_discussion(
                f"[CONVEYOR] CV улучшил изображение: score={cv_result.get('score', 0)}/10 за {cv_result.get('attempts', 0)} попыток",
                "system", "orchestrator"
            )
        else:
            await _post_discussion(
                f"[CONVEYOR] CV результат: score={cv_result.get('score', 0)}/10",
                "system", "orchestrator"
            )
    else:
        cv_result = {"score": 0, "description": "Image generation failed", "matched": [], "missing": [], "attempts": 0}
        pipeline_result["cv_check"] = cv_result

    # Шаг 6.6: Проверка консистентности персонажей
    if image_result.get("image_url") and hr_result.get("result"):
        await _post_discussion("[CONVEYOR] Шаг 6.6: Проверка консистентности персонажей...", "system", "orchestrator")
        if progress_callback:
            await progress_callback("Проверка консистентности персонажей...", 90)
        
        # Извлекаем персонажей из HR результата
        hr_characters = _extract_json_array(hr_result.get("result", ""))
        
        consistency_result = await _check_character_consistency(
            image_url=image_result["image_url"],
            characters_data=hr_characters,
            writer_text=writer_result.get("result", ""),
        )
        
        pipeline_result["consistency_check"] = consistency_result
        
        if consistency_result.get("issues"):
            issues_text = _safe_text_list(consistency_result.get("issues", []))
            await _post_discussion(
                f"[CONVEYOR] ⚠️ Проблемы консистентности: {', '.join(issues_text[:3])}",
                "system", "orchestrator"
            )
        else:
            await _post_discussion(
                f"[CONVEYOR] ✅ Консистентность персонажей: {consistency_result.get('score', 0)}/10",
                "system", "orchestrator"
            )
    else:
        consistency_result = {"score": 0, "issues": ["No characters or image"], "characters_checked": 0}
        pipeline_result["consistency_check"] = consistency_result

    # Шаг 7: Storyboarder → финальная сцена
    await _post_discussion("[CONVEYOR] Шаг 7: Финальная сборка сцены", "system", "orchestrator")
    final_result = await run_step_with_critic("storyboarder",
        "Собери все утверждённые кадры в финальную сцену. Хронологический порядок.",
        {"final_prompt": pipeline_result.get("final_prompt", ""), "image": image_result.get("result", "")}, task_id)
    pipeline_result["steps"]["final_assembly"] = final_result

    pipeline_result["status"] = "completed"
    try:
        write_event(
            agent_id="orchestrator",
            event_type="pipeline_complete",
            result=f"scene={season}x{episode}:{scene_num}:completed",
            status="success",
            task_id=task_id,
        )
        log_med_action("pipeline_completed", f"Scene pipeline completed: {season}x{episode}:{scene_num}", "orchestrator")
    except Exception:
        pass

    # === СОХРАНЕНИЕ В БД ===
    for retry in range(3):
        try:
            async with async_session() as session:
                frames = await crud.get_scene_frames(session, season, episode, scene_num)
                if frames:
                    frame = frames[0]
                    frame_id = frame.id
                else:
                    new_frame = await crud.create_scene_frame(session, {
                        "season_num": season, "episode_num": episode, "scene_num": scene_num,
                        "frame_num": 1, "status": "draft",
                        "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat(),
                    })
                    frame_id = new_frame.id

                await crud.update_scene_frame(session, frame_id, {
                    "writer_text": writer_result.get("result", "")[:4000],
                    "director_notes": director_result.get("result", "")[:4000],
                    "characters_json": json.dumps(hr_result.get("result", ""), ensure_ascii=False)[:4000],
                    "dop_prompt": json.dumps(dop_json, ensure_ascii=False)[:4000],
                    "art_prompt": json.dumps(art_json, ensure_ascii=False)[:4000],
                    "sound_prompt": json.dumps(sound_json, ensure_ascii=False)[:4000],
                    "prompt_parts_json": json.dumps(prompt_parts, ensure_ascii=False)[:8000],
                    "final_prompt": str(image_result.get("used_prompt") or final_prompt)[:8000],
                    "image_url": image_result.get("image_url", "")[:500],
                    "critic_feedback": image_result.get("critic_feedback", "")[:2000],
                    "cv_score": cv_result.get("score", 0),
                    "cv_description": cv_result.get("description", "")[:2000],
                    "cv_details": json.dumps({
                        "matched": cv_result.get("matched", []),
                        "missing": cv_result.get("missing", []),
                        "attempts": cv_result.get("attempts", 0),
                        "history": cv_result.get("history", []),
                    }, ensure_ascii=False)[:5000],
                    "consistency_score": consistency_result.get("score", 0),
                    "consistency_issues": json.dumps({
                        "issues": consistency_result.get("issues", []),
                        "characters_checked": consistency_result.get("characters_checked", 0),
                        "checks": consistency_result.get("checks", []),
                    }, ensure_ascii=False)[:3000],
                    "status": "approved" if image_result.get("status") == "approved" else "in_review",
                    "updated_at": datetime.now().isoformat(),
                })
                await _post_discussion(f"[CONVEYOR] Результаты сцены {season}x{episode}:{scene_num} сохранены в БД", "system", "orchestrator")
                break
        except Exception as e:
            if retry < 2:
                import asyncio
                await asyncio.sleep(2)
            else:
                await _post_discussion(f"[CONVEYOR] Ошибка сохранения в БД: {str(e)}", "system", "orchestrator")

    await _post_discussion(f"[CONVEYOR] Сцена {season}x{episode}:{scene_num} завершена!", "system", "orchestrator")

    return pipeline_result


async def _create_character_pattern(characters_text: str, db):
    """
    Legacy compatibility wrapper.
    Раньше записывал глобальный паттерн в patterns.json (утечка контекста между сценами).
    Теперь НЕ пишет в глобальные файлы — используем scene-local правило в art_prompt.
    """
    await _post_discussion(
        "[CONVEYOR] Character consistency rule применён локально к текущей сцене (без записи в global patterns)",
        "system",
        "hr_agent"
    )


async def _generate_and_review(prompt: str, task_id: str) -> dict:
    """Отправить промпт в Kie.ai и оценить результат через Critic."""
    if not prompt:
        return {"status": "failed", "result": "Нет промпта для генерации"}

    # Финальная страховка: prompt должен остаться image-only
    prompt = _safe_text(prompt).strip()
    if "single still frame" not in prompt.lower():
        prompt = f"{prompt}, single still frame, static composition, no camera movement, no transitions"

    # Генерация через Kie.ai (без negative_prompt для Z-Image Turbo)
    from tools.kieai_tool import generate_image
    
    await _post_discussion(f"[KIE.AI] Отправка image-prompt ({len(prompt)} символов): {prompt[:280]}", "system", "art_director")
    
    result = await generate_image(
        prompt=prompt[:4000],
        negative_prompt="",  # Z-Image Turbo игнорирует negative prompt
        width=1024, height=576, steps=30, cfg_scale=7.0, seed=-1  # 16:9 формат
    )
    
    await _post_discussion(f"[KIE.AI] Статус: {result.status}, URL: {result.result_url[:50] if result.result_url else 'None'}", "system", "art_director")

    if result.status != "success":
        error_msg = f"Генерация не удалась: {result.error}"
        await _post_discussion(f"[KIE.AI] ОШИБКА: {error_msg}", "system", "art_director")
        try:
            set_agent_error("art_director")
            write_event(
                agent_id="art_director",
                event_type="tool_call",
                result=error_msg,
                status="fail",
                task_id=task_id,
                target_agent_id="tools:kieai",
            )
            log_med_action("tool_failure", f"Kie.ai failed for {task_id}: {error_msg[:200]}", "art_director")
            await run_evaluation(
                task_result=error_msg,
                agent_id="art_director",
                task_description=f"Kie.ai image generation for {task_id}",
            )
        except Exception:
            pass
        return {"status": "failed", "result": error_msg, "image_url": "", "critic_feedback": ""}

    # Critic оценивает изображение (по описанию)
    passed, feedback = await _run_critic(
        f"Сгенерированное изображение по промпту:\n{prompt[:2000]}\nURL: {result.result_url}",
        task_id, "art_director"
    )

    return {
        "status": "approved" if passed else "needs_review",
        "result": result.result_url,
        "image_url": result.result_url,
        "critic_feedback": feedback,
        "used_prompt": prompt,
    }
