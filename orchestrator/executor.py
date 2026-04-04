"""
Orchestrator Executor — ядро выполнения цепочки задач.
Выполняет: agent → summarize → critic → fixer цикл.
"""
import asyncio
import json
import os
from datetime import datetime

from config import OPENROUTER_API_KEY
from orchestrator.task_chain import TaskChain, AgentStep
from orchestrator.progress_tracker import tracker
from med_otdel.agent_memory import call_llm

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_FILE = os.path.join(PROJECT_ROOT, "orchestrator", "agent_registry.json")


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

    system = "Ты строгий критик аниме-студии РОДИНА. Оценивай результаты объективно."
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
