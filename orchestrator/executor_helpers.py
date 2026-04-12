"""
Executor Helpers — общие утилиты для executor и его модулей.
"""
import os
import json
import tempfile
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_full_project_context() -> str:
    """Загружает полный контекст активного проекта из project_memory.json."""
    project_memory_file = os.path.join(PROJECT_ROOT, "memory", "project_memory.json")
    if not os.path.exists(project_memory_file):
        return ""
    try:
        with open(project_memory_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        project = data.get("active_project", {})
        if not project or not project.get("name"):
            return ""
        
        parts = []
        parts.append(f"Название проекта: {project.get('name', '')}")
        if project.get("description"):
            parts.append(f"Описание: {project['description']}")
        if project.get("visual_style"):
            parts.append(f"Визуальный стиль: {project['visual_style']}")
        if project.get("color_palette"):
            parts.append(f"Цветовая палитра: {project['color_palette']}")
        if project.get("music_reference"):
            parts.append(f"Музыкальный референс: {project['music_reference']}")
        
        season = project.get("current_season", 1)
        episode = project.get("current_episode", 1)
        parts.append(f"Текущий эпизод: Сезон {season}, Эпизод {episode}")
        
        return "\n".join(parts)
    except Exception:
        return ""


async def _post_discussion(content: str, msg_type: str = "system", agent_id: str = ""):
    """Записать сообщение в Discussion канал."""
    discussion_file = os.path.join(PROJECT_ROOT, "memory", "discussion_log.json")
    entry = {
        "agent_id": agent_id or "orchestrator",
        "content": content,
        "msg_type": msg_type,
        "timestamp": datetime.now().isoformat(),
    }
    try:
        if os.path.exists(discussion_file):
            with open(discussion_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"messages": []}
        data["messages"].append(entry)
        if len(data["messages"]) > 200:
            data["messages"] = data["messages"][-200:]
        dir_name = os.path.dirname(discussion_file)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, discussion_file)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    except Exception:
        pass
