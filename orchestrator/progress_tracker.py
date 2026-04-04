"""
Progress Tracker — хранение и управление задачами Orchestrator.
Thread-safe, с восстановлением при рестарте.
"""
import os
import json
import tempfile
import threading
from datetime import datetime

from orchestrator.task_chain import TaskChain

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_FILE = os.path.join(PROJECT_ROOT, "memory", "orchestrator_tasks.json")

_tracker_lock = threading.Lock()


class ProgressTracker:
    def __init__(self):
        self._tasks: dict[str, TaskChain] = {}
        self._cancel_events: dict[str, bool] = {}
        self._load_tasks()

    def _load_tasks(self):
        """Загрузить задачи из файла. Восстановить при рестарте."""
        if os.path.exists(TASKS_FILE):
            try:
                with open(TASKS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for task_data in data.get("tasks", []):
                    chain = TaskChain.from_dict(task_data)
                    # Задачи в статусе running → interrupted
                    if chain.status == "running":
                        chain.status = "interrupted"
                        chain.cancelled = True
                    self._tasks[chain.task_id] = chain
                    self._cancel_events[chain.task_id] = chain.cancelled
            except Exception:
                pass

    def _save_tasks(self):
        """Атомарно сохранить все задачи."""
        dir_name = os.path.dirname(TASKS_FILE)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(
                    {"tasks": [t.to_dict() for t in self._tasks.values()]},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            os.replace(tmp_path, TASKS_FILE)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def add_task(self, chain: TaskChain):
        with _tracker_lock:
            self._tasks[chain.task_id] = chain
            self._cancel_events[chain.task_id] = False
            self._save_tasks()

    def get_task(self, task_id: str) -> TaskChain | None:
        return self._tasks.get(task_id)

    def update_task(self, chain: TaskChain):
        with _tracker_lock:
            self._tasks[chain.task_id] = chain
            self._save_tasks()

    def cancel_task(self, task_id: str):
        with _tracker_lock:
            if task_id in self._tasks:
                self._tasks[task_id].cancelled = True
                self._tasks[task_id].status = "cancelled"
                self._cancel_events[task_id] = True
                self._save_tasks()

    def is_cancelled(self, task_id: str) -> bool:
        return self._cancel_events.get(task_id, False)

    def get_all_tasks(self) -> list[dict]:
        return [t.to_dict() for t in self._tasks.values()]

    def get_active_tasks(self) -> list[dict]:
        return [
            t.to_dict()
            for t in self._tasks.values()
            if t.status in ("pending", "running")
        ]


# Глобальный экземпляр
tracker = ProgressTracker()
