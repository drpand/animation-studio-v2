"""
Agents API — CRUD агентов, загрузка файлов.
Префикс роутов задаётся в main.py: /api/agents
"""
import os
import json
import tempfile
from io import BytesIO
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from pypdf import PdfReader

from agents.base_agent import STATE_FILE

router = APIRouter()

MEMORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTACHMENTS_DIR = os.path.join(MEMORY_ROOT, "memory", "attachments")

# Допустимые расширения файлов
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".jpg", ".jpeg", ".png", ".json"}
TEXT_READABLE_EXTENSIONS = {".txt", ".md", ".json"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
PDF_TEXT_PREVIEW_LIMIT = 6000
PDF_MIN_TEXT_LENGTH = 80
PDF_MIN_ALNUM_COUNT = 20
PDF_MAX_BYTES = 8 * 1024 * 1024
PDF_MAX_PAGES = 120
PDF_PAGE_SCAN_LIMIT = 20


def _load_state() -> dict:
    """Загрузить agents_state.json."""
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict):
    """Сохранить agents_state.json."""
    dir_name = os.path.dirname(STATE_FILE)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, STATE_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _guess_uploaded_at(filename: str) -> str:
    path = os.path.join(ATTACHMENTS_DIR, filename)
    if os.path.exists(path):
        return datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
    return ""


def _guess_size(filename: str) -> int | None:
    path = os.path.join(ATTACHMENTS_DIR, filename)
    if os.path.exists(path):
        return os.path.getsize(path)
    return None


def _guess_content_type(ext: str) -> str:
    mapping = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".json": "application/json",
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }
    return mapping.get(ext, "application/octet-stream")


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split())


def _is_meaningful_text(text: str) -> bool:
    normalized = _normalize_text(text)
    alnum_count = sum(1 for char in normalized if char.isalnum())
    return len(normalized) >= PDF_MIN_TEXT_LENGTH or alnum_count >= PDF_MIN_ALNUM_COUNT


def _extract_pdf_preview_from_bytes(content: bytes) -> tuple[bool, str]:
    if len(content) > PDF_MAX_BYTES:
        return False, "PDF слишком большой для чтения моделью"
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            return False, "PDF зашифрован и не читается моделью"
        if len(reader.pages) > PDF_MAX_PAGES:
            return False, "PDF слишком большой по числу страниц для чтения моделью"

        chunks = []
        current_length = 0
        for page in reader.pages[:PDF_PAGE_SCAN_LIMIT]:
            page_text = page.extract_text() or ""
            normalized = _normalize_text(page_text)
            if not normalized:
                continue
            remaining = PDF_TEXT_PREVIEW_LIMIT - current_length
            if remaining <= 0:
                break
            excerpt = normalized[:remaining]
            chunks.append(excerpt)
            current_length += len(excerpt)
            if current_length >= PDF_TEXT_PREVIEW_LIMIT:
                break

        preview = "\n".join(chunks)
        if _is_meaningful_text(preview):
            return True, ""
        return False, "PDF без текстового слоя не читается"
    except Exception:
        return False, "PDF без текстового слоя не читается"


def _resolve_attachment_flags(filename: str, content_type: str = "", content: bytes | None = None) -> tuple[bool, str]:
    ext = os.path.splitext(filename)[1].lower()
    if ext in TEXT_READABLE_EXTENSIONS:
        return True, ""
    if ext == ".pdf":
        if content is not None:
            return _extract_pdf_preview_from_bytes(content)
        path = os.path.join(ATTACHMENTS_DIR, filename)
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    return _extract_pdf_preview_from_bytes(f.read())
            except OSError:
                return False, "PDF без текстового слоя не читается"
        return False, "PDF без текстового слоя не читается"
    return False, "не читается моделью"


def _normalize_attachment_objects(data: dict) -> list:
    normalized = []
    seen = set()

    for item in data.get("attachment_objects", []) or []:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename") or item.get("stored_filename") or item.get("name")
        if not filename or filename in seen:
            continue
        ext = os.path.splitext(filename)[1].lower()
        resolved_readable, resolved_reason = _resolve_attachment_flags(filename)
        normalized.append({
            "filename": filename,
            "original_name": item.get("original_name") or filename,
            "content_type": item.get("content_type") or _guess_content_type(ext),
            "size_bytes": item.get("size_bytes", _guess_size(filename)),
            "extension": item.get("extension") or ext,
            "uploaded_at": item.get("uploaded_at") or _guess_uploaded_at(filename),
            "is_text_readable": resolved_readable if ext == ".pdf" else item.get("is_text_readable", resolved_readable),
            "unreadable_reason": resolved_reason if ext == ".pdf" else item.get("unreadable_reason", resolved_reason),
        })
        seen.add(filename)

    for filename in data.get("attachments", []) or []:
        if not filename or filename in seen:
            continue
        ext = os.path.splitext(filename)[1].lower()
        normalized.append({
            "filename": filename,
            "original_name": filename,
            "content_type": _guess_content_type(ext),
            "size_bytes": _guess_size(filename),
            "extension": ext,
            "uploaded_at": _guess_uploaded_at(filename),
            "is_text_readable": _resolve_attachment_flags(filename)[0],
            "unreadable_reason": _resolve_attachment_flags(filename)[1],
        })
        seen.add(filename)

    return sorted(normalized, key=lambda item: item.get("uploaded_at") or "", reverse=True)


