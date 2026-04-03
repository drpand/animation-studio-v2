"""
Med Core — оркестратор МЕД-ОТДЕЛА.
Управляет тремя режимами: agent_heal, chain_heal, studio_alert.
"""
import os
import json
import tempfile
import uuid
import threading
from datetime import datetime
from typing import Optional

from config import OPENROUTER_API_KEY
from med_otdel.agent_memory import AgentMemory, call_llm
from med_otdel.chain_analyzer import analyze_chains, get_chain_heal_prompt
from med_otdel.studio_monitor import check_studio_health, set_agent_error, reset_agent_error

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_BUS_FILE = os.path.join(PROJECT_ROOT, "memory", "events_bus.json")
MED_LOG_FILE = os.path.join(PROJECT_ROOT, "memory", "med_log.json")
AGENTS_STATE_FILE = os.path.join(PROJECT_ROOT, "memory", "agents_state.json")

# Блокировка для атомарной записи
_bus_lock = threading.Lock()
_log_lock = threading.Lock()


def _atomic_write_json(filepath: str, data: dict):
    """Атомарная запись JSON через временный файл + os.replace()."""
    dir_name = os.path.dirname(filepath)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _load_bus() -> dict:
    if not os.path.exists(EVENTS_BUS_FILE):
        return {"events": []}
    with open(EVENTS_BUS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_log() -> dict:
    if not os.path.exists(MED_LOG_FILE):
        return {"entries": []}
    with open(MED_LOG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_agents_state() -> dict:
    if not os.path.exists(AGENTS_STATE_FILE):
        return {}
    with open(AGENTS_STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def write_event(agent_id: str, event_type: str, result: str, status: str,
                task_id: str = "", target_agent_id: str = "") -> str:
    """
    Атомарно записать событие в шину.
    Возвращает event_id.
    """
    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    if not task_id:
        task_id = f"task_{uuid.uuid4().hex[:8]}"

    event = {
        "id": event_id,
        "task_id": task_id,
        "timestamp": datetime.now().isoformat(),
        "agent_id": agent_id,
        "event_type": event_type,
        "result": result[:5000],
        "status": status,
    }
    if target_agent_id:
        event["target_agent_id"] = target_agent_id

    with _bus_lock:
        bus = _load_bus()
        bus["events"].append(event)
        # Храним последние 200 событий
        if len(bus["events"]) > 200:
            bus["events"] = bus["events"][-200:]
        _atomic_write_json(EVENTS_BUS_FILE, bus)

    return event_id


def log_med_action(action: str, details: str, agent_id: str = ""):
    """Записать действие в лог МЕД-ОТДЕЛА."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "details": details[:500],
        "agent_id": agent_id,
    }
    with _log_lock:
        log = _load_log()
        log["entries"].append(entry)
        if len(log["entries"]) > 100:
            log["entries"] = log["entries"][-100:]
        _atomic_write_json(MED_LOG_FILE, log)


async def run_evaluation(task_result: str, agent_id: str, task_description: str = "") -> dict:
    """
    Запустить Critic для оценки результата задачи.
    
    1. Записать событие task_completed в шину
    2. Запустить Critic через OpenRouter
    3. Записать результат оценки
    4. Проверить 3 режима МЕД-ОТДЕЛА
    
    Возвращает: {passed: bool, score: int, feedback: str, task_id: str}
    """
    # 1. Записываем событие выполнения задачи
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    write_event(
        agent_id=agent_id,
        event_type="task_completed",
        result=task_result,
        status="success",
        task_id=task_id,
    )

    # 2. Запускаем Critic
    critic_prompt = f"""Ты критик аниме-студии РОДИНА. Оцени результат работы агента.

Задача: {task_description or "Не указана"}
Результат агента:
{task_result[:4000]}

Оцени по шкале 1-10. Если оценка >= 7 — PASS, иначе FAIL.
Дай конкретную обратную связь — что хорошо, что нужно исправить.

Формат ответа:
SCORE: <число>
PASS/FAIL
FEEDBACK: <текст>"""

    response, _ = await call_llm(
        system_prompt="Ты строгий критик аниме-производства. Оценивай результаты объективно.",
        user_prompt=critic_prompt,
    )

    # 3. Парсим ответ Critic
    passed, score, feedback = _parse_critic_response(response)

    # 4. Записываем событие оценки
    eval_status = "pass" if passed else "fail"
    write_event(
        agent_id="critic",
        event_type="evaluation",
        result=feedback,
        status=eval_status,
        task_id=task_id,
        target_agent_id=agent_id,
    )

    # 5. Если fail — обновляем статус агента и записываем в память
    if not passed:
        set_agent_error(agent_id)

        # Записываем провал в память агента
        memory = AgentMemory(agent_id)
        memory.add_failure("evaluation_fail", feedback, {"task_id": task_id, "score": score})
        memory.save()  # Сохраняем на диск для последующего чтения
        memory.save()  # Сохраняем на диск для последующего чтения

        log_med_action("evaluation_fail", f"Агент {agent_id} провалил оценку: {feedback[:200]}", agent_id)

        # 6. Проверяем 3 режима МЕД-ОТДЕЛА
        await _check_all_modes(agent_id, task_id, feedback)
    else:
        reset_agent_error(agent_id)
        log_med_action("evaluation_pass", f"Агент {agent_id} прошёл оценку (score: {score})", agent_id)

    return {
        "passed": passed,
        "score": score,
        "feedback": feedback,
        "task_id": task_id,
        "raw_response": response,
    }


def _parse_critic_response(response: str) -> tuple[bool, int, str]:
    """Распарсить ответ Critic."""
    score = 5
    passed = False
    feedback = response

    for line in response.split("\n"):
        line_stripped = line.strip().upper()
        if line_stripped.startswith("SCORE:"):
            try:
                score = int("".join(c for c in line_stripped.replace("SCORE:", "").strip() if c.isdigit()))
            except ValueError:
                score = 5
        if "FAIL" in line_stripped and "PASS" not in line_stripped.replace("FAIL", ""):
            passed = False
        elif "PASS" in line_stripped:
            passed = True

    # Extract feedback
    for line in response.split("\n"):
        if line.strip().upper().startswith("FEEDBACK:"):
            feedback = line.strip()[len("FEEDBACK:"):].strip()
            break

    if score >= 7:
        passed = True

    return passed, score, feedback


async def _check_all_modes(agent_id: str, task_id: str, feedback: str):
    """Проверить все 3 режима МЕД-ОТДЕЛА."""
    # 1. agent_heal — проверить провалы агента
    await _check_agent_heal(agent_id, feedback)

    # 2. chain_heal — проверить цепочки
    await _check_chain_heal()

    # 3. studio_alert — проверить здоровье студии
    await _check_studio_alert()


async def _check_agent_heal(agent_id: str, feedback: str):
    """
    Режим agent_heal: если 2+ провала подряд у одного агента → эволюция.
    """
    memory = AgentMemory(agent_id)
    consecutive = memory.get_consecutive_failures()

    if consecutive >= 2:
        log_med_action("agent_heal_triggered",
                       f"Агент {agent_id}: {consecutive} провалов подряд → эволюция", agent_id)
        print(f"[МЕД-ОТДЕЛ] agent_heal: {agent_id} — {consecutive} провалов подряд")

        try:
            new_version = await memory.evolve_agent(agent_id, "evaluation_fail", feedback)

            # Обновляем промпт агента в agents_state.json
            new_prompt = memory.get_prompt()
            if new_prompt:
                state = _load_agents_state()
                if agent_id in state:
                    state[agent_id]["instructions"] = new_prompt
                    _atomic_write_json(AGENTS_STATE_FILE, state)

            log_med_action("agent_evolved",
                           f"Агент {agent_id} эволюционировал в {new_version}", agent_id)
            print(f"[МЕД-ОТДЕЛ] Агент {agent_id} эволюционировал → {new_version}")
        except Exception as e:
            log_med_action("evolution_error", f"Ошибка эволюции {agent_id}: {str(e)}", agent_id)
            print(f"[МЕД-ОТДЕЛ] Ошибка эволюции {agent_id}: {e}")


async def _check_chain_heal():
    """
    Режим chain_heal: если провалы на стыке двух агентов → эволюция формата.
    """
    chains = analyze_chains()

    for chain in chains:
        from_agent = chain["from_agent"]
        to_agent = chain["to_agent"]
        feedback = chain["last_feedback"]

        log_med_action("chain_heal_triggered",
                       f"Цепочка {from_agent}→{to_agent}: {chain['fail_count']} провалов",
                       f"{from_agent},{to_agent}")
        print(f"[МЕД-ОТДЕЛ] chain_heal: {from_agent}→{to_agent} — {chain['fail_count']} провалов")

        try:
            # Эволюционируем промпт принимающего агента
            memory = AgentMemory(to_agent)
            current_prompt = memory.get_prompt() or ""

            chain_rule = get_chain_heal_prompt(from_agent, to_agent, feedback)

            # Добавляем правило в начало промпта
            new_prompt = f"{chain_rule}\n\n{current_prompt}"
            new_prompt = new_prompt[:8000]

            memory.set_current_prompt(new_prompt)

            # Обновляем в agents_state.json
            state = _load_agents_state()
            if to_agent in state:
                state[to_agent]["instructions"] = new_prompt
                _atomic_write_json(AGENTS_STATE_FILE, state)

            log_med_action("chain_healed",
                           f"Цепочка {from_agent}→{to_agent} исправлена: обновлён промпт {to_agent}",
                           f"{from_agent},{to_agent}")
            print(f"[МЕД-ОТДЕЛ] chain_heal: {from_agent}→{to_agent} — промпт {to_agent} обновлён")
        except Exception as e:
            log_med_action("chain_heal_error", f"Ошибка chain_heal {from_agent}→{to_agent}: {str(e)}",
                           f"{from_agent},{to_agent}")
            print(f"[МЕД-ОТДЕЛ] Ошибка chain_heal: {e}")


async def _check_studio_alert():
    """
    Режим studio_alert: если 50%+ агентов в error → алерт.
    """
    health = check_studio_health()

    if health["status"] == "critical":
        log_med_action("studio_alert", health["alert_message"])
        print(f"[МЕД-ОТДЕЛ] studio_alert: {health['alert_message']}")


async def run_fix(original_result: str, critic_feedback: str) -> str:
    """
    Запустить Fixer для исправления результата по замечаниям Critic.
    """
    fix_prompt = f"""Ты фиксер аниме-студии РОДИНА. Исправь результат работы агента по замечаниям критика.

Оригинальный результат:
{original_result[:4000]}

Замечания критика:
{critic_feedback[:2000]}

Исправь результат, устранив все замечания. Верни только исправленный результат."""

    response, _ = await call_llm(
        system_prompt="Ты фиксер. Исправляй результаты по замечаниям критика. Сохраняй стиль и контекст.",
        user_prompt=fix_prompt,
    )

    return response


async def manual_evolve(agent_id: str) -> dict:
    """
    Ручная эволюция агента по запросу пользователя.
    """
    memory = AgentMemory(agent_id)
    current_version = memory.data.get("current_version", "v1")
    current_prompt = memory.get_prompt() or ""

    # Запрашиваем улучшение через OpenRouter
    system = "Ты эксперт по промпт-инженерии. Улучшай системные промпты AI-агентов."
    user = f"""Агент: {agent_id}
Текущая версия: {current_version}
Текущий промпт:
{current_prompt[:7000]}

Улучши промпт — сделай его более точным и эффективным.
Добавь конкретные правила для лучшей работы.
Верни только улучшенный промпт, ничего лишнего. Максимум 8000 символов."""

    new_prompt, _ = await call_llm(system, user)
    new_prompt = new_prompt[:8000]

    # Сохраняем новую версию
    next_version = memory.get_next_version()
    memory.data["current_version"] = next_version
    memory.data["current_prompt"] = new_prompt

    # Архивируем старый
    if current_prompt:
        if "history" not in memory.data:
            memory.data["history"] = {}
        memory.data["history"][current_version] = {
            "prompt": current_prompt,
            "archived_at": datetime.now().isoformat()
        }

    memory.data["lessons"].append({
        "timestamp": datetime.now().isoformat(),
        "lesson": f"{next_version}: Ручная эволюция",
        "version": next_version
    })

    await memory.save_async()

    # Обновляем в agents_state.json
    state = _load_agents_state()
    if agent_id in state:
        state[agent_id]["instructions"] = new_prompt
        _atomic_write_json(AGENTS_STATE_FILE, state)

    log_med_action("manual_evolve", f"Агент {agent_id} эволюционировал: {current_version}→{next_version}", agent_id)

    return {
        "agent_id": agent_id,
        "old_version": current_version,
        "new_version": next_version,
        "new_prompt": new_prompt,
    }
