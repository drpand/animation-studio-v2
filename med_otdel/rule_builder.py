"""
Rule Builder — Конструктор Правил для МЕД-ОТДЕЛА.
Вместо генерации промпта LLM, добавляет/удаляет готовые паттерны.
"""
import os
import json
import tempfile
import threading
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(PROJECT_ROOT, "memory", "agents_state.json")
PATTERNS_FILE = os.path.join(PROJECT_ROOT, "med_otdel", "patterns.json")

_rule_lock = threading.Lock()


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


def _load_patterns() -> dict:
    if not os.path.exists(PATTERNS_FILE):
        return {}
    with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_available_patterns() -> list[dict]:
    """Получить список доступных паттернов."""
    patterns = _load_patterns()
    return [
        {"key": key, "rule": rule}
        for key, rule in patterns.items()
    ]


def apply_pattern(agent_id: str, pattern_key: str) -> dict:
    """
    Применить паттерн к агенту.
    Добавляет правило в конец инструкций агента.
    """
    patterns = _load_patterns()
    if pattern_key not in patterns:
        return {"ok": False, "error": f"Паттерн '{pattern_key}' не найден"}

    rule_text = patterns[pattern_key]

    with _rule_lock:
        state = _load_state()
        if agent_id not in state:
            return {"ok": False, "error": f"Агент '{agent_id}' не найден"}

        agent = state[agent_id]
        current_instructions = agent.get("instructions", "")

        # Проверяем, не добавлено ли уже это правило
        if rule_text in current_instructions:
            return {"ok": False, "error": "Правило уже применено"}

        # Добавляем правило
        new_instructions = f"{current_instructions}\n\n{rule_text}"
        agent["instructions"] = new_instructions

        # Сохраняем в rules историю
        if "rules" not in agent:
            agent["rules"] = []
        agent["rules"].append({
            "pattern_key": pattern_key,
            "rule_text": rule_text,
            "applied_at": datetime.now().isoformat(),
        })

        _save_state(state)

    return {
        "ok": True,
        "agent_id": agent_id,
        "pattern_key": pattern_key,
        "rule": rule_text,
    }


def remove_pattern(agent_id: str, pattern_key: str) -> dict:
    """
    Удалить паттерн у агента.
    Убирает правило из инструкций.
    """
    patterns = _load_patterns()
    if pattern_key not in patterns:
        return {"ok": False, "error": f"Паттерн '{pattern_key}' не найден"}

    rule_text = patterns[pattern_key]

    with _rule_lock:
        state = _load_state()
        if agent_id not in state:
            return {"ok": False, "error": f"Агент '{agent_id}' не найден"}

        agent = state[agent_id]
        current_instructions = agent.get("instructions", "")

        # Удаляем правило из текста
        new_instructions = current_instructions.replace(rule_text, "").strip()
        # Убираем лишние пустые строки
        while "\n\n\n" in new_instructions:
            new_instructions = new_instructions.replace("\n\n\n", "\n\n")
        agent["instructions"] = new_instructions

        # Удаляем из истории правил
        if "rules" in agent:
            agent["rules"] = [
                r for r in agent["rules"] if r.get("pattern_key") != pattern_key
            ]

        _save_state(state)

    return {
        "ok": True,
        "agent_id": agent_id,
        "pattern_key": pattern_key,
    }


def get_agent_rules(agent_id: str) -> list[dict]:
    """Получить список применённых правил агента."""
    state = _load_state()
    if agent_id not in state:
        return []
    return state[agent_id].get("rules", [])
