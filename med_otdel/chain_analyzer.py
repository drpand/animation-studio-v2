"""
Chain Analyzer — анализ цепочек агент→агент
Находит проблемные связи между агентами по task_id.
Если агент A → агент B fails 2 раза с тем же task_id → chain_heal.
"""
import os
import json
from collections import defaultdict
from typing import List, Dict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_BUS_FILE = os.path.join(PROJECT_ROOT, "memory", "events_bus.json")


def _load_events() -> list:
    """Загрузить события из шины."""
    if not os.path.exists(EVENTS_BUS_FILE):
        return []
    with open(EVENTS_BUS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("events", [])


def analyze_chains() -> list[dict]:
    """
    Найти проблемные цепочки агент→агент.
    
    Возвращает список цепочек с 2+ fail подряд:
    [
      {
        "from_agent": "writer",
        "to_agent": "critic",
        "task_ids": ["task_001", "task_002"],
        "fail_count": 2,
        "last_feedback": "Промпт не содержит описание освещения"
      }
    ]
    """
    events = _load_events()
    
    # Группируем по task_id
    task_events: dict[str, list] = defaultdict(list)
    for evt in events:
        task_id = evt.get("task_id", "")
        if task_id:
            task_events[task_id].append(evt)
    
    # Ищем цепочки: один агент завершил задачу, другой оценил и дал fail
    chain_fails: dict[tuple[str, str], list] = defaultdict(list)
    
    for task_id, evts in task_events.items():
        completed = [e for e in evts if e.get("event_type") == "task_completed"]
        evaluations = [e for e in evts if e.get("event_type") == "evaluation" and e.get("status") == "fail"]
        
        for comp in completed:
            from_agent = comp.get("agent_id", "")
            for ev in evaluations:
                # evaluation может быть от critic о работе from_agent
                target = ev.get("target_agent_id", "")
                if target == from_agent or (not target and ev.get("agent_id") != from_agent):
                    # Это оценка работы from_agent
                    to_agent = ev.get("agent_id", "")  # кто оценивал (обычно critic)
                    if from_agent and to_agent and from_agent != to_agent:
                        chain_fails[(from_agent, to_agent)].append({
                            "task_id": task_id,
                            "feedback": ev.get("result", "")[:200],
                            "timestamp": ev.get("timestamp", "")
                        })
    
    # Фильтруем: только цепочки с 2+ fail
    problematic_chains = []
    for (from_agent, to_agent), fails in chain_fails.items():
        if len(fails) >= 2:
            problematic_chains.append({
                "from_agent": from_agent,
                "to_agent": to_agent,
                "task_ids": [f["task_id"] for f in fails],
                "fail_count": len(fails),
                "last_feedback": fails[-1]["feedback"],
                "timestamps": [f["timestamp"] for f in fails]
            })
    
    return problematic_chains


def get_chain_heal_prompt(from_agent: str, to_agent: str, feedback: str) -> str:
    """
    Сгенерировать правило для принимающего агента.
    Добавляет правило обработки входных данных от конкретного отправителя.
    """
    return f"""
ПРАВИЛО ОБРАБОТКИ ВХОДНЫХ ДАННЫХ ОТ {from_agent.upper()}:
При получении результата от агента {from_agent}, ОБЯЗАТЕЛЬНО проверяй:
- Полноту данных (все ли поля заполнены)
- Формат (соответствует ли ожидаемому)
- Контекст задачи (связан ли результат с исходной задачей)

Предыдущие ошибки при работе с {from_agent}:
{feedback}

Если результат не соответствует требованиям — укажи КОНКРЕТНО что исправить,
не просто "плохо", а "отсутствует описание X в разделе Y".
""".strip()
