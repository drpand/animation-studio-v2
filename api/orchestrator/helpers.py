"""Shared helpers for orchestrator API endpoints."""
import asyncio
import json
import os
import re
import uuid
from datetime import datetime

from config import PROJECT_NAME, OPENROUTER_API_KEY
import crud

# Global state
_producer_tasks: dict = {}
_running_pipelines: set = set()
_running_pipelines_lock = asyncio.Lock()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY_FILE = os.path.join(PROJECT_ROOT, "orchestrator", "agent_registry.json")


def extract_edit_hints(user_comment: str) -> dict:
    """Extract JSON edit hints from user_comment."""
    if not user_comment:
        return {}
    try:
        obj = json.loads(user_comment)
        if isinstance(obj, dict) and obj.get("type") == "frame_edit_hints":
            hints = obj.get("hints", {})
            return hints if isinstance(hints, dict) else {}
    except Exception:
        pass
    return {}


def extract_prompt_parts(prompt_parts_json: str) -> dict:
    """Safely parse prompt_parts_json into a dict."""
    if not prompt_parts_json:
        return {}
    try:
        obj = json.loads(prompt_parts_json)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


async def build_task_chain(description: str):
    """Build a task chain via LLM."""
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


async def execute_chain(task_id: str, db):
    """Execute a task chain."""
    from med_otdel.med_core import run_evaluation as run_critic
    import httpx

    task = await crud.get_orchestrator_task(db, task_id)
    if not task:
        return

    await crud.update_orchestrator_task(db, task_id, {"status": "running"})

    steps = await crud.get_orchestrator_steps(db, task_id)
    previous_output = task.description or ""

    for i, step in enumerate(steps):
        if await is_cancelled(db, task_id):
            return

        await crud.update_orchestrator_step(db, step.id, {"status": "running", "input": previous_output[:2000]})

        agent = await crud.get_agent(db, step.agent_id)
        if not agent:
            await crud.update_orchestrator_step(db, step.id, {"status": "failed", "error": "Agent not found"})
            continue

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


async def is_cancelled(db, task_id):
    """Check if a task has been cancelled."""
    task = await crud.get_orchestrator_task(db, task_id)
    return task and (task.cancelled or task.status == "cancelled")
