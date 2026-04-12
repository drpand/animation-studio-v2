"""
Chat API — Чат с агентом через OpenRouter.
Префикс роутов задаётся в main.py: /api/chat

This file is now a thin wrapper that imports from the modularized api/chat/ package
for backward compatibility.
"""
from api.chat import router  # noqa: F401
from api.chat.helpers import (  # noqa: F401
    extract_text_from_file,
    build_attachment_context,
    post_discussion,
    DISCUSSION_FILE,
    ATTACHMENTS_DIR,
    MAX_ATTACHMENT_TEXT,
)
