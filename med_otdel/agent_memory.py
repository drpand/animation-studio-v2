"""
Agent Memory & Learning System — МЕД-ОТДЕЛ v2
Адаптировано из Animation Studio v1 для v2.

Изменения:
- Убраны импорты из v1 (studio, state_machine)
- call_llm через httpx + OpenRouter API
- AGENT_LEARNING_DIR → med_otdel/versions/
- rollback_to_backup() удалён (правило: "Откат запрещён. Только вперёд.")
"""
import os
import json
import asyncio
import threading
import httpx
from datetime import datetime
from typing import Dict, List, Optional

from config import OPENROUTER_API_KEY

# Пути — внутри проекта, не в ~/.qwen
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_LEARNING_DIR = os.path.join(PROJECT_ROOT, "med_otdel", "versions")
FAILURES_LOG = os.path.join(PROJECT_ROOT, "med_otdel", "agent_failures.log")

# Глобальные блокировки для предотвращения concurrent write
_file_locks: dict[str, asyncio.Lock] = {}
_thread_locks: dict[str, threading.Lock] = {}


def _get_async_lock(file_path: str) -> asyncio.Lock:
    """Получить asyncio lock для файла"""
    if file_path not in _file_locks:
        _file_locks[file_path] = asyncio.Lock()
    return _file_locks[file_path]


def _get_thread_lock(file_path: str) -> threading.Lock:
    """Получить threading lock для файла"""
    if file_path not in _thread_locks:
        _thread_locks[file_path] = threading.Lock()
    return _thread_locks[file_path]


async def call_llm(system_prompt: str, user_prompt: str, model: str = "google/gemini-3-flash-preview") -> tuple[str, dict]:
    """Запрос к OpenRouter API. Возвращает (text, usage_info)."""
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
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            }
        )
        data = response.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        return text, usage


