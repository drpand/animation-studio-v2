"""
Med Otdel API — API МЕД-ОТДЕЛА.
Префикс роутов задаётся в main.py: /api/med-otdel

This file is now a thin wrapper that imports from the modularized api/med_otdel/ package
for backward compatibility.
"""
from api.med_otdel import router  # noqa: F401
from api.med_otdel.helpers import (  # noqa: F401
    get_last_agent_result,
    read_med_log_file,
)
