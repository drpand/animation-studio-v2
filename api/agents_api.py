"""
Agents API — CRUD агентов, загрузка файлов.
Префикс роутов задаётся в main.py: /api/agents

This file is now a thin wrapper that imports from the modularized api/agents/ package
for backward compatibility.
"""
from api.agents import router  # noqa: F401
from api.agents.helpers import (  # noqa: F401
    ATTACHMENTS_DIR,
    PROJECT_MEMORY_FILE,
    ALLOWED_EXTENSIONS,
    TEXT_READABLE_EXTENSIONS,
    MAX_FILE_SIZE,
    guess_content_type,
    normalize_text,
    is_meaningful_text,
    extract_pdf_preview_from_bytes,
    resolve_attachment_flags,
    update_active_project,
)
