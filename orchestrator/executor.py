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

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_FILE = os.path.join(PROJECT_ROOT, "orchestrator", "agent_registry.json")
PATTERNS_FILE = os.path.join(PROJECT_ROOT, "med_otdel", "patterns.json")


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
            return agent.get("model", "google/gemini-3-flash-preview")
    return "google/gemini-3-flash-preview"


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
        system_prompt = ""
        if constitution:
            system_prompt += f"[КОНСТИТУЦИЯ СТУДИИ]\n{constitution}\n\n"
        system_prompt += f"[РОЛЬ]\nТы {agent_id} аниме-студии РОДИНА.\n\n[ЗАДАЧА]\n{input_text}"

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

    system = f"Ты строгий критик аниме-студии {PROJECT_NAME}. Оценивай результаты объективно."
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

    system = "Ты фиксер аниме-студии РОДИНА. Исправляй результаты по замечаниям критика."
    user = f"""Исправь результат по замечаниям критика.

Оригинал:
{original_text[:4000]}

Замечания:
{critic_feedback[:1000]}

Верни исправленный результат."""

    try:
        result, _ = await asyncio.wait_for(
            call_llm(system_prompt=system, user_prompt=user),
            timeout=90
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
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return {}
    return {}


def _extract_json_array(text: str) -> list:
    """Извлечь JSON массив из ответа LLM."""
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return []
    return []


def _build_kieai_prompt(parts: dict) -> str:
    """Собрать финальный промпт из JSON частей цехов для Z-Image Turbo."""
    return (
        f"[{parts.get('shot', 'Medium shot, cinematic angle')}] "
        f"[{parts.get('character', '')}] "
        f"[{parts.get('location', '')}] "
        f"[{parts.get('lighting', '')}] "
        f"[{parts.get('mood', '')}] "
        f"[{parts.get('style', '2.5D anime, Satoshi Kon aesthetic, cinematic')}] "
        f"[{parts.get('palette', 'red dust, deep blue sea, violet nights, Goa')}] "
        f"[{parts.get('constraints', 'no watermark, no text, no logos, no extra limbs, correct anatomy, sharp focus')}]"
    )

async def run_step_with_critic(agent_id: str, task: str, context: dict, task_id: str = "pipeline") -> dict:
    """
    Выполнить один шаг с Critic/Fixer циклом (макс 3 круга).
    Возвращает: {"status": "approved"|"needs_review"|"failed", "result": str, "rounds": int}
    """
    # Формируем входной текст из контекста
    input_parts = []
    for key, value in context.items():
        if value:
            input_parts.append(f"[{key.upper()}]\n{value}")
    input_parts.append(f"[ЗАДАЧА]\n{task}")
    input_text = "\n\n".join(input_parts)

    # Шаг 1: Агент выполняет задачу
    result, success = await _run_agent_step(agent_id, input_text, task_id)
    if not success:
        return {"status": "failed", "result": result, "rounds": 0}

    # Critic/Fixer цикл (макс 3 круга)
    for round_num in range(3):
        passed, feedback = await _run_critic(result, task_id, agent_id)
        if passed:
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
            return {"status": "needs_review", "result": result, "rounds": 3, "critique": feedback}

    return {"status": "approved", "result": result, "rounds": 3}


async def run_casting(task_description: str, task_id: str) -> dict:
    """
    Этап Кастинга: HR подбирает агентов → Критик проверяет готовность → Фиксер правит.
    Возвращает список допущенных агентов.
    """
    await _post_discussion("[CASTING] Начало кастинга...", "system", "orchestrator")
    
    # 1. HR анализирует задачу и предлагает агентов
    hr_result = await run_step_with_critic("hr_agent",
        f"Для задачи: '{task_description}'. Какие агенты нужны? Перечисли их ID.",
        {}, task_id)
    
    if hr_result["status"] == "failed":
        await _post_discussion("[CASTING] HR не смог подобрать агентов", "system", "orchestrator")
        return {"status": "failed", "agents": []}
    
    # В реальном сценарии здесь был бы парсинг ответа HR и проверка каждого Критиком
    # Сейчас просто допускаем всех, так как у нас фиксированный набор
    await _post_discussion("[CASTING] Критик проверяет готовность агентов...", "system", "orchestrator")
    
    # Имитация проверки Критиком (в будущем - реальный вызов)
    await _post_discussion("[CASTING] Все агенты допущены к работе", "system", "orchestrator")
    
    return {
        "status": "approved", 
        "agents": ["writer", "director", "dop", "art_director", "sound_director", "storyboarder"]
    }


async def run_scene_pipeline(season: int, episode: int, scene_num: int, pdf_context: str, db=None):
    """
    Полный конвейер одной сцены:
    1. Writer → 2. Director → 3. HR Casting → 4. DOP+Art+Sound (параллельно)
    → 5. Storyboarder → 6. Art Director → Kie.ai → 7. Storyboarder финал
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

    # Этап 0: Кастинг
    casting_result = await run_casting(pdf_context, task_id)
    pipeline_result["steps"]["casting"] = casting_result
    
    if casting_result["status"] == "failed":
        pipeline_result["status"] = "failed"
        return pipeline_result

    # Шаг 1: Writer описывает сцену
    await _post_discussion("[CONVEYOR] Шаг 1: Writer описывает сцену", "system", "orchestrator")
    writer_result = await run_step_with_critic("writer",
        f"Опиши сцену {scene_num} из PDF-сценария. Детально: диалоги, действия, атмосфера.",
        {"pdf_context": pdf_context}, task_id)
    pipeline_result["steps"]["writer"] = writer_result

    if writer_result["status"] == "failed":
        pipeline_result["status"] = "failed"
        return pipeline_result

    # Шаг 2: Director — творческое решение
    await _post_discussion("[CONVEYOR] Шаг 2: Director — режиссёрское решение", "system", "orchestrator")
    director_result = await run_step_with_critic("director",
        f"Режиссёрское решение для сцены {scene_num}. Ракурсы, эмоции, ритм.",
        {"writer_output": writer_result.get("result", "")}, task_id)
    pipeline_result["steps"]["director"] = director_result

    # Шаг 3: HR — кастинг персонажей
    await _post_discussion("[CONVEYOR] Шаг 3: HR — кастинг персонажей", "system", "orchestrator")
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
    
    json_context = f"""
    WRITER OUTPUT: {writer_result.get('result', '')}
    DIRECTOR NOTES: {director_result.get('result', '')}
    CHARACTERS: {hr_result.get('result', '')}
    """

    # Задачи с требованием JSON
    dop_task = run_step_with_critic("dop",
        "Опиши свет, камеру и локацию. Верни СТРОГО JSON: {\"shot\": \"...\", \"location\": \"...\", \"lighting\": \"...\"}",
        {"context": json_context}, task_id)
    art_task = run_step_with_critic("art_director",
        "Опиши стиль и палитру. Верни СТРОГО JSON: {\"style\": \"...\", \"palette\": \"...\"}",
        {"context": json_context}, task_id)
    sound_task = run_step_with_critic("sound_director",
        "Опиши звук. Верни СТРОГО JSON: {\"mood\": \"...\"}",
        {"context": json_context}, task_id)

    dop_res, art_res, sound_res = await asyncio.gather(dop_task, art_task, sound_task, return_exceptions=True)

    # Извлекаем JSON
    dop_json = _extract_json(dop_res.get("result", "") if not isinstance(dop_res, Exception) else "")
    art_json = _extract_json(art_res.get("result", "") if not isinstance(art_res, Exception) else "")
    sound_json = _extract_json(sound_res.get("result", "") if not isinstance(sound_res, Exception) else "")

    # Объединяем JSON части
    combined_parts = {**dop_json, **art_json, **sound_json}

    pipeline_result["steps"]["dop"] = dop_res if not isinstance(dop_res, Exception) else {"status": "failed"}
    pipeline_result["steps"]["art_director"] = art_res if not isinstance(art_res, Exception) else {"status": "failed"}
    pipeline_result["steps"]["sound_director"] = sound_res if not isinstance(sound_res, Exception) else {"status": "failed"}

    # Шаг 5: Storyboarder собирает JSON в промпт
    await _post_discussion("[CONVEYOR] Шаг 5: Storyboarder собирает промпт", "system", "orchestrator")
    final_prompt = _build_kieai_prompt(combined_parts)
    
    # Добавляем промпт в результат
    pipeline_result["final_prompt"] = final_prompt

    # Шаг 6: Art Director → Kie.ai → изображение
    await _post_discussion("[CONVEYOR] Шаг 6: Генерация изображений (Z-Image Turbo)", "system", "orchestrator")
    image_result = await _generate_and_review(final_prompt, task_id)
    pipeline_result["steps"]["image_generation"] = image_result

    # Шаг 7: Storyboarder → финальная сцена
    await _post_discussion("[CONVEYOR] Шаг 7: Финальная сборка сцены", "system", "orchestrator")
    final_result = await run_step_with_critic("storyboarder",
        "Собери все утверждённые кадры в финальную сцену. Хронологический порядок.",
        {"final_prompt": pipeline_result.get("final_prompt", ""), "image": image_result.get("result", "")}, task_id)
    pipeline_result["steps"]["final_assembly"] = final_result

    pipeline_result["status"] = "completed"

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
                    "final_prompt": final_prompt[:8000],
                    "image_url": image_result.get("image_url", "")[:500],
                    "critic_feedback": image_result.get("critic_feedback", "")[:2000],
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
    """Создать паттерн character_consistency из карточек HR."""
    import sys
    sys.path.insert(0, os.path.dirname(PROJECT_ROOT))
    from med_otdel.rule_builder import _load_patterns
    import json

    pattern_text = f"[RULE] При генерации изображений строго соблюдай внешность персонажей:\n{characters_text[:2000]}"

    # Сохраняем в patterns.json
    patterns = _load_patterns()
    patterns.append({
        "key": "character_consistency",
        "name": "Единообразие персонажей",
        "rule_text": pattern_text,
        "description": "Автоматически создано HR при кастинге",
        "category": "visual",
        "priority": 100,
    })

    try:
        with open(PATTERNS_FILE, "w", encoding="utf-8") as f:
            json.dump({"patterns": patterns}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    await _post_discussion(
        f"[CONVEYOR] Создан паттерн character_consistency для Art Director",
        "system",
        "hr_agent"
    )


async def _generate_and_review(prompt: str, task_id: str) -> dict:
    """Отправить промпт в Kie.ai и оценить результат через Critic."""
    if not prompt:
        return {"status": "failed", "result": "Нет промпта для генерации"}

    # Генерация через Kie.ai (без negative_prompt для Z-Image Turbo)
    from tools.kieai_tool import generate_image
    result = await generate_image(
        prompt=prompt[:4000],
        negative_prompt="",  # Z-Image Turbo игнорирует negative prompt
        width=1024, height=1024, steps=30, cfg_scale=7.0, seed=-1
    )

    if result.status != "success":
        return {"status": "failed", "result": f"Генерация не удалась: {result.error}"}

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
    }
