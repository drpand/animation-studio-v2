# Animation Studio v2
import os
import json
from dotenv import load_dotenv

# Загружаем .env СРАЗУ — чтобы все модули видели переменные
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Database
PROJECT_ROOT_CONFIG = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = f"sqlite+aiosqlite:///{PROJECT_ROOT_CONFIG}/memory/studio.db"

# Auth
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "admin2026")

# Project - загружается динамически из активного проекта
def get_project_name():
    """Получить имя активного проекта из project_memory.json"""
    project_file = os.path.join(PROJECT_ROOT_CONFIG, "memory", "project_memory.json")
    try:
        if os.path.exists(project_file):
            with open(project_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                active_project = data.get("active_project", {})
                return active_project.get("name", "Animation Studio")
    except Exception:
        pass
    return "Animation Studio"

PROJECT_NAME = get_project_name()
PORT = 7860

# ComfyUI
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")
COMFYUI_POLL_ATTEMPTS = int(os.getenv("COMFYUI_POLL_ATTEMPTS", "150"))
COMFYUI_POLL_INTERVAL_SEC = int(os.getenv("COMFYUI_POLL_INTERVAL_SEC", "5"))

# Kie.ai
KIEAI_API_KEY = os.getenv("KIEAI_API_KEY", "")
KIEAI_POLL_ATTEMPTS = int(os.getenv("KIEAI_POLL_ATTEMPTS", "60"))
KIEAI_POLL_INTERVAL_SEC = int(os.getenv("KIEAI_POLL_INTERVAL_SEC", "2"))

# ElevenLabs
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_RETRY_ATTEMPTS = 3
ELEVENLABS_RETRY_BASE_DELAY = 2

# Rate limiting (глобальный — т.к. локальный)
RATE_LIMIT_REQUESTS_PER_MIN = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MIN", "10"))

# Промпты
MAX_PROMPT_LENGTH = 5000
