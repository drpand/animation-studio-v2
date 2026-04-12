"""Producer task and pipeline endpoints."""
import asyncio
import json
import os
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session, async_session, AgentAttachment
import crud
from models import SubmitTaskRequest
from config import PROJECT_NAME
from api.orchestrator.helpers import (
    _producer_tasks,
    _running_pipelines,
    _running_pipelines_lock,
    PROJECT_ROOT,
)
from utils.logger import info, error

router = APIRouter()


class ScenePipelineRequest(BaseModel):
    season: int = 1
    episode: int = 1
    scene: int = 1
    pdf_context: str = ""
    description: str = ""


@router.post("/task")
async def create_task(req: dict):
    """Продюсер ставит задачу. Оркестратор запускает полный конвейер."""
    from orchestrator.executor import run_scene_pipeline
    from med_otdel.med_core import write_event, log_med_action

    task_desc = req.get("description", "")
    if not task_desc:
        raise HTTPException(400, "Описание задачи не может быть пустым")

    # Определяем season/episode/scene из описания или используем дефолт
    season = int(req.get("season", 1))
    episode = int(req.get("episode", 1))
    scene = int(req.get("scene", 1))

    # Парсим номер сцены из текста если пользователь указал
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
    
    info(f"[PRODUCER] Парсинг: найдено {num_frames} кадров из описания: {task_desc[:100]}")

    task_id = f"producer_{uuid.uuid4().hex[:8]}"
    scene_id = f"{season}_{episode}_{scene}"

    # Защита от двойного запуска (atomic check-and-add with lock)
    async with _running_pipelines_lock:
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
            
            info(f"[PRODUCER] Запуск цикла генерации {num_frames} кадров")

            # Генерируем N кадров (каждый кадр = отдельная сцена)
            for frame_idx in range(num_frames):
                current_scene = scene + frame_idx
                frame_progress_base = int((frame_idx / num_frames) * 90)
                frame_task_id = f"{task_id}_frame_{frame_idx + 1}"
                
                info(f"[PRODUCER] Генерация кадра {frame_idx + 1}/{num_frames}, сцена {current_scene}")
                
                await _progress(f"Кадр {frame_idx + 1}/{num_frames}: Кастинг...", frame_progress_base + 5)

                async def _frame_progress(step: str, prog: int):
                    await _progress(
                        f"Кадр {frame_idx + 1}/{num_frames}: {step}",
                        frame_progress_base + int(prog * 0.9)
                    )
                
                async with async_session() as db:
                    result = await run_scene_pipeline(
                        season, episode, current_scene, 
                        f"{task_desc}\n\nКадр {frame_idx + 1} из {num_frames}",
                        db, 
                        progress_callback=_frame_progress
                    )
                
                info(f"[PRODUCER] Кадр {frame_idx + 1} завершён, статус: {result.get('status')}")
                try:
                    write_event(
                        agent_id="orchestrator",
                        event_type="frame_pipeline",
                        result=f"frame={frame_idx + 1}/{num_frames}; scene={current_scene}; status={result.get('status')}",
                        status="success" if result.get("status") == "completed" else "fail",
                        task_id=frame_task_id,
                    )
                except Exception:
                    pass
                
                if result.get("status") == "failed":
                    failure_reason = ""
                    try:
                        # Пытаемся извлечь первопричину из шагов конвейера
                        steps = result.get("steps", {}) if isinstance(result, dict) else {}
                        if isinstance(steps, dict):
                            for step_name, step_data in steps.items():
                                if isinstance(step_data, dict) and step_data.get("status") == "failed":
                                    failure_reason = str(step_data.get("result") or step_data.get("error") or "")
                                    if failure_reason:
                                        failure_reason = f"step={step_name}: {failure_reason[:300]}"
                                        break
                        if not failure_reason and isinstance(result, dict):
                            failure_reason = str(result.get("error") or result.get("result") or "")[:300]
                    except Exception:
                        failure_reason = ""

                    error(f"[PRODUCER] Кадр {frame_idx + 1} провалился. reason={failure_reason}")
                    try:
                        log_med_action("frame_failed", f"{task_id} frame={frame_idx + 1}/{num_frames} reason={failure_reason[:200]}", "orchestrator")
                    except Exception:
                        pass
                    if failure_reason:
                        raise Exception(f"Кадр {frame_idx + 1} провалился ({failure_reason})")
                    raise Exception(f"Кадр {frame_idx + 1} провалился")

            info(f"[PRODUCER] Все {num_frames} кадров сгенерированы успешно")
            _producer_tasks[task_id]["status"] = "completed"
            _producer_tasks[task_id]["progress"] = 100
            _producer_tasks[task_id]["current_step"] = "Готово!"
            _producer_tasks[task_id]["result"] = f"completed_{num_frames}_frames"
        except Exception as e:
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
        async with async_session() as db:
            result = await run_full_casting(full_text, db)
            return {"ok": True, "characters": result}
    except Exception as e:
        raise HTTPException(500, f"Ошибка выполнения полного кастинга: {str(e)}")


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
    from med_otdel.med_core import write_event, log_med_action

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
