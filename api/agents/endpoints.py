"""Agent CRUD and management endpoints."""
import os
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from models import AgentOut, AgentUpdate
from agents.base_agent import _load_instructions, _save_instructions
from api.agents.helpers import (
    ATTACHMENTS_DIR,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    guess_content_type,
    resolve_attachment_flags,
    update_active_project,
)

router = APIRouter()


@router.get("/")
async def list_agents(db: AsyncSession = Depends(get_session)):
    """List all agents with their instructions."""
    agents = await crud.get_all_agents(db)
    instructions = _load_instructions()
    result = []
    for agent in agents:
        attachments = await crud.get_attachments(db, agent.agent_id)
        instr = instructions.get(agent.agent_id, agent.instructions)
        result.append(AgentOut(
            agent_id=agent.agent_id,
            name=agent.name,
            role=agent.role,
            model=agent.model,
            status=agent.status,
            instructions=instr,
            access_level=getattr(agent, 'access_level', 'production'),
        ))
    return {"agents": result}


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_session)):
    """Get agent details with attachments and chat history."""
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")
    attachments = await crud.get_attachments(db, agent_id)
    rules = await crud.get_rules(db, agent_id)
    messages = await crud.get_messages(db, agent_id)
    instructions = _load_instructions()
    instr = instructions.get(agent_id, agent.instructions)
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "role": agent.role,
        "model": agent.model,
        "status": agent.status,
        "access_level": getattr(agent, 'access_level', 'production'),
        "instructions": instr,
        "attachment_objects": [
            {
                "filename": a.filename, "original_name": a.original_name,
                "content_type": a.content_type, "size_bytes": a.size_bytes,
                "extension": a.extension, "uploaded_at": a.uploaded_at,
                "is_text_readable": a.is_text_readable, "unreadable_reason": a.unreadable_reason,
            }
            for a in attachments
        ],
        "attachments": [a.filename for a in attachments],
        "applied_rules": [r.pattern_key for r in rules],
        "chat_history": [
            {"role": m.role, "content": m.content, "time": m.time}
            for m in messages
        ],
    }


@router.put("/{agent_id}")
async def update_agent(agent_id: str, update: AgentUpdate, db: AsyncSession = Depends(get_session)):
    """Update agent instructions and model."""
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")
    
    # Update instructions in JSON file (not in DB)
    if update.instructions is not None:
        instructions = _load_instructions()
        instructions[agent_id] = update.instructions
        _save_instructions(instructions)
    
    # Update model in DB
    if update.model is not None:
        await crud.update_agent(db, agent_id, {"model": update.model})
    
    return {"ok": True, "agent_id": agent_id}


@router.post("/{agent_id}/upload")
async def upload_file(agent_id: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_session)):
    """Upload file attachment for agent."""
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Недопустимый тип файла '{ext}'. Разрешены: {', '.join(ALLOWED_EXTENSIONS)}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"Файл слишком большой (макс. {MAX_FILE_SIZE // 1024 // 1024} MB)")

    os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
    safe_name = f"{agent_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    save_path = os.path.join(ATTACHMENTS_DIR, safe_name)
    with open(save_path, "wb") as f:
        f.write(content)

    uploaded_at = datetime.now().isoformat()
    is_text_readable, unreadable_reason = resolve_attachment_flags(file.filename, file.content_type or "", content)

    attachment_data = {
        "filename": safe_name, "original_name": file.filename,
        "content_type": file.content_type or guess_content_type(ext),
        "size_bytes": len(content), "extension": ext,
        "uploaded_at": uploaded_at, "is_text_readable": is_text_readable,
        "unreadable_reason": unreadable_reason,
    }
    await crud.add_attachment(db, agent_id, attachment_data)

    if agent_id == "orchestrator":
        update_active_project(file.filename, safe_name)

    return {
        "ok": True, "filename": safe_name, "uploaded_at": uploaded_at,
        "is_text_readable": is_text_readable, "unreadable_reason": unreadable_reason,
        "attachment": attachment_data,
    }


@router.delete("/{agent_id}/attachments/{filename}")
async def delete_attachment(agent_id: str, filename: str, db: AsyncSession = Depends(get_session)):
    """Delete file attachment for agent."""
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")
    await crud.remove_attachment(db, agent_id, filename)
    path = os.path.join(ATTACHMENTS_DIR, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    return {"ok": True, "filename": filename}
