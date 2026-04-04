"""
Orchestrator API — управление цепочками задач.
Префикс роутов задаётся в main.py: /api/orchestrator
"""
import asyncio
import json
import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from models import SubmitTaskRequest, InterveneRequest

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

    system = "Ты Orchestrator аниме-студии РОДИНА. Определи какие агенты нужны для задачи."
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


@router.post("/scene-pipeline")
async def scene_pipeline(req: ScenePipelineRequest, db: AsyncSession = Depends(get_session)):
    """Запустить полный конвейер сцены."""
    from orchestrator.executor import run_scene_pipeline
    task_id = f"scene_{req.season}_{req.episode}_{req.scene}"

    # Создаём запись в БД
    await crud.create_scene_frame(db, {
        "season_num": req.season,
        "episode_num": req.episode,
        "scene_num": req.scene,
        "frame_num": 1,
        "status": "draft",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    })

    # Запускаем конвейер в фоне
    pdf_context = req.pdf_context or req.description or ""
    asyncio.create_task(run_scene_pipeline(
        req.season, req.episode, req.scene, pdf_context, db
    ))

    return {"ok": True, "task_id": task_id, "message": "Конвейер сцены запущен"}


async def _is_cancelled(db, task_id):
    task = await crud.get_orchestrator_task(db, task_id)
    return task and (task.cancelled or task.status == "cancelled")
