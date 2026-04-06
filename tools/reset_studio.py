"""
Hard reset runtime studio state (non-destructive schema reset).

What it does:
- Clears runtime DB content tables (frames/messages/events/discussions/tasks/med logs/etc.)
- Resets all agents status to idle
- Clears chat histories in memory/agents_state.json
- Resets memory files: events_bus, med_log, discussion_log, orchestrator_tasks, tasks
- Resets project_memory to a minimal default active project
- Clears generated media cache (memory/tools_cache/images)

Does NOT:
- Drop DB schema
- Delete repo code/config
"""

import json
import os
import sqlite3
from datetime import datetime


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_DIR = os.path.join(PROJECT_ROOT, "memory")
DB_PATH = os.path.join(MEMORY_DIR, "studio.db")
PATTERNS_PATH = os.path.join(PROJECT_ROOT, "med_otdel", "patterns.json")


def _write_json(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _safe_delete_file(path: str):
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


def reset_db_content():
    if not os.path.exists(DB_PATH):
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Keep schema, clear content tables used by runtime.
    tables_to_clear = [
        "orchestrator_steps",
        "orchestrator_tasks",
        "scene_frames",
        "messages",
        "events",
        "discussions",
        "med_logs",
        "characters",
        "agent_attachments",
        "agent_rules",
        "scene_versions",
        "scenes",
        "episodes",
        "seasons",
        "mood_board",
        "decisions",
        "passports",
        "init_state",
    ]

    for tbl in tables_to_clear:
        try:
            cur.execute(f"DELETE FROM {tbl}")
        except Exception:
            pass

    # Reset agents runtime status only (keep agents list/instructions/models)
    try:
        cur.execute("UPDATE agents SET status='idle'")
    except Exception:
        pass

    conn.commit()
    conn.close()


def reset_memory_files():
    _write_json(os.path.join(MEMORY_DIR, "events_bus.json"), {"events": []})
    _write_json(os.path.join(MEMORY_DIR, "med_log.json"), {"entries": []})
    _write_json(os.path.join(MEMORY_DIR, "discussion_log.json"), {"messages": []})
    _write_json(os.path.join(MEMORY_DIR, "orchestrator_tasks.json"), {"tasks": []})
    _write_json(os.path.join(MEMORY_DIR, "tasks.json"), {"studio_status": "ok"})

    # Reset init state
    _write_json(os.path.join(MEMORY_DIR, "init_state.json"), {
        "status": "not_started",
        "project_description": "",
        "initialized_at": "",
        "updated_at": datetime.now().isoformat(),
    })

    # Minimal active project
    _write_json(os.path.join(MEMORY_DIR, "project_memory.json"), {
        "active_project": {
            "name": "Animation Studio",
            "description": "",
            "file": "",
            "file_path": "",
            "current_season": 1,
            "current_episode": 1,
            "total_episodes": 1,
            "visual_style": "",
            "color_palette": "",
            "music_reference": "",
            "updated_at": datetime.now().isoformat(),
        },
        "projects": [],
        "seasons": [],
        "characters": [],
        "mood_board": [],
        "decision_log": [],
        "completed_tasks": [],
        "agent_decisions": [],
    })

    # Reset agents_state chat/status, keep role/model/instructions
    agents_state_file = os.path.join(MEMORY_DIR, "agents_state.json")
    if os.path.exists(agents_state_file):
        try:
            with open(agents_state_file, "r", encoding="utf-8") as f:
                st = json.load(f)
            for agent_id, data in st.items():
                if isinstance(data, dict):
                    data["status"] = "idle"
                    data["chat_history"] = []
                    data["attachments"] = []
                    data["attachment_objects"] = []
                    data["applied_rules"] = []
            _write_json(agents_state_file, st)
        except Exception:
            pass


def reset_patterns_file():
    """Сбросить patterns.json к базовому набору (без runtime character_consistency)."""
    baseline = {
        "patterns": [
            {
                "key": "duration_check",
                "name": "Проверка длительности",
                "rule_text": "[RULE] Длительность сцены должна соответствовать указанной в задаче.",
                "description": "Проверка соответствия тайминга задаче.",
                "category": "format",
                "priority": 10,
            },
            {
                "key": "style_reminder",
                "name": "Напоминание о стиле",
                "rule_text": "[RULE] Строго следуй визуальному стилю активного проекта.",
                "description": "Напоминание о визуальном стиле.",
                "category": "style",
                "priority": 5,
            },
            {
                "key": "kieai_prompt_template",
                "name": "Шаблон промпта Z-Image Turbo",
                "rule_text": "[subject] + [location/background] + [lighting] + [mood] + [style] + [palette] + [constraints: no text, no watermark, correct anatomy]",
                "description": "Negative prompt НЕ использовать. Ограничения в позитивном промпте.",
                "category": "visual",
                "priority": 100,
            },
            {
                "key": "no_hallucination",
                "name": "Запрет галлюцинаций",
                "rule_text": "[RULE] НЕ создавай персонажей, локации или детали, которых нет в текущем сценарии и карточках текущей сцены.",
                "description": "Запрет на выдумывание несуществующих элементов.",
                "category": "narrative",
                "priority": 10,
            },
        ]
    }
    _write_json(PATTERNS_PATH, baseline)


def clear_generated_cache():
    img_dir = os.path.join(MEMORY_DIR, "tools_cache", "images")
    if os.path.isdir(img_dir):
        for name in os.listdir(img_dir):
            path = os.path.join(img_dir, name)
            if os.path.isfile(path):
                _safe_delete_file(path)

    # Remove sqlite runtime side files
    _safe_delete_file(os.path.join(MEMORY_DIR, "studio.db-wal"))
    _safe_delete_file(os.path.join(MEMORY_DIR, "studio.db-shm"))


def main():
    reset_db_content()
    reset_memory_files()
    reset_patterns_file()
    clear_generated_cache()
    print("[OK] Studio runtime state reset complete")


if __name__ == "__main__":
    main()
