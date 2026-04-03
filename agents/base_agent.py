"""
Base Agent — базовый класс для всех агентов Animation Studio v2
Интеграция с OpenRouter API, сохранение состояния и истории чата.
"""
import httpx
import json
import os
import tempfile
import threading
from datetime import datetime
from pypdf import PdfReader

from config import OPENROUTER_API_KEY

# Пути
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_PATH = os.path.join(PROJECT_ROOT, "memory")
STATE_FILE = os.path.join(MEMORY_PATH, "agents_state.json")
ATTACHMENTS_DIR = os.path.join(MEMORY_PATH, "attachments")

TEXT_READABLE_EXTENSIONS = {".txt", ".md", ".json"}
ATTACHMENT_CONTEXT_LIMIT = 3
ATTACHMENT_TEXT_PREVIEW_LIMIT = 6000
PDF_MIN_TEXT_LENGTH = 80
PDF_MIN_ALNUM_COUNT = 20
PDF_MAX_BYTES = 8 * 1024 * 1024
PDF_MAX_PAGES = 120
PDF_PAGE_SCAN_LIMIT = 20

# Глобальная блокировка для записи в agents_state.json
_state_lock = threading.Lock()


class BaseAgent:
    """Базовый агент с чатом через OpenRouter API."""

    def __init__(self, agent_id, name, role, model, instructions, status="idle", chat_history=None, attachments=None, attachment_objects=None):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.model = model
        self.instructions = instructions
        self.status = status
        self.attachments = attachments or [
            item.get("filename")
            for item in (attachment_objects or [])
            if isinstance(item, dict) and item.get("filename")
        ]
        self.attachment_objects = self._normalize_attachment_objects(attachment_objects or [], self.attachments)
        self.chat_history = chat_history or []

    async def chat(self, message):
        """Отправить сообщение агенту, получить ответ через OpenRouter."""
        self.status = "working"

        # Сохраняем сообщение пользователя
        self.chat_history.append({
            "role": "user",
            "content": message,
            "time": datetime.now().isoformat()
        })

        # Attachment system-блок собирается только на лету для запроса к модели
        # и НИКОГДА не сохраняется в chat_history.
        context = self._build_context()

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:7860",
                        "X-Title": "Animation Studio v2"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": self.instructions},
                            *self._build_attachment_messages(),
                            *context
                        ]
                    }
                )
                data = response.json()

                if response.status_code >= 400:
                    error_obj = data.get("error", {}) if isinstance(data, dict) else {}
                    error_message = error_obj.get("message") or data.get("message") or response.text
                    reply = f"OpenRouter {response.status_code}: {error_message}"
                elif not isinstance(data, dict) or "choices" not in data or not data.get("choices"):
                    reply = f"OpenRouter: неожиданный формат ответа: {str(data)[:300]}"
                else:
                    reply = data["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            reply = "OpenRouter: таймаут запроса"
        except httpx.ConnectError as e:
            reply = f"OpenRouter: ошибка соединения: {str(e)}"
        except Exception as e:
            reply = f"Ошибка API: {str(e)}"

        # Сохраняем ответ
        self.chat_history.append({
            "role": "assistant",
            "content": reply,
            "time": datetime.now().isoformat()
        })

        self.status = "idle"
        self._save_state()
        return reply

    def _build_context(self):
        """Построить контекст из истории чата. Без дублирования."""
        messages = []
        for msg in self.chat_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        return messages

    def _normalize_attachment_objects(self, attachment_objects, attachments):
        normalized = []
        seen = set()

        for item in attachment_objects or []:
            if not isinstance(item, dict):
                continue
            filename = item.get("filename") or item.get("stored_filename") or item.get("name")
            if not filename or filename in seen:
                continue
            ext = os.path.splitext(filename)[1].lower()
            uploaded_at = item.get("uploaded_at") or self._guess_uploaded_at(filename)
            pdf_preview = self._read_pdf_preview(item.get("path") or os.path.join(ATTACHMENTS_DIR, filename)) if ext == ".pdf" else ""
            is_text_readable = bool(pdf_preview) if ext == ".pdf" else item.get("is_text_readable", ext in TEXT_READABLE_EXTENSIONS)
            unreadable_reason = "" if is_text_readable else (item.get("unreadable_reason") or ("PDF без текстового слоя не читается" if ext == ".pdf" else "не читается моделью"))
            normalized.append({
                "filename": filename,
                "original_name": item.get("original_name") or filename,
                "path": item.get("path") or os.path.join(ATTACHMENTS_DIR, filename),
                "content_type": item.get("content_type") or self._guess_content_type(ext),
                "size_bytes": item.get("size_bytes", self._guess_file_size(filename)),
                "extension": item.get("extension") or ext,
                "uploaded_at": uploaded_at,
                "is_text_readable": is_text_readable,
                "unreadable_reason": unreadable_reason,
            })
            seen.add(filename)

        for filename in attachments or []:
            if not filename or filename in seen:
                continue
            ext = os.path.splitext(filename)[1].lower()
            normalized.append({
                "filename": filename,
                "original_name": filename,
                "path": os.path.join(ATTACHMENTS_DIR, filename),
                "content_type": self._guess_content_type(ext),
                "size_bytes": self._guess_file_size(filename),
                "extension": ext,
                "uploaded_at": self._guess_uploaded_at(filename),
                "is_text_readable": ext in TEXT_READABLE_EXTENSIONS,
                "unreadable_reason": "" if ext in TEXT_READABLE_EXTENSIONS else "не читается моделью",
            })
            seen.add(filename)

        return sorted(normalized, key=lambda item: item.get("uploaded_at") or "", reverse=True)

    def _build_attachment_messages(self):
        attachment_block = self._build_attachment_system_block()
        if not attachment_block:
            return []
        return [{"role": "system", "content": attachment_block}]

    def _build_attachment_system_block(self):
        sorted_attachments = sorted(
            self.attachment_objects,
            key=lambda item: item.get("uploaded_at") or "",
            reverse=True,
        )
        latest_text_attachments = [
            item for item in sorted_attachments if item.get("is_text_readable")
        ][:ATTACHMENT_CONTEXT_LIMIT]

        if not sorted_attachments:
            return ""

        lines = [
            "В систему загружены активные файлы агента. Используй этот блок как дополнительный контекст.",
            "Этот attachment-блок собран на лету для текущего запроса и не должен считаться частью chat_history.",
            f"Всего активных вложений: {len(sorted_attachments)}.",
        ]

        for index, item in enumerate(sorted_attachments, start=1):
            filename = item.get("original_name") or item.get("filename") or f"file_{index}"
            uploaded_at = item.get("uploaded_at") or ""
            size_bytes = item.get("size_bytes")
            ext = (item.get("extension") or os.path.splitext(filename)[1].lower())
            is_text_readable = bool(item.get("is_text_readable"))

            lines.append(f"[{index}] {filename}")
            lines.append(f"- uploaded_at: {uploaded_at}")
            lines.append(f"- type: {ext or 'unknown'}")
            if size_bytes is not None:
                lines.append(f"- size_bytes: {size_bytes}")
            lines.append(f"- is_text_readable: {str(is_text_readable).lower()}")

            if is_text_readable and item in latest_text_attachments:
                text_preview = self._read_attachment_preview(item)
                if text_preview:
                    lines.append("- content_preview:")
                    lines.append(text_preview)
                else:
                    lines.append("- content_preview: недоступно")
            elif is_text_readable:
                lines.append("- content_preview: пропущено (не входит в последние 3 читаемых файла)")
            else:
                lines.append("- metadata_only: true")
                reason = item.get("unreadable_reason") or "файл не читается моделью, нужен текстовый формат или ручная вставка"
                lines.append(f"- note: {reason}")

        return "\n".join(lines)

    def _read_attachment_preview(self, attachment):
        path = attachment.get("path")
        if not path or not os.path.exists(path):
            return ""
        try:
            extension = (attachment.get("extension") or os.path.splitext(path)[1].lower())
            if extension == ".pdf":
                return self._read_pdf_preview(path)
            with open(path, "r", encoding="utf-8") as f:
                raw_text = f.read()
            if extension == ".json":
                try:
                    parsed = json.loads(raw_text)
                    raw_text = json.dumps(parsed, ensure_ascii=False, indent=2)
                except json.JSONDecodeError:
                    pass
            return raw_text[:ATTACHMENT_TEXT_PREVIEW_LIMIT]
        except Exception:
            return ""

    def _read_pdf_preview(self, path):
        try:
            if os.path.getsize(path) > PDF_MAX_BYTES:
                return ""
            reader = PdfReader(path)
            if reader.is_encrypted or len(reader.pages) > PDF_MAX_PAGES:
                return ""

            chunks = []
            current_length = 0
            for page in reader.pages[:PDF_PAGE_SCAN_LIMIT]:
                page_text = page.extract_text() or ""
                normalized = " ".join(page_text.split())
                if not normalized:
                    continue
                remaining = ATTACHMENT_TEXT_PREVIEW_LIMIT - current_length
                if remaining <= 0:
                    break
                excerpt = normalized[:remaining]
                chunks.append(excerpt)
                current_length += len(excerpt)
                if current_length >= ATTACHMENT_TEXT_PREVIEW_LIMIT:
                    break

            preview = "\n".join(chunks)
            normalized_preview = " ".join(preview.split())
            alnum_count = sum(1 for char in normalized_preview if char.isalnum())
            if len(normalized_preview) >= PDF_MIN_TEXT_LENGTH or alnum_count >= PDF_MIN_ALNUM_COUNT:
                return preview
            return ""
        except Exception:
            return ""

    def _guess_uploaded_at(self, filename):
        path = os.path.join(ATTACHMENTS_DIR, filename)
        if os.path.exists(path):
            return datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
        return ""

    def _guess_file_size(self, filename):
        path = os.path.join(ATTACHMENTS_DIR, filename)
        if os.path.exists(path):
            return os.path.getsize(path)
        return None

    def _guess_content_type(self, ext):
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

    def _save_state(self):
        """Атомарно сохранить состояние агента в agents_state.json."""
        with _state_lock:
            if not os.path.exists(STATE_FILE):
                return

            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

            state[self.agent_id] = {
                "name": self.name,
                "role": self.role,
                "model": self.model,
                "status": self.status,
                "instructions": self.instructions,
                "attachments": self.attachments,
                "attachment_objects": self.attachment_objects,
                "chat_history": self.chat_history[-50:]  # Храним последние 50 сообщений
            }

            # Атомарная запись через временный файл
            dir_name = os.path.dirname(STATE_FILE)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                    json.dump(state, tmp, ensure_ascii=False, indent=2)
                os.replace(tmp_path, STATE_FILE)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

    def to_dict(self):
        """Сериализация в dict для API."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "model": self.model,
            "status": self.status,
            "instructions": self.instructions,
            "attachments": self.attachments,
            "attachment_objects": self.attachment_objects,
            "chat_history": self.chat_history[-20:]  # Для API — последние 20
        }
