# Animation Studio v2 — РОДИНА
import os

# OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Database
PROJECT_ROOT_CONFIG = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = f"sqlite+aiosqlite:///{PROJECT_ROOT_CONFIG}/memory/studio.db"

# Auth
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "rodina2026")

# Project
PROJECT_NAME = "РОДИНА"
PORT = 7860

# ComfyUI
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")
COMFYUI_POLL_ATTEMPTS = int(os.getenv("COMFYUI_POLL_ATTEMPTS", "150"))
COMFYUI_POLL_INTERVAL_SEC = int(os.getenv("COMFYUI_POLL_INTERVAL_SEC", "5"))

# Kie.ai
KIEAI_API_KEY = os.getenv("KIEAI_API_KEY", "")
KIEAI_POLL_ATTEMPTS = int(os.getenv("KIEAI_POLL_ATTEMPTS", "200"))
KIEAI_POLL_INTERVAL_SEC = int(os.getenv("KIEAI_POLL_INTERVAL_SEC", "3"))

# ElevenLabs
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_RETRY_ATTEMPTS = 3
ELEVENLABS_RETRY_BASE_DELAY = 2

# Rate limiting (глобальный — т.к. локальный)
RATE_LIMIT_REQUESTS_PER_MIN = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MIN", "10"))

# Промпты
MAX_PROMPT_LENGTH = 5000
