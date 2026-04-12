"""Med Otdel evaluation and fixing endpoints."""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from models import EvaluateRequest, FixRequest
from api.med_otdel.helpers import get_last_agent_result

router = APIRouter()


@router.post("/evaluate")
async def evaluate(req: EvaluateRequest, db: AsyncSession = Depends(get_session)):
    """Critic evaluates last agent response."""
    agent = await crud.get_agent(db, req.agent_id)
    if not agent:
        raise HTTPException(404, f"Агент '{req.agent_id}' не найден")

    last_result = await get_last_agent_result(db, req.agent_id)
    if not last_result:
        raise HTTPException(400, "Нет результатов для оценки.")

    from med_otdel.med_core import run_evaluation
    try:
        result = await run_evaluation(
            task_result=last_result, agent_id=req.agent_id, task_description=req.task_description
        )
    except Exception as e:
        import logging
        logging.error(f"Evaluation error: {e}")
        result = {
            "passed": False,
            "score": 0,
            "feedback": f"Ошибка оценки: {str(e)[:500]}",
            "task_id": "",
            "raw_response": "",
            "fixed_result": None,
        }

    # If Fixer fixed result — save to agent history
    if result.get("fixed_result"):
        try:
            import crud as crud_mod
            await crud_mod.add_message(db, req.agent_id, "assistant",
                f"[ИСПРАВЛЕНО FIXER'ом]\n\n{result['fixed_result'][:4000]}",
                datetime.now().isoformat())
        except Exception:
            pass

    return result


@router.post("/fix")
async def fix(req: FixRequest, db: AsyncSession = Depends(get_session)):
    """Fixer fixes result."""
    from med_otdel.med_core import run_fix
    fixed_result = await run_fix(req.original_result, req.critic_feedback)
    return {"fixed_result": fixed_result}
