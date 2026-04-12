"""Shared helpers for chat API endpoints."""
import os
import json
from datetime import datetime

from pypdf import PdfReader

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DISCUSSION_FILE = os.path.join(PROJECT_ROOT, "memory", "discussion_log.json")
ATTACHMENTS_DIR = os.path.join(PROJECT_ROOT, "memory", "attachments")
MAX_ATTACHMENT_TEXT = 8000


def extract_text_from_file(filepath: str, ext: str) -> str:
    """Extract text from attached file."""
    if not os.path.exists(filepath):
        return ""
    try:
        if ext == ".pdf":
            reader = PdfReader(filepath)
            texts = []
            for page in reader.pages[:20]:  # Max 20 pages
                text = page.extract_text() or ""
                texts.append(text)
                if sum(len(t) for t in texts) > MAX_ATTACHMENT_TEXT:
                    break
            result = "\n\n".join(texts)[:MAX_ATTACHMENT_TEXT]
            return result
        elif ext in (".txt", ".md"):
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()[:MAX_ATTACHMENT_TEXT]
        elif ext == ".json":
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return json.dumps(data, ensure_ascii=False, indent=2)[:MAX_ATTACHMENT_TEXT]
    except Exception as e:
        return f"[Ошибка чтения файла: {str(e)}]"
    return ""


def build_attachment_context(attachments) -> str:
    """Build text context from all agent attachments."""
    if not attachments:
        return ""
    texts = []
    for att in attachments:
        filename = att.filename if hasattr(att, 'filename') else att.get('filename', '')
        ext = os.path.splitext(filename)[1].lower()
        if ext in (".pdf", ".txt", ".md", ".json"):
            filepath = os.path.join(ATTACHMENTS_DIR, filename)
            text = extract_text_from_file(filepath, ext)
            if text:
                texts.append(f"--- Файл: {filename} ---\n{text}")
    if not texts:
        return ""
    return "\n\n".join(texts)


async def post_discussion(db, agent_id: str, agent_name: str, content: str):
    """Post agent message to discussion channel (via DB)."""
    import crud as crud_module
    entry = {
        "agent_id": agent_id,
        "content": f"[{agent_name}] {content[:500]}",
        "msg_type": "agent",
        "timestamp": datetime.now().isoformat(),
    }
    try:
        await crud_module.add_discussion(db, entry)
    except Exception:
        pass
