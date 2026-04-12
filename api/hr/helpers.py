"""Shared helpers for HR API endpoints."""
import os
import json
import uuid
import tempfile
import threading
from datetime import datetime
from config import PROJECT_NAME

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENTS_STATE_FILE = os.path.join(PROJECT_ROOT, "memory", "agents_state.json")

_state_lock = threading.Lock()

AGENT_ICONS = {
    "animator": "🎨",
    "editor": "✂️",
    "composer": "🎼",
    "voice": "🎤",
    "color": "🖌️",
    "lighting": "💡",
    "vfx": "✨",
    "translator": "🌐",
    "researcher": "🔬",
    "producer": "📋",
    "director": "🎬",
    "writer": "✍️",
    "critic": "🔍",
    "fixer": "🔧",
    "sound": "🎵",
    "art": "🎨",
    "dop": "📷",
    "storyboard": "📋",
}

DEFAULT_MODELS = [
    "google/gemini-3-flash-preview",
    "anthropic/claude-sonnet-4.5",
    "qwen/qwen3.5-9b",
    "openai/gpt-4o",
]


def load_state() -> dict:
    """Load agent state from file."""
    if not os.path.exists(AGENTS_STATE_FILE):
        return {}
    with open(AGENTS_STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict):
    """Save agent state to file atomically."""
    dir_name = os.path.dirname(AGENTS_STATE_FILE)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            json.dump(state, tmp, ensure_ascii=False, indent=2)
        os.replace(tmp_path, AGENTS_STATE_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def generate_agent_id(name: str) -> str:
    """Generate unique agent ID from name."""
    base = name.lower().replace(" ", "_").replace("-", "_")
    base = "".join(c for c in base if c.isalpha() or c == "_")
    suffix = uuid.uuid4().hex[:4]
    return f"{base}_{suffix}"


def pick_model() -> str:
    """Pick random model from defaults."""
    import random
    return random.choice(DEFAULT_MODELS)


def parse_hr_response(response: str, agent_name: str = "", agent_role: str = "", task_desc: str = "") -> tuple:
    """Parse HR LLM response into agent components."""
    name = agent_name or "New Agent"
    role = agent_role or "Специалист"
    prompt = f"Ты {role}. Выполняй задачи качественно."
    model = pick_model()

    for line in response.split("\n"):
        line_stripped = line.strip()
        if line_stripped.upper().startswith("NAME:"):
            name = line_stripped[len("NAME:"):].strip()
        elif line_stripped.upper().startswith("ROLE:"):
            role = line_stripped[len("ROLE:"):].strip()
        elif line_stripped.upper().startswith("PROMPT:"):
            prompt = line_stripped[len("PROMPT:"):].strip()
        elif line_stripped.upper().startswith("MODEL:"):
            model = line_stripped[len("MODEL:"):].strip()

    if not prompt or len(prompt) < 10:
        prompt = f"Ты {role} аниме-студии {PROJECT_NAME}. {task_desc[:500]}"

    return name, role, prompt, model


def find_icon(name: str) -> str:
    """Find icon for agent based on name."""
    name_lower = name.lower()
    for key, icon in AGENT_ICONS.items():
        if key in name_lower:
            return icon
    return "🤖"
