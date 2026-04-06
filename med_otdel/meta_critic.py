"""
Meta-Critic — надзиратель за качеством в МЕД-ОТДЕЛЕ.
Проверяет промпты при создании, мониторит Critic в процессе,
эволюционирует Critic если качество оценок падает.
"""
import os
import json
import asyncio
import tempfile
import threading
from datetime import datetime

from config import OPENROUTER_API_KEY
from med_otdel.agent_memory import call_llm

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES_DIR = os.path.join(PROJECT_ROOT, "prompts", "candidates")
PASSPORTS_DIR = os.path.join(PROJECT_ROOT, "memory", "passports")
STATE_FILE = os.path.join(PROJECT_ROOT, "memory", "agents_state.json")
CONSTITUTION_FILE = os.path.join(PROJECT_ROOT, "constitution.md")

# Критерии оценки промптов Meta-Critic (10 баллов каждый, итого 40)
EVALUATION_CRITERIA = {
    "constitution_match": {
        "label": "Соответствие Constitution.md",
        "description": "Формат 3 мин, стиль 2.5D, тон, запреты",
        "max_score": 10,
    },
    "role_clarity": {
        "label": "Чёткость роли",
        "description": "Агент понимает свою задачу без двусмысленностей",
        "max_score": 10,
    },
    "source_credibility": {
        "label": "Проверенность источника",
        "description": "Реальные результаты из сообщества (GitHub, Civitai, Medium)",
        "max_score": 10,
    },
    "project_adaptation": {
        "label": "Адаптация под активный проект",
        "description": "Учитывает контекст, сеттинг, персонажей и требования активного проекта",
        "max_score": 10,
    },
}

_mc_lock = threading.Lock()


