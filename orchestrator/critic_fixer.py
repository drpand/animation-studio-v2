"""
Critic/Fixer — цикл оценки и исправления результатов агентов.
Вынесено из orchestrator/executor.py для улучшения поддерживаемости.
"""
import asyncio
from datetime import datetime

from orchestrator.progress_tracker import tracker
from orchestrator.executor_helpers import _post_discussion, _load_full_project_context
from med_otdel.agent_memory import call_llm


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
            timeout=120
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


async def run_step_with_critic(agent_id: str, task: str, context: dict, task_id: str = "pipeline") -> dict:
    """
    Выполнить один шаг с Critic/Fixer циклом (макс 3 круга).
    Возвращает: {"status": "approved"|"needs_review"|"failed", "result": str, "rounds": int}
    """
    from orchestrator.prompt_builder import _safe_text
    from orchestrator.agent_runner import _run_agent_step
    from med_otdel.med_core import write_event, run_evaluation
    from med_otdel.studio_monitor import set_agent_error, reset_agent_error

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
            from med_otdel.med_core import log_med_action
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


def _extract_names_to_remove(feedback: str) -> list:
    """Извлечь имена персонажей для удаления из feedback Critic."""
    import re
    names = []
    for line in feedback.split('\n'):
        line = line.strip()
        if any(kw in line.lower() for kw in ['галлюцин', 'удал', 'нет в тексте', 'не упоминается', 'выдуман']):
            # Ищем имена в кавычках или после тире
            quoted = re.findall(r'["«"]([^"»"]+)["»"]', line)
            names.extend(quoted)
    return names
