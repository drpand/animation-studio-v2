"""
Episodes API — управление эпизодами, сезонами, сценами.
Префикс роутов задаётся в main.py: /api/episodes

This file is now a thin wrapper that imports from the modularized api/episodes/ package
for backward compatibility.
"""
from api.episodes import router  # noqa: F401
from api.episodes.helpers import (  # noqa: F401
    get_active_project_id,
    get_active_project,
    get_season_by_number,
    ensure_season,
    get_episode_by_number,
    now_iso,
)
