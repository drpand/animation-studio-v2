"""
Orchestrator API — управление цепочками задач.
Префикс роутов задаётся в main.py: /api/orchestrator
"""
import asyncio
import json
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from models import SubmitTaskRequest, InterveneRequest
from config import PROJECT_NAME

class ScenePipelineRequest(BaseModel):
    season: int = 1
    episode: int = 1
    scene: int = 1
    pdf_context: str = ""
    description: str = ""

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_FILE = os.path.join(PROJECT_ROOT, "orchestrator", "agent_registry.json")


@router.post("/submit")
async def submit_task(req: SubmitTaskRequest, db: AsyncSession = Depends(get_session)):
    """Отправить задачу Orchestrator'у."""
    if not req.description.strip():
        raise HTTPException(400, "Описание задачи не может быть пустым")

    chain = await _build_task_chain(req.description)
    if not chain or not chain.steps:
        raise HTTPException(400, "Не удалось построить цепочку для задачи")

    task_data = {
        "task_id": chain.task_id, "description": chain.description,
        "status": "pending", "current_step": 0,
    }
    task = await crud.create_orchestrator_task(db, task_data)

    for step_data in chain.steps:
        await crud.add_orchestrator_step(db, chain.task_id, {
            "agent_id": step_data.get("agent_id", ""),
            "input": step_data.get("input", ""),
            "status": "pending",
        })

    # Запуск в фоне
    asyncio.create_task(_execute_chain(chain.task_id, db))

    return {"ok": True, "task_id": chain.task_id, "steps": len(chain.steps)}


@router.get("/status/{task_id}")
async def get_task_status(task_id: str, db: AsyncSession = Depends(get_session)):
    """Получить статус задачи."""
    task = await crud.get_orchestrator_task(db, task_id)
    if not task:
        raise HTTPException(404, f"Задача '{task_id}' не найдена")
    steps = await crud.get_orchestrator_steps(db, task_id)
    return {
        "task_id": task.task_id, "description": task.description,
        "status": task.status, "current_step": task.current_step,
        "result": task.result[:2000] if task.result else "",
        "steps": [{"agent_id": s.agent_id, "status": s.status, "output": s.output[:500] if s.output else ""} for s in steps],
    }


@router.post("/intervene/{task_id}")
async def intervene_task(task_id: str, req: InterveneRequest, db: AsyncSession = Depends(get_session)):
    """Вмешаться в выполнение."""
    if req.action == "cancel":
        await crud.update_orchestrator_task(db, task_id, {"status": "cancelled", "cancelled": True})
        return {"ok": True, "message": f"Задача '{task_id}' отменена"}
    raise HTTPException(400, f"Неизвестное действие: {req.action}")


@router.get("/history")
async def get_task_history(db: AsyncSession = Depends(get_session)):
    """История всех задач."""
    tasks = await crud.get_orchestrator_tasks(db) if hasattr(crud, 'get_orchestrator_tasks') else []
    return {"tasks": tasks}


@router.get("/active")
async def get_active_tasks(db: AsyncSession = Depends(get_session)):
    """Активные задачи."""
    tasks = await crud.get_active_orchestrator_tasks(db)
    result = []
    for t in tasks:
        steps = await crud.get_orchestrator_steps(db, t.task_id)
        result.append({
            "task_id": t.task_id, "description": t.description,
            "status": t.status, "current_step": t.current_step,
            "steps": len(steps), "progress": (t.current_step / max(len(steps), 1)) * 100,
        })
    return {"tasks": result}


@router.get("/registry")
async def get_agent_registry(db: AsyncSession = Depends(get_session)):
    """Реестр агентов."""
    if os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


