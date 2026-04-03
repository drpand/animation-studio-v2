"""
Base Tool — единый формат ответа и rate limiter для всех инструментов.
"""
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from config import RATE_LIMIT_REQUESTS_PER_MIN


@dataclass
class ToolResponse:
    """Унифицированный ответ от любого инструмента."""
    status: str  # "success" | "error" | "rate_limited" | "timeout"
    result_url: Optional[str] = None
    error: Optional[str] = None
    elapsed_ms: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "result_url": self.result_url,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "metadata": self.metadata,
        }


class RateLimiter:
    """Глобальный rate limiter для всех инструментов."""

    def __init__(self, max_requests: int = RATE_LIMIT_REQUESTS_PER_MIN):
        self.max_requests = max_requests
        self.requests: deque = deque()

    def is_allowed(self) -> tuple[bool, int]:
        """Возвращает (разрешено, секунд до следующего запроса)."""
        now = time.time()

        # Удаляем запросы старше 60 сек
        while self.requests and self.requests[0] < now - 60:
            self.requests.popleft()

        if len(self.requests) >= self.max_requests:
            wait_time = int(60 - (now - self.requests[0])) + 1
            return False, wait_time

        self.requests.append(now)
        return True, 0

    def get_usage(self) -> dict:
        """Текущее использование."""
        now = time.time()
        while self.requests and self.requests[0] < now - 60:
            self.requests.popleft()
        return {
            "used": len(self.requests),
            "limit": self.max_requests,
            "remaining": max(0, self.max_requests - len(self.requests)),
        }


# Глобальный экземпляр
rate_limiter = RateLimiter()
