"""
Meta-Critic — надзиратель за качеством в МЕД-ОТДЕЛЕ.
Проверяет промпты при создании, мониторит Critic в процессе,
эволюционирует Critic если качество оценок падает.
"""
import os
import json
import tempfile
import threading
from datetime import datetime

from config import OPENROUTER_API_KEY
from med_otdel.agent_memory import call_llm

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES_DIR = os.path.join(PROJECT_ROOT, "prompts", "candidates")
PASSPORTS_DIR = os.path.join(PROJECT_ROOT, "memory", "passports")
STATE_FILE = os.path.join(PROJECT_ROOT, "memory", "agents_state.json")

_mc_lock = threading.Lock()


def _load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict):
    dir_name = os.path.dirname(STATE_FILE)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, STATE_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _save_passport(agent_id: str, passport: dict):
    os.makedirs(PASSPORTS_DIR, exist_ok=True)
    path = os.path.join(PASSPORTS_DIR, f"{agent_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(passport, f, ensure_ascii=False, indent=2)


async def evaluate_prompt(role: str, prompt_text: str, constitution: str = "") -> dict:
    """
    Оценить промпт кандидата по 4 критериям.
    Возвращает {relevance, specificity, constitution_compatibility, safety, total, feedback}.
    """
    system = (
        "Ты Meta-Critic аниме-студии. Оцениваешь системные промпты для AI-агентов. "
        "Будь строгим и объективным. Оценивай каждый критерий от 0 до 10."
    )

    user = f"""Оцени промпт для роли "{role}".

ПРОМПТ:
{prompt_text[:4000]}

{"КОНСТИТУЦИЯ СТУДИИ (проверь совместимость):\n" + constitution[:2000] if constitution else ""}

Оцени по 4 критериям (0-10):
1. relevance — насколько промпт релевантен роли {role}
2. specificity — конкретность инструкций (нет ли размытых формулировок)
3. constitution_compatibility — совместимость с конституцией студии
4. safety — безопасность (нет ли инструкций, ломающих систему)

Формат ответа:
RELEVANCE: <число>
SPECIFICITY: <число>
CONSTITUTION: <число>
SAFETY: <число>
FEEDBACK: <краткий комментарий>"""

    response, _ = await call_llm(system_prompt=system, user_prompt=user)

    scores = {}
    feedback = ""
    for line in response.split("\n"):
        s = line.strip().upper()
        if s.startswith("RELEVANCE:"):
            try:
                scores["relevance"] = int("".join(c for c in s.replace("RELEVANCE:", "").strip() if c.isdigit()))
            except ValueError:
                scores["relevance"] = 5
        elif s.startswith("SPECIFICITY:"):
            try:
                scores["specificity"] = int("".join(c for c in s.replace("SPECIFICITY:", "").strip() if c.isdigit()))
            except ValueError:
                scores["specificity"] = 5
        elif s.startswith("CONSTITUTION:"):
            try:
                scores["constitution_compatibility"] = int("".join(c for c in s.replace("CONSTITUTION:", "").strip() if c.isdigit()))
            except ValueError:
                scores["constitution_compatibility"] = 5
        elif s.startswith("SAFETY:"):
            try:
                scores["safety"] = int("".join(c for c in s.replace("SAFETY:", "").strip() if c.isdigit()))
            except ValueError:
                scores["safety"] = 5
        elif s.startswith("FEEDBACK:"):
            feedback = line.strip()[len("FEEDBACK:"):].strip()

    total = sum(scores.values())
    return {
        "relevance": scores.get("relevance", 5),
        "specificity": scores.get("specificity", 5),
        "constitution_compatibility": scores.get("constitution_compatibility", 5),
        "safety": scores.get("safety", 5),
        "total": total,
        "feedback": feedback,
    }


async def select_best_candidate(role: str, constitution: str = "") -> dict:
    """
    Оценить всех кандидатов для роли и выбрать лучшего.
    Возвращает лучший кандидат с оценками Meta-Critic.
    """
    candidates_file = os.path.join(CANDIDATES_DIR, f"{role}.json")
    if not os.path.exists(candidates_file):
        return {"error": f"Нет кандидатов для роли {role}"}

    with open(candidates_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    candidates = data.get("candidates", [])
    if not candidates:
        return {"error": f"Список кандидатов для {role} пуст"}

    results = []
    for candidate in candidates:
        evaluation = await evaluate_prompt(role, candidate.get("prompt", ""), constitution)
        candidate["meta_critic_evaluation"] = evaluation
        results.append(candidate)

    # Сортируем по total score
    results.sort(key=lambda c: c.get("meta_critic_evaluation", {}).get("total", 0), reverse=True)

    # Обновляем оценки в файле
    data["candidates"] = results
    with open(candidates_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "role": role,
        "best_candidate": results[0],
        "all_evaluations": [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "score": c.get("meta_critic_evaluation", {}).get("total", 0),
            }
            for c in results
        ],
    }


async def monitor_critic_quality(agent_id: str = "critic", threshold: int = 6) -> dict:
    """
    Проверить качество оценок Critic.
    Сравнивает оценки Critic с ожидаемым качеством.
    Если средняя оценка качества < threshold → рекомендация эволюции.
    """
    from med_otdel.agent_memory import AgentMemory

    memory = AgentMemory(agent_id)
    failures = memory.data.get("failures", [])

    if not failures:
        return {"status": "ok", "message": "Нет данных для анализа"}

    # Анализируем паттерны провалов
    recent = failures[-10:]  # Последние 10
    failure_types = {}
    for f in recent:
        ftype = f.get("type", "unknown")
        failure_types[ftype] = failure_types.get(ftype, 0) + 1

    # Если Critic сам часто проваливается — проблема
    critic_fail_count = sum(1 for f in recent if "critic" in f.get("type", "").lower())

    if critic_fail_count >= 2:
        return {
            "status": "warning",
            "message": f"Critic имеет {critic_fail_count} провалов в последних 10 оценках. Рекомендуется эволюция.",
            "recommendation": "evolve_critic",
            "failure_types": failure_types,
        }

    return {
        "status": "ok",
        "message": "Качество Critic в норме",
        "failure_types": failure_types,
    }


async def create_passport(agent_id: str, name: str, created_by: str = "HR", prompt_source: str = "", approved_by: str = "", meta_critic_score: float = 0.0) -> dict:
    """Создать паспорт агента."""
    passport = {
        "name": name,
        "agent_id": agent_id,
        "created_by": created_by,
        "prompt_source": prompt_source,
        "approved_by": approved_by,
        "meta_critic_score": meta_critic_score,
        "version": 1,
        "created_at": datetime.now().isoformat(),
    }
    _save_passport(agent_id, passport)
    return passport
