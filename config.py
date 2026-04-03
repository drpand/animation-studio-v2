# Animation Studio v2 — РОДИНА
import os

# OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")

# Project
PROJECT_NAME = "РОДИНА"
PORT = 7860

# ComfyUI
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://localhost:8188")
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
