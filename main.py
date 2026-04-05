"""
Animation Studio v2 — РОДИНА
FastAPI сервер, точка входа.
"""
import os
import json
import time
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

# Загружаем .env ДО импорта config
load_dotenv()

from config import PORT, PROJECT_NAME
from database import init_db, async_session, get_session
from auth import AuthMiddleware
from utils.logger import info, warn, error
from api.agents_api import router as agents_router
from api.tasks_api import router as tasks_router
from api.chat_api import router as chat_router
from api.med_otdel_api import router as med_otdel_router
from api.hr_api import router as hr_router
from api.tools_api import router as tools_router
from api.discussion_api import router as discussion_router
from api.hr_init_api import router as hr_init_router
from api.orchestrator_api import router as orchestrator_router
from api.project_api import router as project_router
from api.episodes_api import router as episodes_router
from api.characters_api import router as characters_router
from api.cv_check_api import router as cv_check_router

# Абсолютные пути
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")
TOOLS_CACHE_DIR = os.path.join(PROJECT_ROOT, "memory", "tools_cache")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/Shutdown hooks."""
    # Startup
    info("Initializing database...")
    await init_db()
    info("Database initialized.")
    
    # Уровень 3: МЕД-ОТДЕЛ — фоновый мониторинг студии
    import asyncio
    from med_otdel.med_core import log_med_action
    from database import async_session
    import crud
    
    async def med_otdel_monitor():
        """Фоновая задача МЕД-ОТДЕЛА — мониторинг каждые 30 секунд."""
        while True:
            try:
                async with async_session() as db:
                    # Проверяем процент агентов в error
                    all_agents = await crud.get_all_agents(db)
                    if all_agents:
                        error_count = sum(1 for a in all_agents if a.status == "error")
                        error_pct = error_count / len(all_agents)
                        
                        if error_pct >= 0.5:
                            # studio_alert — 50%+ агентов в красном
                            log_med_action("studio_alert", f"{error_pct*100:.0f}% агентов в error. Студия приостановлена.")
                            warn(f"STUDIO ALERT: {error_pct*100:.0f}% агентов в error")
                        
                        # agent_heal — логируем агентов в error
                        for agent in all_agents:
                            if agent.status == "error":
                                log_med_action("agent_error_detected", f"Агент {agent.agent_id} в error статусе", agent.agent_id)
                    
                    # chain_heal — проверяем мед логи на повторяющиеся ошибки
                    logs = await crud.get_med_logs(db, limit=50)
                    fail_count = sum(1 for log in logs if "fail" in log.action.lower())
                    if fail_count > 10:
                        log_med_action("chain_heal_triggered", f"Обнаружено {fail_count} провалов в последних 50 логах")
                    
            except Exception as e:
                warn(f"МЕД-ОТДЕЛ ошибка мониторинга: {e}")
            
            await asyncio.sleep(30)  # Проверка каждые 30 секунд
    
    monitor_task = asyncio.create_task(med_otdel_monitor())
    info("МЕД-ОТДЕЛ мониторинг запущен (каждые 30 сек)")
    
    yield
    
    # Shutdown
    monitor_task.cancel()
    info("МЕД-ОТДЕЛ мониторинг остановлен.")
    info("Server shutting down.")


class UTF8JSONResponse(JSONResponse):
    """JSON response с корректным UTF-8 (без escape русских символов)."""
    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, allow_nan=False).encode("utf-8")


app = FastAPI(title=f"Animation Studio v2 — {PROJECT_NAME}", lifespan=lifespan, default_response_class=UTF8JSONResponse)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Логирование запросов и ошибок."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        try:
            response = await call_next(request)
            duration = time.time() - start_time
            if response.status_code >= 500:
                error(f"{request.method} {request.url.path} -> {response.status_code} ({duration:.2f}s)")
            elif request.url.path.startswith("/api/"):
                info(f"{request.method} {request.url.path} -> {response.status_code} ({duration:.2f}s)")
            return response
        except Exception as e:
            error(f"{request.method} {request.url.path} -> EXCEPTION: {str(e)}")
            raise


# Logging first, then Auth (disabled for now - local dev)
app.add_middleware(LoggingMiddleware)
# app.add_middleware(AuthMiddleware)  # Uncomment when ready

# API роуты (префиксы задаются здесь, в роут-файлах префиксов нет)
app.include_router(agents_router, prefix="/api/agents", tags=["agents"])
app.include_router(tasks_router, prefix="/api/tasks", tags=["tasks"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(med_otdel_router, prefix="/api/med-otdel", tags=["med-otdel"])
app.include_router(hr_router, prefix="/api/hr", tags=["hr"])
app.include_router(tools_router, prefix="/api/tools", tags=["tools"])
app.include_router(discussion_router, prefix="/api/discussion", tags=["discussion"])
app.include_router(hr_init_router, prefix="/api/hr/init", tags=["hr-init"])
app.include_router(orchestrator_router, prefix="/api/orchestrator", tags=["orchestrator"])
app.include_router(project_router, prefix="/api/project", tags=["project"])
app.include_router(episodes_router, prefix="/api/episodes", tags=["episodes"])
app.include_router(characters_router, prefix="/api/characters", tags=["characters"])
app.include_router(cv_check_router, prefix="/api/tools", tags=["cv-check"])

# Статика с отключением кэша
class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

app.mount("/static", NoCacheStaticFiles(directory=STATIC_DIR), name="static")

# Кэш инструментов (изображения, аудио)
IMAGES_CACHE_DIR = os.path.join(PROJECT_ROOT, "memory", "tools_cache", "images")
os.makedirs(IMAGES_CACHE_DIR, exist_ok=True)
app.mount("/tools_cache", NoCacheStaticFiles(directory=IMAGES_CACHE_DIR), name="tools_cache")


@app.get("/")
async def index():
    """Главная страница — офис."""
    path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(path):
        error("static/index.html not found")
        return HTMLResponse(
            "<h1>Ошибка: static/index.html не найден</h1>"
            "<p>Убедитесь что фронтенд файлы находятся в папке static/</p>",
            status_code=500
        )
    return FileResponse(path)


@app.get("/health")
async def health():
    """Проверка здоровья сервера."""
    return UTF8JSONResponse(content={"status": "ok", "project": PROJECT_NAME})


@app.get("/init")
async def init_page():
    """Страница инициализации проекта."""
    path = os.path.join(STATIC_DIR, "init.html")
    if not os.path.exists(path):
        return HTMLResponse("<h1>init.html не найден</h1>", status_code=500)
    return FileResponse(path)


if __name__ == "__main__":
    import asyncio
    from hypercorn.config import Config
    from hypercorn.asyncio import serve

    # Fix for Python 3.13 on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    config = Config()
    config.bind = [f"0.0.0.0:{PORT}"]

    info(f"Server starting on port {PORT}")
    print(f"\n{'='*40}")
    print(f"  ANIMATION STUDIO v2 — {PROJECT_NAME}")
    print(f"  http://localhost:{PORT}")
    print(f"  Logs: logs/app.log")
    print(f"{'='*40}\n")

    asyncio.run(serve(app, config))