def _load_constitution() -> str:
    if os.path.exists(CONSTITUTION_FILE):
        with open(CONSTITUTION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


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
    Оценить промпт кандидата по 4 критериям EVALUATION_CRITERIA.
    Возвращает оценки + total + feedback.
    """
    if not constitution:
        constitution = _load_constitution()

    criteria_desc = "\n".join(
        f"{i+1}. {name} — {data['description']} (0-{data['max_score']})"
        for i, (name, data) in enumerate(EVALUATION_CRITERIA.items())
    )

    system = (
        "Ты Meta-Critic анимационной студии. Оцениваешь системные промпты для AI-агентов. "
        "Будь строгим и объективным. Оценивай каждый критерий от 0 до 10."
    )

    user = f"""Оцени промпт для роли "{role}".

ПРОМПТ:
{prompt_text[:4000]}

КОНСТИТУЦИЯ СТУДИИ:
{constitution[:2000]}

Оцени по 4 критериям (0-10 каждый):
{criteria_desc}

ОТВЕЧАЙ ТОЛЬКО В JSON ФОРМАТЕ БЕЗ MARKDOWN И ПОЯСНЕНИЙ:
{{"constitution_match": <число>, "role_clarity": <число>, "source_credibility": <число>, "project_adaptation": <число>, "comment": "<одно предложение на русском>"}}"""

    response, _ = await call_llm(system_prompt=system, user_prompt=user)

    scores = {}
    feedback = ""

    # Попытка 1: парсим JSON из ответа
    try:
        # Убираем markdown code blocks если есть
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("\n", 1)[0]
        cleaned = cleaned.strip()
        data = json.loads(cleaned)
        scores["constitution_match"] = min(int(data.get("constitution_match", 0)), 10)
        scores["role_clarity"] = min(int(data.get("role_clarity", 0)), 10)
        scores["source_credibility"] = min(int(data.get("source_credibility", 0)), 10)
        scores["project_adaptation"] = min(int(data.get("project_adaptation", data.get("rodina_adaptation", 0))), 10)
        feedback = data.get("comment", "")
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    # Попытка 2: ищем числа после ключевых слов
    if not scores:
        for line in response.split("\n"):
            s = line.strip().upper()
            if any(s.startswith(k) for k in ["CONSTITUTION_MATCH:", "CONSTITUTION:", "СООТВЕТСТВИЕ:"]):
                nums = [int(c) for c in s.replace(":", " ").split() if c.isdigit()]
                if nums:
                    scores["constitution_match"] = min(nums[0], 10)
            elif any(s.startswith(k) for k in ["ROLE_CLARITY:", "ROLE CLARITY:", "ЧЁТКОСТЬ:", "ЯСНОСТЬ:"]):
                nums = [int(c) for c in s.replace(":", " ").split() if c.isdigit()]
                if nums:
                    scores["role_clarity"] = min(nums[0], 10)
            elif any(s.startswith(k) for k in ["SOURCE_CREDIBILITY:", "SOURCE CREDIBILITY:", "ИСТОЧНИК:", "ПРОВЕРЕННОСТЬ:"]):
                nums = [int(c) for c in s.replace(":", " ").split() if c.isdigit()]
                if nums:
                    scores["source_credibility"] = min(nums[0], 10)
            elif any(s.startswith(k) for k in ["PROJECT_ADAPTATION:", "PROJECT ADAPTATION:", "RODINA_ADAPTATION:", "RODINA ADAPTATION:", "АДАПТАЦИЯ:", "РОДИНА:"]):
                nums = [int(c) for c in s.replace(":", " ").split() if c.isdigit()]
                if nums:
                    scores["project_adaptation"] = min(nums[0], 10)
            elif any(s.startswith(k) for k in ["FEEDBACK:", "ОБРАТНАЯ СВЯЗЬ:", "КОММЕНТАРИЙ:", "COMMENT:"]):
                colon_idx = line.find(":")
                if colon_idx >= 0:
                    feedback = line[colon_idx + 1:].strip()

    # Попытка 3: fallback — ищем 4 числа 0-10 подряд
    if not scores:
        nums = []
        for line in response.split("\n"):
            parts = line.replace(":", " ").split()
            for p in parts:
                try:
                    n = int(p)
                    if 0 <= n <= 10:
                        nums.append(n)
                except ValueError:
                    pass
        if len(nums) >= 4:
            scores["constitution_match"] = nums[0]
            scores["role_clarity"] = nums[1]
            scores["source_credibility"] = nums[2]
            scores["project_adaptation"] = nums[3]
            feedback = response.strip()[:300]

    if not scores:
        feedback = response.strip()[:500]

    total = sum(scores.values()) if scores else 0
    max_total = sum(c["max_score"] for c in EVALUATION_CRITERIA.values())

    return {
        "constitution_match": scores.get("constitution_match", 0),
        "role_clarity": scores.get("role_clarity", 0),
        "source_credibility": scores.get("source_credibility", 0),
        "project_adaptation": scores.get("project_adaptation", 0),
        "rodina_adaptation": scores.get("project_adaptation", 0),
        "total": total,
        "max_total": max_total,
        "feedback": feedback,
    }


async def select_best_candidate(role: str) -> dict:
    """Оценить всех кандидатов для роли и выбрать лучшего."""
    candidates_file = os.path.join(CANDIDATES_DIR, f"{role}.json")
    if not os.path.exists(candidates_file):
        return {"error": f"Нет кандидатов для роли {role}"}

    with open(candidates_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    candidates = data.get("candidates", [])
    if not candidates:
        return {"error": f"Список кандидатов для {role} пуст"}

    constitution = _load_constitution()
    results = []
    for candidate in candidates:
        evaluation = await evaluate_prompt(role, candidate.get("prompt", ""), constitution)
        candidate["meta_critic_evaluation"] = evaluation
        results.append(candidate)

    results.sort(key=lambda c: c.get("meta_critic_evaluation", {}).get("total", 0), reverse=True)

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
                "max_score": c.get("meta_critic_evaluation", {}).get("max_total", 40),
                "feedback": c.get("meta_critic_evaluation", {}).get("feedback", ""),
            }
            for c in results
        ],
    }


async def initialize_project(project_description: str) -> dict:
    """
    Полный pipeline инициализации проекта:
    1. Загрузить constitution.md
    2. Загрузить всех кандидатов
    3. Оценить каждого через evaluate_prompt() параллельно
    4. Выбрать лучших
    5. Вернуть результаты для UI
    """
    roles = ["writer", "director", "dop", "critic", "sound_director"]
    constitution = _load_constitution()

    # Параллельная оценка всех кандидатов
    tasks = [select_best_candidate(role) for role in roles]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    evaluations = {}
    errors = []
    for i, result in enumerate(results):
        role = roles[i]
        if isinstance(result, Exception):
            errors.append({"role": role, "error": str(result)})
        elif "error" in result:
            errors.append({"role": role, "error": result["error"]})
        else:
            evaluations[role] = result

    return {
        "status": "ready",
        "project_description": project_description,
        "constitution_loaded": bool(constitution),
        "evaluations": evaluations,
        "errors": errors,
    }


async def approve_and_apply(approvals: dict, project_description: str = "") -> dict:
    """
    Утвердить выбранные промпты и применить их к агентам.
    approvals = {writer: "candidate_id", director: "candidate_id", ...}
    """
    state = _load_state()
    applied = []
    errors = []

    for role, candidate_id in approvals.items():
        candidates_file = os.path.join(CANDIDATES_DIR, f"{role}.json")
        if not os.path.exists(candidates_file):
            errors.append({"role": role, "error": "Нет файла кандидатов"})
            continue

        with open(candidates_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        candidate = None
        for c in data.get("candidates", []):
            if c.get("id") == candidate_id:
                candidate = c
                break

        if not candidate:
            errors.append({"role": role, "error": f"Кандидат {candidate_id} не найден"})
            continue

        eval_data = candidate.get("meta_critic_evaluation", {})
        prompt = candidate.get("prompt", "")

        # Применяем промпт к агенту
        if role in state:
            state[role]["instructions"] = prompt
            applied.append({
                "role": role,
                "candidate_id": candidate_id,
                "score": eval_data.get("total", 0),
            })

            # Создаём паспорт
            await create_passport(
                agent_id=role,
                name=state[role].get("name", role),
                created_by="HR",
                prompt_source=candidate.get("source_url", candidate.get("source", "")),
                approved_by="user",
                meta_critic_score=eval_data.get("total", 0),
            )

    _save_state(state)

    # Сохраняем состояние инициализации
    init_state = {
        "status": "completed",
        "project_description": project_description,
        "applied": applied,
        "errors": errors,
        "initialized_at": datetime.now().isoformat(),
    }
    init_file = os.path.join(PROJECT_ROOT, "memory", "init_state.json")
    with open(init_file, "w", encoding="utf-8") as f:
        json.dump(init_state, f, ensure_ascii=False, indent=2)

    return {
        "status": "completed",
        "applied": applied,
        "errors": errors,
    }


async def monitor_critic_quality(agent_id: str = "critic", threshold: int = 6) -> dict:
    """Проверить качество оценок Critic."""
    from med_otdel.agent_memory import AgentMemory

    memory = AgentMemory(agent_id)
    failures = memory.data.get("failures", [])

    if not failures:
        return {"status": "ok", "message": "Нет данных для анализа"}

    recent = failures[-10:]
    failure_types = {}
    for f in recent:
        ftype = f.get("type", "unknown")
        failure_types[ftype] = failure_types.get(ftype, 0) + 1

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


async def approve_and_apply_db(db, approvals: dict, project_description: str = "") -> dict:
    """
    Утвердить выбранные промпты и применить их к агентам в БД.
    approvals = {writer: "candidate_id", director: "candidate_id", ...}
    
    Уровень 1 — Meta-Critic:
    1. Оценивает промпт кандидата
    2. Если score >= threshold — агент допускается (status: idle)
    3. Если score < threshold — агент отклонён (status: rejected)
    4. Создаёт passport в БД
    """
    import crud
    
    state = _load_state()
    applied = []
    errors = []
    rejected = []
    
    # Meta-Critic threshold для допуска (из 40)
    THRESHOLD = 24  # 60% от максимума
    
    constitution = _load_constitution()
    
    for role, candidate_id in approvals.items():
        candidates_file = os.path.join(CANDIDATES_DIR, f"{role}.json")
        if not os.path.exists(candidates_file):
            errors.append({"role": role, "error": "Нет файла кандидатов"})
            continue
        
        with open(candidates_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        candidate = None
        for c in data.get("candidates", []):
            if c.get("id") == candidate_id:
                candidate = c
                break
        
        if not candidate:
            errors.append({"role": role, "error": f"Кандидат {candidate_id} не найден"})
            continue
        
        prompt = candidate.get("prompt", "")
        
        # Уровень 1: Meta-Critic оценивает промпт
        evaluation = await evaluate_prompt(role, prompt, constitution)
        total_score = evaluation.get("total", 0)
        
        if total_score >= THRESHOLD:
            # Агент допущен — обновляем в БД
            agent = await crud.get_agent(db, role)
            if agent:
                await crud.update_agent(db, role, {
                    "instructions": prompt,
                    "status": "idle"
                })
                
                # Создаём паспорт в БД
                await crud.create_passport(db, {
                    "agent_id": role,
                    "name": state.get(role, {}).get("name", role),
                    "created_by": "HR",
                    "prompt_source": candidate.get("source_url", candidate.get("source", "")),
                    "approved_by": "meta_critic",
                    "meta_critic_score": float(total_score),
                    "version": 1,
                    "created_at": datetime.now().isoformat(),
                })
                
                applied.append({
                    "role": role,
                    "candidate_id": candidate_id,
                    "score": total_score,
                    "status": "approved",
                    "feedback": evaluation.get("feedback", ""),
                })
        else:
            # Агент отклонён
            agent = await crud.get_agent(db, role)
            if agent:
                await crud.update_agent(db, role, {"status": "rejected"})
            
            rejected.append({
                "role": role,
                "candidate_id": candidate_id,
                "score": total_score,
                "threshold": THRESHOLD,
                "status": "rejected",
                "feedback": evaluation.get("feedback", ""),
            })
    
    # Сохраняем состояние инициализации
    init_state = {
        "status": "completed",
        "project_description": project_description,
        "applied": applied,
        "rejected": rejected,
        "errors": errors,
        "initialized_at": datetime.now().isoformat(),
    }
    init_file = os.path.join(PROJECT_ROOT, "memory", "init_state.json")
    with open(init_file, "w", encoding="utf-8") as f:
        json.dump(init_state, f, ensure_ascii=False, indent=2)
    
    return {
        "status": "completed",
        "applied": applied,
        "rejected": rejected,
        "errors": errors,
    }