async def _build_task_chain(description: str):
    """Построить цепочку через LLM."""
    registry = []
    if os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            registry = json.load(f)

    agents_info = "\n".join(
        f"- {a['id']}: {', '.join(a.get('capabilities', []))}"
        for a in registry if a.get("id") not in ("critic", "fixer")
    )

    system = f"Ты Orchestrator аниме-студии {PROJECT_NAME}. Определи какие агенты нужны для задачи."
    user = f"""Задача: {description}
Доступные агенты:
{agents_info}
Верни СТРОГО JSON массив с ID агентов. Только JSON.
Пример: ["writer", "director", "storyboarder"]"""

    try:
        from med_otdel.agent_memory import call_llm
        import re
        result, _ = await call_llm(system_prompt=system, user_prompt=user)
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            agent_ids = json.loads(json_match.group())
        else:
            agent_ids = ["writer", "director"]
    except Exception:
        agent_ids = ["writer", "director"]

    class SimpleChain:
        def __init__(self):
            import uuid
            self.task_id = f"task_{uuid.uuid4().hex[:8]}"
            self.description = description
            self.steps = []

    chain = SimpleChain()
    for agent_id in agent_ids:
        if any(a.get("id") == agent_id for a in registry):
            chain.steps.append({"agent_id": agent_id, "input": description})

    if not chain.steps:
        chain.steps.append({"agent_id": "writer", "input": description})

    return chain


async def _execute_chain(task_id: str, db):
    """Выполнить цепочку задач."""
    from med_otdel.med_core import run_evaluation as run_critic
    from config import OPENROUTER_API_KEY
    import httpx

    task = await crud.get_orchestrator_task(db, task_id)
    if not task:
        return

    await crud.update_orchestrator_task(db, task_id, {"status": "running"})

    steps = await crud.get_orchestrator_steps(db, task_id)
    previous_output = task.description or ""

    for i, step in enumerate(steps):
        if await _is_cancelled(db, task_id):
            return

        await crud.update_orchestrator_step(db, step.id, {"status": "running", "input": previous_output[:2000]})

        agent = await crud.get_agent(db, step.agent_id)
        if not agent:
            await crud.update_orchestrator_step(db, step.id, {"status": "failed", "error": "Agent not found"})
            continue

        # Call agent
        try:
            from agents.base_agent import _load_constitution, _load_project_context
            constitution = _load_constitution()
            project_context = _load_project_context()
            parts = []
            if constitution:
                parts.extend(["[КОНСТИТУЦИЯ СТУДИИ]", constitution, ""])
            if project_context:
                parts.extend(["[ПРОЕКТ]", project_context, ""])
            parts.extend(["[РОЛЬ]", agent.role])
            if agent.instructions:
                parts.extend(["[ИНСТРУКЦИИ]", agent.instructions])

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                    json={"model": agent.model, "messages": [
                        {"role": "system", "content": "\n".join(parts)},
                        {"role": "user", "content": previous_output[:4000]}
                    ]}
                )
                data = resp.json()
                output = data.get("choices", [{}])[0].get("message", {}).get("content", "Error")
        except Exception as e:
            output = f"Error: {str(e)}"

        await crud.update_orchestrator_step(db, step.id, {"status": "completed", "output": output[:5000]})
        previous_output = output

        # Critic
        if step.agent_id not in ("critic", "fixer"):
            try:
                critic_result = await run_critic(output, step.agent_id)
                await crud.update_orchestrator_step(db, step.id, {
                    "critic_passed": critic_result.get("passed", False),
                    "critic_feedback": critic_result.get("feedback", "")[:500],
                })
            except Exception:
                pass

        await crud.update_orchestrator_task(db, task_id, {"current_step": i + 1, "result": previous_output[:2000]})

    await crud.update_orchestrator_task(db, task_id, {"status": "completed"})


# Глобальное хранилище статусов задач от продюсера
_producer_tasks: dict = {}


