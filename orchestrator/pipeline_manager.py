"""
Pipeline Manager — управление конвейером сцен.
Вынесено из orchestrator/executor.py для улучшения поддерживаемости.
"""
import json
import asyncio
from datetime import datetime

from config import PROJECT_NAME
from orchestrator.task_chain import TaskChain, AgentStep
from orchestrator.progress_tracker import tracker
from orchestrator.executor_helpers import _post_discussion, _load_full_project_context
from orchestrator.prompt_builder import (
    _extract_json, _extract_json_array, _extract_names_to_remove,
    _safe_text, _safe_text_list, _build_strict_image_parts,
    _compose_image_prompt, _sanitize_subject_leakage,
    _sanitize_entity_leakage, _build_strict_image_prompt,
)
from orchestrator.agent_runner import _run_agent_step, _summarize_for_next_agent
from orchestrator.critic_fixer import _run_critic, _run_fixer, run_step_with_critic
from med_otdel.med_core import write_event, run_evaluation, log_med_action
from med_otdel.studio_monitor import set_agent_error, reset_agent_error


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
                input_text = await _summarize_for_next_agent(previous_output, next_agent_id, chain.task_id)
            else:
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
                original_output = output
                for fix_attempt in range(3):
                    if tracker.is_cancelled(chain.task_id):
                        chain.status = "cancelled"
                        chain.completed_at = datetime.now().isoformat()
                        tracker.update_task(chain)
                        return

                    step.fix_attempts = fix_attempt + 1
                    fixed_output = await _run_fixer(output, feedback, chain.task_id)

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
                    step.status = "degraded"
                    step.output = original_output
                    await _post_discussion(
                        f"[ORCHESTRATOR] Шаг {i+1} ({step.agent_id}) выполнен с ошибками (degraded). Fixer не смог исправить 3 раза.",
                        "system",
                        "orchestrator"
                    )
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

    chain.status = "completed"
    chain.result = previous_output
    chain.completed_at = datetime.now().isoformat()
    tracker.update_task(chain)

    await _post_discussion(
        f"[ORCHESTRATOR] Задача '{chain.description}' завершена успешно.",
        "system",
        "orchestrator"
    )


