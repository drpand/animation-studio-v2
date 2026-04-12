"""Shared helpers for agents API endpoints."""
import os
import json
from datetime import datetime
from io import BytesIO
from typing import Tuple

from pypdf import PdfReader

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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


def guess_content_type(ext: str) -> str:
    """Guess content type from file extension."""
    mapping = {
        ".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown",
        ".json": "application/json", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"
    }
    return mapping.get(ext, "application/octet-stream")


def normalize_text(text: str) -> str:
    """Normalize whitespace in text."""
    return " ".join((text or "").split())


def is_meaningful_text(text: str) -> bool:
    """Check if text is meaningful (has enough content)."""
    normalized = normalize_text(text)
    alnum_count = sum(1 for char in normalized if char.isalnum())
    return len(normalized) >= PDF_MIN_TEXT_LENGTH or alnum_count >= PDF_MIN_ALNUM_COUNT


def extract_pdf_preview_from_bytes(content: bytes) -> Tuple[bool, str]:
    """Extract and validate PDF text preview from bytes."""
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
            normalized = normalize_text(page_text)
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
        if is_meaningful_text(preview):
            return True, ""
        return False, "PDF без текстового слоя не читается"
    except Exception:
        return False, "PDF без текстового слоя не читается"


def resolve_attachment_flags(filename: str, content_type: str = "", content: bytes = None) -> Tuple[bool, str]:
    """Resolve attachment readability flags."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in TEXT_READABLE_EXTENSIONS:
        return True, ""
    if ext == ".pdf":
        if content is not None:
            return extract_pdf_preview_from_bytes(content)
        path = os.path.join(ATTACHMENTS_DIR, filename)
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    return extract_pdf_preview_from_bytes(f.read())
            except OSError:
                return False, "PDF без текстового слоя не читается"
        return False, "PDF без текстового слоя не читается"
    return False, "не читается моделью"


def update_active_project(filename: str, file_path: str):
    """Update active project in project memory file."""
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