@router.post("/task")
async def create_task(req: dict):
    """Продюсер ставит задачу. Оркестратор запускает полный конвейер."""
    from orchestrator.executor import run_scene_pipeline
    from database import async_session
    import uuid

    task_desc = req.get("description", "")
    if not task_desc:
        raise HTTPException(400, "Описание задачи не может быть пустым")

    # Определяем season/episode/scene из описания или используем дефолт
    season = int(req.get("season", 1))
    episode = int(req.get("episode", 1))
    scene = int(req.get("scene", 1))

    # Парсим номер сцены из текста если пользователь указал
    import re
    scene_match = re.search(r'[сc]цен[ауе]?\s*(\d+)', task_desc, re.IGNORECASE)
    if scene_match:
        scene = int(scene_match.group(1))

    episode_match = re.search(r'[эe]пизод\s*(\d+)', task_desc, re.IGNORECASE)
    if episode_match:
        episode = int(episode_match.group(1))

    season_match = re.search(r'[сs]езон\s*(\d+)', task_desc, re.IGNORECASE)
    if season_match:
        season = int(season_match.group(1))
    
    # Парсим количество кадров
    frames_match = re.search(r'(\d+)\s*кадр[аов]?', task_desc, re.IGNORECASE)
    num_frames = int(frames_match.group(1)) if frames_match else 1
    
    from utils.logger import info
    info(f"[PRODUCER] Парсинг: найдено {num_frames} кадров из описания: {task_desc[:100]}")

    task_id = f"producer_{uuid.uuid4().hex[:8]}"
    scene_id = f"{season}_{episode}_{scene}"

    # Защита от двойного запуска
    if scene_id in _running_pipelines:
        raise HTTPException(409, f"Конвейер для сцены {scene_id} уже запущен")

    _running_pipelines.add(scene_id)

    # Инициализируем статус задачи
    _producer_tasks[task_id] = {
        "task_id": task_id,
        "scene_id": scene_id,
        "season": season,
        "episode": episode,
        "scene": scene,
        "description": task_desc,
        "status": "starting",
        "current_step": "",
        "progress": 0,
        "started_at": datetime.now().isoformat(),
        "error": None,
    }

    async def _run_with_cleanup():
        async def _progress(step_name: str, progress: int):
            _producer_tasks[task_id]["current_step"] = step_name
            _producer_tasks[task_id]["progress"] = progress

        try:
            _producer_tasks[task_id]["status"] = "running"
            _producer_tasks[task_id]["current_step"] = "Запуск конвейера..."
            _producer_tasks[task_id]["progress"] = 5
            
            from utils.logger import info, error
            info(f"[PRODUCER] Запуск цикла генерации {num_frames} кадров")

            # Генерируем N кадров (каждый кадр = отдельная сцена)
            for frame_idx in range(num_frames):
                current_scene = scene + frame_idx
                frame_progress_base = int((frame_idx / num_frames) * 90)
                
                info(f"[PRODUCER] Генерация кадра {frame_idx + 1}/{num_frames}, сцена {current_scene}")
                
                await _progress(f"Кадр {frame_idx + 1}/{num_frames}: Кастинг...", frame_progress_base + 5)
                
                async with async_session() as db:
                    result = await run_scene_pipeline(
                        season, episode, current_scene, 
                        f"{task_desc}\n\nКадр {frame_idx + 1} из {num_frames}",
                        db, 
                        progress_callback=lambda step, prog: _progress(
                            f"Кадр {frame_idx + 1}/{num_frames}: {step}", 
                            frame_progress_base + int(prog * 0.9)
                        )
                    )
                
                info(f"[PRODUCER] Кадр {frame_idx + 1} завершён, статус: {result.get('status')}")
                
                if result.get("status") == "failed":
                    error(f"[PRODUCER] Кадр {frame_idx + 1} провалился")
                    raise Exception(f"Кадр {frame_idx + 1} провалился")

            info(f"[PRODUCER] Все {num_frames} кадров сгенерированы успешно")
            _producer_tasks[task_id]["status"] = "completed"
            _producer_tasks[task_id]["progress"] = 100
            _producer_tasks[task_id]["current_step"] = "Готово!"
            _producer_tasks[task_id]["result"] = f"completed_{num_frames}_frames"
        except Exception as e:
            from utils.logger import error
            error(f"[PRODUCER] Ошибка в цикле генерации: {str(e)}")
            import traceback
            error(f"[PRODUCER] Traceback: {traceback.format_exc()}")
            _producer_tasks[task_id]["status"] = "failed"
            _producer_tasks[task_id]["error"] = str(e)[:500]
            _producer_tasks[task_id]["current_step"] = f"Ошибка: {str(e)[:200]}"
        finally:
            _running_pipelines.discard(scene_id)

    asyncio.create_task(_run_with_cleanup())

    return {
        "ok": True,
        "task_id": task_id,
        "scene_id": scene_id,
        "num_frames": num_frames,
        "message": f"Конвейер запущен: Сезон {season}, Эпизод {episode}, Сцена {scene}, {num_frames} кадров"
    }


