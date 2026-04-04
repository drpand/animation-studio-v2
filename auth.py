"""
Auth — HTTP Basic Auth middleware для FastAPI.
"""
import secrets
from fastapi import Request, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.middleware.base import BaseHTTPMiddleware

from config import AUTH_USERNAME, AUTH_PASSWORD

security = HTTPBasic()


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware для проверки HTTP Basic Auth."""

    async def dispatch(self, request: Request, call_next):
        # Разрешаем доступ к healthcheck и статике без авторизации
        if request.url.path in ("/health", "/docs", "/openapi.json") or request.url.path.startswith("/static"):
            return await call_next(request)

        try:
            credentials = await security(request)
        except Exception:
            raise HTTPException(
                status_code=401,
                detail="Неверные учетные данные",
                headers={"WWW-Authenticate": "Basic"},
            )

        correct_username = secrets.compare_digest(credentials.username, AUTH_USERNAME)
        correct_password = secrets.compare_digest(credentials.password, AUTH_PASSWORD)

        if not (correct_username and correct_password):
            raise HTTPException(
                status_code=401,
                detail="Неверные учетные данные",
                headers={"WWW-Authenticate": "Basic"},
            )

        return await call_next(request)
