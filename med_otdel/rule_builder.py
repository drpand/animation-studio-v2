"""
Rule Builder — Конструктор Правил для МЕД-ОТДЕЛА.
Вместо генерации промпта LLM, добавляет/удаляет готовые паттерны.
"""
import os
import json
import tempfile
import threading
import re
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(PROJECT_ROOT, "memory", "agents_state.json")
PATTERNS_FILE = os.path.join(PROJECT_ROOT, "med_otdel", "patterns.json")

_rule_lock = threading.Lock()

# Валидация ключа паттерна
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,49}$")

# Лимиты
MAX_RULES_PER_AGENT = 20
MAX_INSTRUCTION_LENGTH = 50000


def _post_discussion_rule_applied(agent_id: str, pattern_key: str, rule_name: str):
    """Записать применение правила в Discussion канал."""
    discussion_file = os.path.join(PROJECT_ROOT, "memory", "discussion_log.json")
    entry = {
        "agent_id": "med_otdel",
        "content": f"[RULE_APPLIED] Применено правило '{rule_name}' ({pattern_key}) агенту {agent_id}",
        "msg_type": "med_otdel",
        "timestamp": datetime.now().isoformat(),
    }
    try:
        with _rule_lock:
            if os.path.exists(discussion_file):
                with open(discussion_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {"messages": []}
            data["messages"].append(entry)
            if len(data["messages"]) > 100:
                data["messages"] = data["messages"][-100:]
            dir_name = os.path.dirname(discussion_file)
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


def _post_discussion_rule_removed(agent_id: str, pattern_key: str, rule_name: str):
    """Записать удаление правила в Discussion канал."""
    discussion_file = os.path.join(PROJECT_ROOT, "memory", "discussion_log.json")
    entry = {
        "agent_id": "med_otdel",
        "content": f"[RULE_REMOVED] Удалено правило '{rule_name}' ({pattern_key}) у агента {agent_id}",
        "msg_type": "med_otdel",
        "timestamp": datetime.now().isoformat(),
    }
    try:
        with _rule_lock:
            if os.path.exists(discussion_file):
                with open(discussion_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {"messages": []}
            data["messages"].append(entry)
            if len(data["messages"]) > 100:
                data["messages"] = data["messages"][-100:]
            dir_name = os.path.dirname(discussion_file)
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

# Лимиты
MAX_RULES_PER_AGENT = 20
MAX_INSTRUCTION_LENGTH = 50000


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


def _load_patterns() -> list:
    if not os.path.exists(PATTERNS_FILE):
        return []
    with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("patterns", [])


def _get_pattern(key: str) -> dict | None:
    patterns = _load_patterns()
    for p in patterns:
        if p.get("key") == key:
            return p
    return None


def get_available_patterns() -> list[dict]:
    """Получить список доступных паттернов."""
    return _load_patterns()


def apply_pattern(agent_id: str, pattern_key: str) -> dict:
    """
    Применить паттерн к агенту.
    Добавляет правило в конец инструкций агента.
    """
    if not _KEY_RE.match(pattern_key):
        return {"ok": False, "error": f"Недопустимый ключ паттерна: {pattern_key}"}

    pattern = _get_pattern(pattern_key)
    if not pattern:
        return {"ok": False, "error": f"Паттерн '{pattern_key}' не найден"}

    rule_text = pattern.get("rule_text", "")
    if not rule_text:
        return {"ok": False, "error": f"Паттерн '{pattern_key}' пуст"}

    # Запрет на изменение роли
    if "role:" in rule_text.lower() or "роль:" in rule_text.lower():
        return {"ok": False, "error": "Правило не может содержать изменение роли"}

    with _rule_lock:
        state = _load_state()
        if agent_id not in state:
            return {"ok": False, "error": f"Агент '{agent_id}' не найден"}

        agent = state[agent_id]
        current_instructions = agent.get("instructions", "")
        
        # Инициализация списка правил
        if "applied_rules" not in agent:
            agent["applied_rules"] = []

        # Проверка дубликатов
        if pattern_key in agent["applied_rules"]:
            return {"ok": False, "error": "Правило уже применено"}

        # Проверка лимита правил
        if len(agent["applied_rules"]) >= MAX_RULES_PER_AGENT:
            return {"ok": False, "error": f"Превышен лимит правил ({MAX_RULES_PER_AGENT})"}

        # Проверка длины инструкций
        if len(current_instructions) + len(rule_text) + 2 > MAX_INSTRUCTION_LENGTH:
            return {"ok": False, "error": "Превышен лимит длины инструкций"}

        # Добавление правила
        separator = "\n\n" if current_instructions else ""
        agent["instructions"] = current_instructions + separator + rule_text
        agent["applied_rules"].append(pattern_key)

        _save_state(state)

    # Запись в Discussion канал
    _post_discussion_rule_applied(agent_id, pattern_key, pattern.get("name", pattern_key))

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
    if not _KEY_RE.match(pattern_key):
        return {"ok": False, "error": f"Недопустимый ключ паттерна: {pattern_key}"}

    pattern = _get_pattern(pattern_key)
    if not pattern:
        return {"ok": False, "error": f"Паттерн '{pattern_key}' не найден"}

    rule_text = pattern.get("rule_text", "")

    with _rule_lock:
        state = _load_state()
        if agent_id not in state:
            return {"ok": False, "error": f"Агент '{agent_id}' не найден"}

        agent = state[agent_id]
        current_instructions = agent.get("instructions", "")

        # Удаляем правило из текста
        if rule_text in current_instructions:
            new_instructions = current_instructions.replace(rule_text, "")
            # Чистим лишние пустые строки
            while "\n\n\n" in new_instructions:
                new_instructions = new_instructions.replace("\n\n\n", "\n\n")
            agent["instructions"] = new_instructions.strip()
        else:
            return {"ok": False, "error": "Правило не найдено в инструкциях агента"}

        # Удаляем из истории правил
        if "applied_rules" in agent and pattern_key in agent["applied_rules"]:
            agent["applied_rules"].remove(pattern_key)

        _save_state(state)

    # Запись в Discussion канал
    _post_discussion_rule_removed(agent_id, pattern_key, pattern.get("name", pattern_key))

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
    
    agent = state[agent_id]
    applied_keys = agent.get("applied_rules", [])
    rules = []
    
    for key in applied_keys:
        pattern = _get_pattern(key)
        if pattern:
            rules.append({
                "key": key,
                "name": pattern.get("name"),
                "rule_text": pattern.get("rule_text"),
                "description": pattern.get("description"),
                "category": pattern.get("category"),
                "priority": pattern.get("priority"),
            })
    
    return rules
