"""
HR Agent API — Создание временных агентов под задачу.
Префикс роутов задаётся в main.py: /api/hr

This file is now a thin wrapper that imports from the modularized api/hr/ package
for backward compatibility.
"""
from api.hr import router  # noqa: F401
from api.hr.helpers import (  # noqa: F401
    load_state,
    save_state,
    generate_agent_id,
    pick_model,
    parse_hr_response,
    find_icon,
    AGENT_ICONS,
    DEFAULT_MODELS,
    AGENTS_STATE_FILE,
)