async def run_casting(pdf_context: str, task_id: str, db=None) -> dict:
    """
    Этап Кастинга: HR извлекает персонажей из PDF → Critic сверяет с текстом → Fixer исправляет галлюцинации.
    Возвращает список персонажей и сохраняет в БД.
    """
    import crud
    from database import async_session

    await _post_discussion("[CASTING] Начало кастинга — извлечение персонажей из сценария...", "system", "orchestrator")

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

    characters_data = _extract_json_array(hr_result)

    await _post_discussion(
        f"[FULL_CASTING] HR вернул {len(hr_result)} символов, извлечено {len(characters_data)} персонажей",
        "system", "orchestrator")

    if not characters_data:
        await _post_discussion("[FULL_CASTING] Не удалось извлечь JSON из ответа HR", "system", "orchestrator")
        await _post_discussion(f"[FULL_CASTING] HR output: {hr_result[:500]}", "system", "orchestrator")
        return []

    critic_passed = False
    critic_feedback = ""
    characters_to_save = characters_data

    await _post_discussion("[FULL_CASTING] Critic сверяет персонажей с PDF сценария...", "system", "orchestrator")

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
        "full_casting_task", "critic")

    if passed:
        critic_passed = True
        await _post_discussion(f"[FULL_CASTING] Critic: PASS. Все {len(characters_data)} персонажей подтверждены.", "system", "orchestrator")
    else:
        critic_feedback = feedback
        await _post_discussion(f"[FULL_CASTING] Critic: FAIL. {feedback[:200]}", "system", "orchestrator")

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

    saved_count = 0

    if characters_to_save and db:
        for char_data in characters_to_save:
            name = char_data.get("name", "")
            if not name:
                await _post_discussion(f"[FULL_CASTING] WARNING: Character with empty name skipped: {char_data}", "system", "orchestrator")
                continue
            
            await _post_discussion(f"[FULL_CASTING] Saving character: name='{name}' (type: {type(name)}, length: {len(name)})", "system", "orchestrator")
            
            try:
                character_data = {
                    "name": str(name).strip(),
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

    prompt = _safe_text(prompt).strip()
    if "single still frame" not in prompt.lower():
        prompt = f"{prompt}, single still frame, static composition, no camera movement, no transitions"

    from tools.kieai_tool import generate_image
    
    await _post_discussion(f"[KIE.AI] Отправка image-prompt ({len(prompt)} символов): {prompt[:280]}", "system", "art_director")
    
    result = await generate_image(
        prompt=prompt[:4000],
        negative_prompt="",
        width=1024, height=576, steps=30, cfg_scale=7.0, seed=-1
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


async def run_scene_pipeline(season: int, episode: int, scene_num: int, pdf_context: str, db=None, progress_callback=None):
    """
    Полный конвейер одной сцены:
    1. Writer → 2. Director → 3. HR Casting → 4. DOP+Art+Sound (параллельно)
    → 5. Storyboarder → 6. Art Director → Kie.ai → 7. Storyboarder финал
    
    progress_callback: optional async callable(step_name: str, progress: int)
    """
    import crud
    from database import async_session
    from orchestrator.cv_checker import _cv_auto_check, _check_character_consistency

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

    await _post_discussion("[CONVEYOR] Шаг 2: Director — режиссёрское решение", "system", "orchestrator")
    if progress_callback:
        await progress_callback("Director принимает режиссёрское решение...", 30)
    director_result = await run_step_with_critic("director",
        f"Режиссёрское решение для сцены {scene_num}. Ракурсы, эмоции, ритм.",
        {"writer_output": writer_result.get("result", "")}, task_id)
    pipeline_result["steps"]["director"] = director_result

    await _post_discussion("[CONVEYOR] Шаг 3: HR — кастинг персонажей", "system", "orchestrator")
    if progress_callback:
        await progress_callback("HR кастинг персонажей...", 40)
    hr_result = await run_step_with_critic("hr_agent",
        f"Создай карточки персонажей сцены {scene_num}. Для каждого: имя, возраст, внешность, одежда, манера речи. Верни СТРОГО JSON массив: [{{\"name\": \"...\", \"age\": 20, \"appearance\": \"...\", \"clothing\": \"...\", \"speech\": \"...\"}}]",
        {"writer_output": writer_result.get("result", "")}, task_id)
    pipeline_result["steps"]["hr_casting"] = hr_result

    if hr_result["status"] in ("approved", "needs_review"):
        hr_text = hr_result.get("result", "")
        characters_data = _extract_json_array(hr_text)
        if characters_data and db:
            for char_data in characters_data:
                try:
                    await crud.create_character(db, {
                        "project_id": 1,
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

    if hr_result["status"] == "approved":
        await _create_character_pattern(hr_result.get("result", ""), db)

    await _post_discussion("[CONVEYOR] Шаг 4: Параллельная работа цехов (JSON)", "system", "orchestrator")
    if progress_callback:
        await progress_callback("DOP, Art Director, Sound Director работают...", 55)
    
    json_context = f"""
    WRITER OUTPUT: {writer_result.get('result', '')}
    DIRECTOR NOTES: {director_result.get('result', '')}
    CHARACTERS: {hr_result.get('result', '')}
    """

    dop_res = await run_step_with_critic("dop",
        "Опиши свет, камеру и локацию. Верни СТРОГО JSON: {\"shot\": \"...\", \"location\": \"...\", \"lighting\": \"...\"}",
        {"context": json_context}, task_id)
    art_res = await run_step_with_critic("art_director",
        "Опиши стиль и палитру. Верни СТРОГО JSON: {\"style\": \"...\", \"palette\": \"...\"}",
        {"context": json_context}, task_id)
    sound_res = await run_step_with_critic("sound_director",
        "Опиши звук. Верни СТРОГО JSON: {\"mood\": \"...\"}",
        {"context": json_context}, task_id)

    dop_json = _extract_json(dop_res.get("result", "") if isinstance(dop_res, dict) else "")
    art_json = _extract_json(art_res.get("result", "") if isinstance(art_res, dict) else "")
    sound_json = _extract_json(sound_res.get("result", "") if isinstance(sound_res, dict) else "")

    hr_characters = _extract_json_array(hr_result.get("result", "") if isinstance(hr_result, dict) else "")
    
    character_description = ""
    if hr_characters:
        main_char = hr_characters[0]
        char_parts = []
        if main_char.get("name"):
            char_parts.append(main_char["name"])
        if main_char.get("appearance"):
            char_parts.append(main_char["appearance"])
        if main_char.get("clothing"):
            char_parts.append(f"одежда: {main_char['clothing']}")
        character_description = ", ".join(char_parts) if char_parts else "adult human protagonist"
    
    combined_parts = {**dop_json, **art_json, **sound_json}
    if character_description:
        combined_parts["character"] = character_description

    pipeline_result["steps"]["dop"] = dop_res if not isinstance(dop_res, Exception) else {"status": "failed"}
    pipeline_result["steps"]["art_director"] = art_res if not isinstance(art_res, Exception) else {"status": "failed"}
    pipeline_result["steps"]["sound_director"] = sound_res if not isinstance(sound_res, Exception) else {"status": "failed"}

    await _post_discussion("[CONVEYOR] Шаг 5: Storyboarder собирает промпт", "system", "orchestrator")
    if progress_callback:
        await progress_callback("Storyboarder собирает промпт...", 70)
    context_guard = {
        "writer_text": writer_result.get("result", "") if isinstance(writer_result, dict) else "",
        "task_text": pdf_context,
        "hr_text": hr_result.get("result", "") if isinstance(hr_result, dict) else "",
    }

    prompt_parts = _build_strict_image_parts(combined_parts)
    prompt_parts["subject"] = _sanitize_subject_leakage(prompt_parts.get("subject", ""), context_guard)
    prompt_parts["source"] = {
        "dop": dop_json,
        "art": art_json,
        "sound": sound_json,
    }

    final_prompt = _compose_image_prompt(prompt_parts)
    final_prompt = _sanitize_entity_leakage(final_prompt, context_guard)
    
    pipeline_result["final_prompt"] = final_prompt
    pipeline_result["prompt_parts"] = prompt_parts

    await _post_discussion("[CONVEYOR] Шаг 6: Генерация изображений (Z-Image Turbo)", "system", "orchestrator")
    if progress_callback:
        await progress_callback("Kie.ai генерирует изображение...", 80)
    image_result = await _generate_and_review(final_prompt, task_id)
    pipeline_result["steps"]["image_generation"] = image_result

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

    if image_result.get("image_url") and hr_result.get("result"):
        await _post_discussion("[CONVEYOR] Шаг 6.6: Проверка консистентности персонажей...", "system", "orchestrator")
        if progress_callback:
            await progress_callback("Проверка консистентности персонажей...", 90)
        
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
                await asyncio.sleep(2)
            else:
                await _post_discussion(f"[CONVEYOR] Ошибка сохранения в БД: {str(e)}", "system", "orchestrator")

    await _post_discussion(f"[CONVEYOR] Сцена {season}x{episode}:{scene_num} завершена!", "system", "orchestrator")

    return pipeline_result
