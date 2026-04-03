"""
Animation Studio v2 — РОДИНА
FastAPI сервер, точка входа.
"""
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse

# Загружаем .env ДО импорта config
load_dotenv()

from config import PORT, PROJECT_NAME
from api.agents_api import router as agents_router
from api.tasks_api import router as tasks_router
from api.chat_api import router as chat_router
from api.med_otdel_api import router as med_otdel_router
from api.hr_api import router as hr_router
from api.tools_api import router as tools_router

# Абсолютные пути
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")
TOOLS_CACHE_DIR = os.path.join(PROJECT_ROOT, "memory", "tools_cache")

app = FastAPI(title=f"Animation Studio v2 — {PROJECT_NAME}")

# API роуты (префиксы задаются здесь, в роут-файлах префиксов нет)
app.include_router(agents_router, prefix="/api/agents", tags=["agents"])
app.include_router(tasks_router, prefix="/api/tasks", tags=["tasks"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(med_otdel_router, prefix="/api/med-otdel", tags=["med-otdel"])
app.include_router(hr_router, prefix="/api/hr", tags=["hr"])
app.include_router(tools_router, prefix="/api/tools", tags=["tools"])

# Статика
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Кэш инструментов (изображения, аудио)
if os.path.exists(TOOLS_CACHE_DIR):
    app.mount("/static/tools_cache", StaticFiles(directory=TOOLS_CACHE_DIR), name="tools_cache")


@app.get("/")
async def index():
    """Главная страница — офис."""
    path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(path):
        return HTMLResponse(
            "<h1>Ошибка: static/index.html не найден</h1>"
            "<p>Убедитесь что фронтенд файлы находятся в папке static/</p>",
            status_code=500
        )
    return FileResponse(path)


@app.get("/health")
async def health():
    """Проверка здоровья сервера."""
    return {"status": "ok", "project": PROJECT_NAME}


if __name__ == "__main__":
    import asyncio
    from hypercorn.config import Config
    from hypercorn.asyncio import serve

    # Fix for Python 3.13 on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    config = Config()
    config.bind = [f"0.0.0.0:{PORT}"]

    print(f"\n{'='*40}")
    print(f"  ANIMATION STUDIO v2 — {PROJECT_NAME}")
    print(f"  http://localhost:{PORT}")
    print(f"{'='*40}\n")

    asyncio.run(serve(app, config))