class AgentMemory:
    """Память одного агента (fixer, writer, critic)"""

    def __init__(self, role: str):
        self.role = role
        self.memory_file = os.path.join(AGENT_LEARNING_DIR, f"{role}.json")
        self.data = self._load()

    def _load(self) -> dict:
        """Загрузить память из файла"""
        lock = _get_thread_lock(self.memory_file)
        with lock:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    return json.load(f)

            # Новая память с расширенной структурой
            return {
                "role": self.role,
                "current_version": "v1",
                "current_prompt": None,
                "history": {},
                "failures": [],
                "lessons": [],
                "total_failures": 0,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

    async def save_async(self):
        """Асинхронное сохранение памяти"""
        lock = _get_async_lock(self.memory_file)
        async with lock:
            self.data["updated_at"] = datetime.now().isoformat()
            os.makedirs(AGENT_LEARNING_DIR, exist_ok=True)
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)

    def save(self):
        """Синхронное сохранение памяти"""
        lock = _get_thread_lock(self.memory_file)
        with lock:
            self.data["updated_at"] = datetime.now().isoformat()
            os.makedirs(AGENT_LEARNING_DIR, exist_ok=True)
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)

    async def add_failure_async(self, error_type: str, error_text: str, context: dict = None):
        """Асинхронное добавление ошибки"""
        lock = _get_async_lock(self.memory_file)
        async with lock:
            failure = {
                "timestamp": datetime.now().isoformat(),
                "type": error_type,
                "text": error_text[:1000],
                "context": context or {}
            }
            self.data["failures"].append(failure)
            self.data["updated_at"] = datetime.now().isoformat()

            os.makedirs(AGENT_LEARNING_DIR, exist_ok=True)
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)

            # Логирование в глобальный лог
            log_lock = _get_async_lock(FAILURES_LOG)
            async with log_lock:
                with open(FAILURES_LOG, "a", encoding="utf-8") as f:
                    f.write(f"[{self.role}] {error_type}: {error_text[:200]}\n")

    def add_failure(self, error_type: str, error_text: str, context: dict = None):
        """Добавить запись об ошибке"""
        lock = _get_thread_lock(self.memory_file)
        with lock:
            failure = {
                "timestamp": datetime.now().isoformat(),
                "type": error_type,
                "text": error_text[:1000],
                "context": context or {}
            }
            self.data["failures"].append(failure)
            self.data["updated_at"] = datetime.now().isoformat()

            os.makedirs(AGENT_LEARNING_DIR, exist_ok=True)
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)

            # Логирование в глобальный лог
            log_lock = _get_thread_lock(FAILURES_LOG)
            with log_lock:
                with open(FAILURES_LOG, "a", encoding="utf-8") as f:
                    f.write(f"[{self.role}] {error_type}: {error_text[:200]}\n")

    def get_failure_count(self, error_type: str) -> int:
        """Посчитать количество однотипных ошибок"""
        return sum(1 for f in self.data["failures"] if f["type"] == error_type)

    def set_current_prompt(self, prompt: str):
        """Установить текущий промпт агента"""
        # Старый промпт уходит в историю, НЕ в backup (откат запрещён)
        current_version = self.data.get("current_version", "v1")
        if self.data["current_prompt"]:
            if "history" not in self.data:
                self.data["history"] = {}
            self.data["history"][current_version] = {
                "prompt": self.data["current_prompt"],
                "archived_at": datetime.now().isoformat()
            }

        self.data["current_prompt"] = prompt
        self.save()

    def get_prompt(self) -> Optional[str]:
        """Получить текущий промпт"""
        return self.data.get("current_prompt")

    def add_lesson(self, lesson: str):
        """Добавить извлечённый урок"""
        self.data["lessons"].append({
            "timestamp": datetime.now().isoformat(),
            "lesson": lesson
        })
        self.save()

    def should_learn(self, error_type: str, threshold: int = 2) -> bool:
        """Проверить стоит ли запускать обучение (2+ однотипные ошибки)"""
        return self.get_failure_count(error_type) >= threshold

    def get_consecutive_failures(self) -> int:
        """Посчитать количество провалов подряд (с конца списка)"""
        count = 0
        for f in reversed(self.data["failures"]):
            ftype = f.get("type", "")
            if ftype in ("evaluation_fail", "critic_fail") or f.get("status") == "fail":
                count += 1
            else:
                break
        return count

    def get_next_version(self) -> str:
        """Получить следующую версию агента"""
        current = self.data.get("current_version", "v1")
        version_num = int(current[1:]) if current.startswith("v") else 1
        return f"v{version_num + 1}"

    async def evolve_agent(self, role: str, error_type: str, error_text: str):
        """
        Эволюция агента после 3+ падений.
        Создаёт новую версию промпта с учётом ошибки.
        Откат запрещён — только вперёд.
        """
        current_version = self.data.get("current_version", "v1")
        current_prompt = self.data.get("current_prompt", "")

        # Сохраняем текущую версию в историю
        if "history" not in self.data:
            self.data["history"] = {}

        self.data["history"][current_version] = {
            "prompt": current_prompt,
            "died_on": error_type,
            "timestamp": datetime.now().isoformat()
        }

        # Удаляем старые версии (храним максимум 5)
        history_keys = list(self.data["history"].keys())
        if len(history_keys) > 5:
            for old_key in history_keys[:-5]:
                del self.data["history"][old_key]

        # Запрашиваем улучшенный промпт через OpenRouter
        orchestrator_system = "Ты эксперт по промпт-инженерии. Твоя задача — улучшать системные промпты AI-агентов."
        orchestrator_prompt = f"""Агент {role} упал с ошибкой: {error_text[:500]}

Его текущий промпт (версия {current_version}):
{current_prompt[:7000]}

Придумай ОДНО конкретное правило которое предотвратит эту ошибку.
Добавь это правило в НАЧАЛО промпта.
Верни только улучшенный промпт, ничего лишнего.
Максимум 8000 символов."""

        new_prompt, _ = await call_llm(orchestrator_system, orchestrator_prompt)

        # Усекаем до 8000 символов
        new_prompt = new_prompt[:8000]

        # Сохраняем новую версию
        next_version = self.get_next_version()
        self.data["current_version"] = next_version
        self.data["current_prompt"] = new_prompt
        # backup_prompt УДАЛЁН — откат запрещён

        # Добавляем урок
        lesson = f"{next_version}: Исправлена ошибка {error_type}"
        self.data["lessons"].append({
            "timestamp": datetime.now().isoformat(),
            "lesson": lesson,
            "version": next_version
        })

        self.data["total_failures"] = self.data.get("total_failures", 0) + 1
        self.data["updated_at"] = datetime.now().isoformat()

        # Сохраняем
        await self.save_async()

        print(f"[MED-ОТДЕЛ] Агент {role} эволюционировал: {current_version} -> {next_version}")
        print(f"   Урок: {lesson}")

        return next_version


def log_agent_error(role: str, error_type: str, error_text: str, context: dict = None):
    """Быстрое логирование ошибки агента"""
    memory = AgentMemory(role)
    memory.add_failure(error_type, error_text, context)
    return memory.should_learn(error_type)


def get_agent_prompt(role: str) -> Optional[str]:
    """Получить промпт агента из памяти"""
    memory = AgentMemory(role)
    return memory.get_prompt()


def save_agent_prompt(role: str, prompt: str):
    """Сохранить промпт агента в память"""
    memory = AgentMemory(role)
    memory.set_current_prompt(prompt)


# ─── Декоратор для автоматического логирования ошибок ─────────────────────────

def monitor_agent(role: str):
    """
    Декоратор для мониторинга ошибок агента.
    Автоматически логирует ошибки и запускает эволюцию при 3+ ошибках.
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                error_type = type(e).__name__
                error_text = str(e)

                # Асинхронное логирование ошибки
                memory = AgentMemory(role)
                await memory.add_failure_async(error_type, error_text)

                should_learn = memory.should_learn(error_type)

                print(f"[MED-ОТДЕЛ] Агент {role} упал: {error_type}")
                print(f"   Ошибок этого типа: {memory.get_failure_count(error_type)}")

                if should_learn:
                    print(f"   Запускаю эволюцию агента {role}...")
                    try:
                        new_version = await memory.evolve_agent(role, error_type, error_text)
                        print(f"   Агент {role} эволюционировал в {new_version}!")
                    except Exception as evolve_error:
                        print(f"   Ошибка эволюции: {evolve_error}")

                # Пробрасываем ошибку дальше
                raise
        return wrapper
    return decorator
