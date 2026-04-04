"""
Agents API — CRUD агентов, загрузка файлов.
Префикс роутов задаётся в main.py: /api/agents
"""
import os
import json
import tempfile
from io import BytesIO
from datetime import datetime
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from pypdf import PdfReader

from database import get_session
import crud
from models import AgentOut, AgentUpdate

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTACHMENTS_DIR = os.path.join(PROJECT_ROOT, "memory", "attachments")
PROJECT_MEMORY_FILE = os.path.join(PROJECT_ROOT, "memory", "project_memory.json")

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".jpg", ".jpeg", ".png", ".json"}
TEXT_READABLE_EXTENSIONS = {".txt", ".md", ".json"}
MAX_FILE_SIZE = 10 * 1024 * 1024
PDF_TEXT_PREVIEW_LIMIT = 6000
PDF_MIN_TEXT_LENGTH = 80
PDF_MIN_ALNUM_COUNT = 20
PDF_MAX_BYTES = 8 * 1024 * 1024
PDF_MAX_PAGES = 120
PDF_PAGE_SCAN_LIMIT = 20


def _guess_content_type(ext: str) -> str:
    mapping = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown",
               ".json": "application/json", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    return mapping.get(ext, "application/octet-stream")


def _guess_size(filename: str) -> int:
    path = os.path.join(ATTACHMENTS_DIR, filename)
    return os.path.getsize(path) if os.path.exists(path) else 0


def _guess_uploaded_at(filename: str) -> str:
    path = os.path.join(ATTACHMENTS_DIR, filename)
    return datetime.fromtimestamp(os.path.getmtime(path)).isoformat() if os.path.exists(path) else ""


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split())


def _is_meaningful_text(text: str) -> bool:
    normalized = _normalize_text(text)
    alnum_count = sum(1 for char in normalized if char.isalnum())
    return len(normalized) >= PDF_MIN_TEXT_LENGTH or alnum_count >= PDF_MIN_ALNUM_COUNT


def _extract_pdf_preview_from_bytes(content: bytes) -> tuple:
    if len(content) > PDF_MAX_BYTES:
        return False, "PDF слишком большой для чтения моделью"
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            return False, "PDF зашифрован и не читается моделью"
        if len(reader.pages) > PDF_MAX_PAGES:
            return False, "PDF слишком большой по числу страниц"
        chunks, current_length = [], 0
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


def _resolve_attachment_flags(filename: str, content_type: str = "", content: bytes = None) -> tuple:
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


def _update_active_project(filename: str, file_path: str):
    try:
        if os.path.exists(PROJECT_MEMORY_FILE):
            with open(PROJECT_MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"active_project": {}, "projects": [], "completed_tasks": [], "agent_decisions": []}
        if "active_project" not in data:
            data["active_project"] = {}
        data["active_project"]["file"] = filename
        data["active_project"]["file_path"] = file_path
        data["active_project"]["updated_at"] = datetime.now().isoformat()
        with open(PROJECT_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


@router.get("/")
async def list_agents(db: AsyncSession = Depends(get_session)):
    agents = await crud.get_all_agents(db)
    result = []
    for agent in agents:
        attachments = await crud.get_attachments(db, agent.agent_id)
        result.append(AgentOut(
            agent_id=agent.agent_id,
            name=agent.name,
            role=agent.role,
            model=agent.model,
            status=agent.status,
            instructions=agent.instructions,
        ))
    return {"agents": result}


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_session)):
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")
    attachments = await crud.get_attachments(db, agent_id)
    rules = await crud.get_rules(db, agent_id)
    messages = await crud.get_messages(db, agent_id)
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "role": agent.role,
        "model": agent.model,
        "status": agent.status,
        "instructions": agent.instructions,
        "attachment_objects": [
            {
                "filename": a.filename, "original_name": a.original_name,
                "content_type": a.content_type, "size_bytes": a.size_bytes,
                "extension": a.extension, "uploaded_at": a.uploaded_at,
                "is_text_readable": a.is_text_readable, "unreadable_reason": a.unreadable_reason,
            }
            for a in attachments
        ],
        "attachments": [a.filename for a in attachments],
        "applied_rules": [r.pattern_key for r in rules],
        "chat_history": [
            {"role": m.role, "content": m.content, "time": m.time}
            for m in messages
        ],
    }


@router.put("/{agent_id}")
async def update_agent(agent_id: str, update: AgentUpdate, db: AsyncSession = Depends(get_session)):
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")
    data = {k: v for k, v in update.model_dump().items() if v is not None}
    await crud.update_agent(db, agent_id, data)
    return {"ok": True, "agent_id": agent_id}


@router.post("/{agent_id}/upload")
async def upload_file(agent_id: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_session)):
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Недопустимый тип файла '{ext}'. Разрешены: {', '.join(ALLOWED_EXTENSIONS)}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"Файл слишком большой (макс. {MAX_FILE_SIZE // 1024 // 1024} MB)")

    os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
    safe_name = f"{agent_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    save_path = os.path.join(ATTACHMENTS_DIR, safe_name)
    with open(save_path, "wb") as f:
        f.write(content)

    uploaded_at = datetime.now().isoformat()
    is_text_readable, unreadable_reason = _resolve_attachment_flags(file.filename, file.content_type or "", content)

    attachment_data = {
        "filename": safe_name, "original_name": file.filename,
        "content_type": file.content_type or _guess_content_type(ext),
        "size_bytes": len(content), "extension": ext,
        "uploaded_at": uploaded_at, "is_text_readable": is_text_readable,
        "unreadable_reason": unreadable_reason,
    }
    await crud.add_attachment(db, agent_id, attachment_data)

    if agent_id == "orchestrator":
        _update_active_project(file.filename, safe_name)

    return {
        "ok": True, "filename": safe_name, "uploaded_at": uploaded_at,
        "is_text_readable": is_text_readable, "unreadable_reason": unreadable_reason,
        "attachment": attachment_data,
    }


@router.delete("/{agent_id}/attachments/{filename}")
async def delete_attachment(agent_id: str, filename: str, db: AsyncSession = Depends(get_session)):
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")
    await crud.remove_attachment(db, agent_id, filename)
    path = os.path.join(ATTACHMENTS_DIR, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    return {"ok": True, "filename": filename}