@router.get("/task/{task_id}")
async def get_producer_task_status(task_id: str):
    """Получить статус задачи продюсера."""
    task = _producer_tasks.get(task_id)
    if not task:
        raise HTTPException(404, f"Задача '{task_id}' не найдена")
    return task


@router.post("/upload-script")
async def upload_script(file: UploadFile = File(...), db: AsyncSession = Depends(get_session)):
    """Продюсер загружает сценарий. Оркестратор принимает, извлекает текст и запускает Writer."""
    try:
        if not file.filename or not file.filename.endswith(('.pdf', '.txt', '.md')):
            raise HTTPException(400, "Поддерживаются только .pdf, .txt, .md файлы")
        
        # Защита от дублирования: проверяем не загружался ли такой же файл за последние 10 сек
        from sqlalchemy import select, func
        from database import AgentAttachment
        recent = await db.execute(
            select(AgentAttachment).where(
                AgentAttachment.agent_id == "orchestrator",
                AgentAttachment.original_name == file.filename,
                AgentAttachment.uploaded_at >= (datetime.now().isoformat()[:19])
            ).order_by(AgentAttachment.uploaded_at.desc()).limit(1)
        )
        if recent.scalars().first():
            print(f"⚠️ Дубликат: {file.filename} уже загружен, пропускаю")
            return {"ok": True, "filename": file.filename, "message": "Файл уже загружен", "duplicate": True}
        
        from pypdf import PdfReader
        
        PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        UPLOAD_DIR = os.path.join(PROJECT_ROOT, "memory", "scripts")
        ATTACHMENTS_DIR = os.path.join(PROJECT_ROOT, "memory", "attachments")
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
        
        safe_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, safe_name)
        
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Также копируем в attachments для агентов
        attach_path = os.path.join(ATTACHMENTS_DIR, safe_name)
        with open(attach_path, "wb") as f:
            f.write(content)
            
        print(f"✅ Файл сохранен: {file_path} ({len(content)} bytes)")
        
        # Извлекаем текст из файла
        ext = os.path.splitext(file.filename)[1].lower()
        extracted_text = ""
        try:
            if ext == ".pdf":
                reader = PdfReader(file_path)
                texts = []
                for page in reader.pages[:50]:
                    text = page.extract_text() or ""
                    texts.append(text)
                extracted_text = "\n\n".join(texts)[:20000]
            elif ext in (".txt", ".md"):
                with open(file_path, "r", encoding="utf-8") as f:
                    extracted_text = f.read()[:20000]
        except Exception as e:
            print(f"⚠️ Ошибка извлечения текста: {e}")
            extracted_text = f"[Ошибка извлечения текста: {str(e)}]"
        
        # Прикрепляем файл к Orchestrator в БД
        await crud.add_attachment(db, "orchestrator", {
            "filename": safe_name,
            "original_name": file.filename,
            "content_type": file.content_type or "application/octet-stream",
            "size_bytes": len(content),
            "extension": ext,
            "uploaded_at": datetime.now().isoformat(),
            "is_text_readable": len(extracted_text) > 0,
            "unreadable_reason": "" if extracted_text else "Не удалось извлечь текст",
        })
        
        # Обновляем статус Orchestrator
        await crud.update_agent(db, "orchestrator", {"status": "working"})
        
        # Отправляем текст Writer'у для анализа
        if extracted_text:
            await crud.add_message(db, "writer", "user", 
                f"[НОВЫЙ СЦЕНАРИЙ ЗАГРУЖЕН]\n\nФайл: {file.filename}\n\n{extracted_text}\n\n[КОНЕЦ СЦЕНАРИЯ]\n\nПроанализируй этот сценарий и разбей его на сцены. Для каждой сцены опиши: локацию, время суток, персонажей, ключевые действия.",
                datetime.now().isoformat())
            await crud.update_agent(db, "writer", {"status": "working"})
        
        print(f"✅ Текст извлечён: {len(extracted_text)} символов")
        print(f"✅ Файл прикреплён к Orchestrator")
        print(f"✅ Сценарий отправлен Writer'у для анализа")
        
        return {
            "ok": True, 
            "filename": safe_name, 
            "message": f"Сценарий загружен и отправлен Writer'у для анализа",
            "extracted_chars": len(extracted_text),
            "pages_analyzed": len(extracted_text) // 2000 if ext == ".pdf" else 1
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка загрузки сценария: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Ошибка загрузки файла: {str(e)}")


# Глобальный набор запущенных конвейеров (защита от двойного запуска)
_running_pipelines: set = set()


@router.post("/scene-pipeline")
async def scene_pipeline(req: ScenePipelineRequest):
    """Запустить полный конвейер сцены."""
    from orchestrator.executor import run_scene_pipeline
    scene_id = f"{req.season}_{req.episode}_{req.scene}"
    task_id = f"scene_{scene_id}"

    # Защита от двойного запуска
    if scene_id in _running_pipelines:
        raise HTTPException(409, f"Конвейер для сцены {scene_id} уже запущен")

    _running_pipelines.add(scene_id)

    # Запускаем конвейер в фоне (без БД — executor создаст свою сессию)
    pdf_context = req.pdf_context or req.description or ""

    async def _run_with_cleanup():
        try:
            await run_scene_pipeline(req.season, req.episode, req.scene, pdf_context, None)
        finally:
            _running_pipelines.discard(scene_id)

    asyncio.create_task(_run_with_cleanup())

    return {"ok": True, "task_id": task_id, "message": "Конвейер сцены запущен"}


@router.post("/full-casting")
async def full_casting(req: dict):
    """Извлечь всех персонажей из всего сценария."""
    from orchestrator.executor import run_full_casting
    
    pdf_file = req.get("pdf_file", "")
    if not pdf_file:
        raise HTTPException(400, "Не указан файл PDF")
    
    # Проверим, существует ли файл
    import os
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    file_path = os.path.join(PROJECT_ROOT, "memory", "scripts", pdf_file)
    
    if not os.path.exists(file_path):
        raise HTTPException(404, f"Файл не найден: {pdf_file}")
    
    # Прочитаем содержимое PDF
    from pypdf import PdfReader
    try:
        reader = PdfReader(file_path)
        texts = []
        for page in reader.pages[:50]:  # Максимум 50 страниц
            text = page.extract_text() or ""
            texts.append(text)
        full_text = "\n\n".join(texts)
    except Exception as e:
        raise HTTPException(500, f"Ошибка чтения PDF: {str(e)}")
    
    # Запустим полный кастинг
    try:
        # Создаем временную сессию БД для сохранения персонажей
        from database import async_session
        async with async_session() as db:
            result = await run_full_casting(full_text, db)
            return {"ok": True, "characters": result}
    except Exception as e:
        raise HTTPException(500, f"Ошибка выполнения полного кастинга: {str(e)}")


@router.get("/storyboard/frames")
async def get_storyboard_frames(db: AsyncSession = Depends(get_session)):
    """Получить ВСЕ кадры storyboard для текущего проекта."""
    frames = await crud.get_all_scene_frames(db)
    return {"frames": [{
        "id": f.id, "season_num": f.season_num, "episode_num": f.episode_num,
        "scene_num": f.scene_num, "frame_num": f.frame_num,
        "status": f.status, "final_prompt": f.final_prompt or "",
        "image_url": f.image_url or "", "writer_text": f.writer_text or "",
        "critic_feedback": f.critic_feedback or "",
        "cv_score": f.cv_score or 0,
        "cv_description": f.cv_description or "",
        "cv_details": f.cv_details or "",
        "consistency_score": f.consistency_score or 0,
        "consistency_issues": f.consistency_issues or "",
    } for f in frames]}


@router.get("/scene-result/{season}/{episode}/{scene}")
async def get_scene_result(season: int, episode: int, scene: int, db: AsyncSession = Depends(get_session)):
    """Получить результат конвейера сцены."""
    frames = await crud.get_scene_frames(db, season, episode, scene)
    if frames:
        frame = frames[0]
        return {
            "status": frame.status,
            "final_prompt": frame.final_prompt or "",
            "image_url": frame.image_url or "",
            "writer_text": frame.writer_text or "",
            "director_notes": frame.director_notes or "",
            "characters_json": frame.characters_json or "",
            "dop_prompt": frame.dop_prompt or "",
            "art_prompt": frame.art_prompt or "",
            "sound_prompt": frame.sound_prompt or "",
            "critic_feedback": frame.critic_feedback or "",
            "user_status": frame.user_status or "pending",
            "user_comment": frame.user_comment or "",
        }
    return {"status": "not_found"}


@router.post("/scene-action/{season}/{episode}/{scene}")
async def scene_action(season: int, episode: int, scene: int, action: dict, db: AsyncSession = Depends(get_session)):
    """Утвердить сцену или отправить на доработку."""
    frames = await crud.get_scene_frames(db, season, episode, scene)
    if frames:
        frame = frames[0]
        action_type = action.get("action")
        comment = action.get("comment", "")
        
        if action_type == "approve":
            frame.user_status = "approved"
            frame.user_comment = comment
        elif action_type == "revise":
            frame.user_status = "revision"
            frame.user_comment = comment
        
        await db.commit()
        return {"ok": True, "status": frame.user_status}
    return {"ok": False, "error": "Scene not found"}


@router.post("/revise-frame/{frame_id}")
async def revise_frame(frame_id: int, action: dict, db: AsyncSession = Depends(get_session)):
    """
    Доработка кадра: пользователь пишет что изменить → Art Director переписывает промпт → Kie.ai генерирует.
    action: {"comment": "что изменить", "edited_prompt": "отредактированный промпт (опционально)"}
    """
    import crud
    frames = await crud.get_all_scene_frames(db)
    frame = next((f for f in frames if f.id == frame_id), None)
    if not frame:
        return {"ok": False, "error": "Кадр не найден"}

    user_comment = action.get("comment", "")
    edited_prompt = action.get("edited_prompt", "")

    # Если пользователь сам отредактировал промпт — используем его
    if edited_prompt.strip():
        new_prompt = edited_prompt.strip()
    else:
        # Иначе просим Art Director переписать промпт с учётом комментария
        from med_otdel.agent_memory import call_llm
        current_prompt = frame.final_prompt or ""
        system = "Ты арт-директор 2.5D аниме-студии. Перепиши промпт для Kie.ai Z-Image с учётом правок."
        user = f"""Оригинальный промпт:
{current_prompt[:2000]}

Правка от пользователя: {user_comment}

Перепиши промпт чтобы учесть правку. Сохрани стиль 2.5D аниме, кинематографичность.
Верни ТОЛЬКО новый промпт, без пояснений."""

        try:
            new_prompt, _ = await call_llm(system_prompt=system, user_prompt=user)
            new_prompt = new_prompt.strip()[:800]
        except Exception as e:
            new_prompt = current_prompt  # fallback

    # Генерация через Kie.ai
    from tools.kieai_tool import generate_image
    result = await generate_image(prompt=new_prompt[:4000], width=1024, height=576)

    if result.status != "success":
        return {"ok": False, "error": f"Kie.ai ошибка: {result.error}"}

    # Обновляем кадр
    frame.final_prompt = new_prompt[:8000]
    frame.image_url = result.result_url
    frame.user_status = "in_review"
    frame.user_comment = user_comment
    frame.status = "approved"

    await db.commit()

    return {
        "ok": True,
        "image_url": result.result_url,
        "new_prompt": new_prompt[:500],
        "message": "Кадр перегенерирован"
    }


@router.patch("/scene-frame/{season}/{episode}/{scene}")
async def patch_scene_frame(season: int, episode: int, scene: int, updates: dict, db: AsyncSession = Depends(get_session)):
    """Обновить поля кадра сцены (location, prompt, image_url и т.д.)."""
    frames = await crud.get_scene_frames(db, season, episode, scene)
    if not frames:
        return {"ok": False, "error": "Scene not found"}
    
    frame = frames[0]
    allowed_fields = {
        "writer_text", "director_notes", "characters_json",
        "dop_prompt", "art_prompt", "sound_prompt",
        "final_prompt", "image_url", "critic_feedback",
        "status", "user_status", "user_comment",
    }
    
    for field, value in updates.items():
        if field in allowed_fields and hasattr(frame, field):
            setattr(frame, field, value)
    
    await db.commit()
    return {"ok": True, "message": f"Frame {season}x{episode}:{scene} updated"}


async def _is_cancelled(db, task_id):
    task = await crud.get_orchestrator_task(db, task_id)
    return task and (task.cancelled or task.status == "cancelled")


@router.post("/panda-pipeline")
async def panda_pipeline(req: dict):
    """
    Специальный endpoint для теста 'Панда Самурай'.
    1. Writer пишет сценарий с нуля из идеи
    2. Critic проверяет → Fixer правит
    3. HR кастинг → Critic сверяет
    4. DOP + Art + Sound пишут промпты
    5. Storyboarder собирает 4 кадра
    6. Kie.ai генерирует изображения
    """
    from orchestrator.executor import run_scene_pipeline, run_step_with_critic, _post_discussion
    from database import async_session
    import json

    idea = req.get("idea", "")
    if not idea:
        raise HTTPException(400, "Нет идеи")

    task_id = "panda_samurai_test"

    async def _run_full_pipeline():
        # Шаг 1: Writer пишет сценарий с нуля
        await _post_discussion("[PANDA] Шаг 1: Writer пишет сценарий...", "system", "orchestrator")

        writer_prompt = f"""Напиши сценарий аниме-короткометражки на основе идеи:

{idea}

ТРЕБОВАНИЯ:
- Длительность: 80 секунд
- Стиль: 2.5D аниме реализм
- Жанр: Философия + Триллер
- Формат: 16:9
- 4-5 сцен с таймингом
- Каждая сцена: локация, время, описание действия, диалог (если есть), атмосфера

Формат:
[СЦЕНА 1] [ЛОКАЦИЯ] [ВРЕМЯ] [ТАЙМИНГ: X сек]
[Описание действия]
[Диалог если есть]
[Атмосфера]
"""

        writer_result, _ = await run_step_with_critic("writer", writer_prompt, {}, task_id)

        if writer_result["status"] == "failed":
            await _post_discussion(f"[PANDA] Writer провалился: {writer_result.get('result', '')}", "system", "orchestrator")
            return

        script_text = writer_result.get("result", "")
        await _post_discussion(f"[PANDA] Сценарий написан ({len(script_text)} символов)", "system", "orchestrator")

        # Шаг 2: HR кастинг — извлекаем персонажей из написанного сценария
        await _post_discussion("[PANDA] Шаг 2: HR кастинг персонажей...", "system", "orchestrator")

        async with async_session() as db:
            from orchestrator.executor import run_casting
            casting_result = await run_casting(script_text, task_id, db)

        if casting_result["status"] == "failed":
            await _post_discussion("[PANDA] Кастинг провалился", "system", "orchestrator")
            return

        await _post_discussion(f"[PANDA] Кастинг завершён: {casting_result.get('saved_count', 0)} персонажей", "system", "orchestrator")

        # Шаг 3: Запускаем production pipeline для сцены 1
        await _post_discussion("[PANDA] Шаг 3: Запуск production pipeline...", "system", "orchestrator")

        async with async_session() as db:
            from orchestrator.executor import run_scene_pipeline
            pipeline_result = await run_scene_pipeline(1, 1, 1, script_text[:6000], db)

        await _post_discussion(f"[PANDA] Pipeline завершён: {pipeline_result.get('status', 'unknown')}", "system", "orchestrator")

        # Шаг 4-6: Генерируем ещё 3 кадра (сцены 2-4)
        for scene_num in range(2, 5):
            await _post_discussion(f"[PANDA] Генерация кадра {scene_num}...", "system", "orchestrator")
            async with async_session() as db:
                pipeline_result = await run_scene_pipeline(1, 1, scene_num, script_text[:6000], db)

        await _post_discussion("[PANDA] Все 4 кадра сгенерированы!", "system", "orchestrator")

    asyncio.create_task(_run_full_pipeline())

    return {"ok": True, "message": "Панда-конвейер запущен"}