class AgentUpdate(BaseModel):
    model: str | None = None
    instructions: str | None = None
    status: str | None = None


@router.get("/")
async def list_agents():
    """Список всех агентов."""
    state = _load_state()
    agents = []
    for agent_id, data in state.items():
        attachment_objects = _normalize_attachment_objects(data)
        agents.append({
            "agent_id": agent_id,
            "name": data.get("name", agent_id),
            "role": data.get("role", ""),
            "model": data.get("model", ""),
            "status": data.get("status", "idle"),
            "attachment_objects": attachment_objects,
            "attachments": data.get("attachments", []),
        })
    return {"agents": agents}


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    """Получить данные одного агента."""
    state = _load_state()
    if agent_id not in state:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")
    data = state[agent_id]
    attachment_objects = _normalize_attachment_objects(data)
    return {
        "agent_id": agent_id,
        "name": data.get("name", agent_id),
        "role": data.get("role", ""),
        "model": data.get("model", ""),
        "status": data.get("status", "idle"),
        "instructions": data.get("instructions", ""),
        "attachment_objects": attachment_objects,
        "attachments": data.get("attachments", []),
        "chat_history": data.get("chat_history", []),
    }


@router.put("/{agent_id}")
async def update_agent(agent_id: str, update: AgentUpdate):
    """Обновить модель, инструкции или статус агента."""
    state = _load_state()
    if agent_id not in state:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")

    if update.model is not None:
        state[agent_id]["model"] = update.model
    if update.instructions is not None:
        state[agent_id]["instructions"] = update.instructions
    if update.status is not None:
        state[agent_id]["status"] = update.status

    _save_state(state)
    return {"ok": True, "agent_id": agent_id}


@router.post("/{agent_id}/upload")
async def upload_file(agent_id: str, file: UploadFile = File(...)):
    """Прикрепить файл к агенту с валидацией типа и размера."""
    state = _load_state()
    if agent_id not in state:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")

    # Валидация расширения
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Недопустимый тип файла '{ext}'. Разрешены: {', '.join(ALLOWED_EXTENSIONS)}")

    # Читаем файл и проверяем размер
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"Файл слишком большой (макс. {MAX_FILE_SIZE // 1024 // 1024} MB)")

    # Сохраняем
    os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
    safe_name = f"{agent_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    save_path = os.path.join(ATTACHMENTS_DIR, safe_name)

    with open(save_path, "wb") as f:
        f.write(content)

    uploaded_at = datetime.now().isoformat()
    is_text_readable, unreadable_reason = _resolve_attachment_flags(file.filename, file.content_type or "", content)

    # Новое основное поле
    if "attachment_objects" not in state[agent_id]:
        state[agent_id]["attachment_objects"] = []
    attachment_object = {
        "filename": safe_name,
        "original_name": file.filename,
        "content_type": file.content_type or _guess_content_type(ext),
        "size_bytes": len(content),
        "extension": ext,
        "uploaded_at": uploaded_at,
        "is_text_readable": is_text_readable,
        "unreadable_reason": unreadable_reason,
    }
    state[agent_id]["attachment_objects"].append(attachment_object)

    # Старое поле оставляем только для fallback/UI-совместимости
    if "attachments" not in state[agent_id]:
        state[agent_id]["attachments"] = []
    state[agent_id]["attachments"].append(safe_name)
    _save_state(state)

    return {
        "ok": True,
        "filename": safe_name,
        "uploaded_at": uploaded_at,
        "is_text_readable": is_text_readable,
        "unreadable_reason": unreadable_reason,
        "attachment": attachment_object,
    }


@router.delete("/{agent_id}/attachments/{filename}")
async def delete_attachment(agent_id: str, filename: str):
    """Удалить активное вложение агента."""
    state = _load_state()
    if agent_id not in state:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")

    agent = state[agent_id]
    attachment_objects = agent.get("attachment_objects", []) or []
    attachments = agent.get("attachments", []) or []

    exists = any(item.get("filename") == filename for item in attachment_objects) or filename in attachments
    if not exists:
        raise HTTPException(404, f"Вложение '{filename}' не найдено")

    agent["attachment_objects"] = [
        item for item in attachment_objects if item.get("filename") != filename
    ]
    agent["attachments"] = [item for item in attachments if item != filename]
    _save_state(state)

    path = os.path.join(ATTACHMENTS_DIR, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass

    return {"ok": True, "filename": filename}
