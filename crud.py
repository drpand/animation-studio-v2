"""
CRUD Operations — Абстракция базы данных для API.
"""
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any

from database import (
    Project, Season, Episode, Scene, SceneVersion,
    Agent, AgentAttachment, AgentRule, Message,
    Event, Discussion, MedLog,
    Character, MoodBoard, Decision,
    OrchestratorTask, OrchestratorStep, Passport, InitState, SceneFrame
)

# ============================================
# Agents
# ============================================

async def get_all_agents(db: AsyncSession) -> List[Agent]:
    result = await db.execute(select(Agent))
    return result.scalars().all()

async def get_agent(db: AsyncSession, agent_id: str) -> Optional[Agent]:
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    return result.scalars().first()

async def update_agent(db: AsyncSession, agent_id: str, data: Dict[str, Any]) -> Optional[Agent]:
    agent = await get_agent(db, agent_id)
    if agent:
        for key, value in data.items():
            if hasattr(agent, key) and value is not None:
                setattr(agent, key, value)
        await db.commit()
        await db.refresh(agent)
    return agent

async def add_attachment(db: AsyncSession, agent_id: str, data: Dict[str, Any]):
    attachment = AgentAttachment(agent_id=agent_id, **data)
    db.add(attachment)
    await db.commit()

async def remove_attachment(db: AsyncSession, agent_id: str, filename: str):
    await db.execute(
        delete(AgentAttachment).where(
            AgentAttachment.agent_id == agent_id,
            AgentAttachment.filename == filename
        )
    )
    await db.commit()

async def add_message(db: AsyncSession, agent_id: str, role: str, content: str, time: str):
    msg = Message(agent_id=agent_id, role=role, content=content, time=time)
    db.add(msg)
    await db.commit()

async def get_messages(db: AsyncSession, agent_id: str) -> List[Message]:
    result = await db.execute(
        select(Message).where(Message.agent_id == agent_id).order_by(Message.time)
    )
    return result.scalars().all()

async def get_attachments(db: AsyncSession, agent_id: str) -> List[AgentAttachment]:
    result = await db.execute(
        select(AgentAttachment).where(AgentAttachment.agent_id == agent_id)
    )
    return result.scalars().all()

async def get_rules(db: AsyncSession, agent_id: str) -> List[AgentRule]:
    result = await db.execute(
        select(AgentRule).where(AgentRule.agent_id == agent_id)
    )
    return result.scalars().all()

async def add_rule(db: AsyncSession, agent_id: str, pattern_key: str):
    rule = AgentRule(agent_id=agent_id, pattern_key=pattern_key)
    db.add(rule)
    await db.commit()

async def remove_rule(db: AsyncSession, agent_id: str, pattern_key: str):
    await db.execute(
        delete(AgentRule).where(
            AgentRule.agent_id == agent_id,
            AgentRule.pattern_key == pattern_key
        )
    )
    await db.commit()

# ============================================
# Projects & Episodes
# ============================================

async def get_active_project(db: AsyncSession) -> Optional[Project]:
    result = await db.execute(select(Project).where(Project.is_active == True))
    return result.scalars().first()

async def create_project(db: AsyncSession, data: Dict[str, Any]) -> Project:
    """Создать новый проект и сделать его активным."""
    # Деактивируем текущий активный проект
    await db.execute(update(Project).where(Project.is_active == True).values(is_active=False))
    project = Project(**data, is_active=True)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project

async def list_projects(db: AsyncSession) -> List[Project]:
    """Список всех проектов."""
    result = await db.execute(select(Project).order_by(Project.id.desc()))
    return result.scalars().all()

async def reset_project_content(db: AsyncSession):
    """Очистить весь контент проекта: кадры, персонажи, обсуждения, задачи."""
    from database import SceneFrame, Character, Message, OrchestratorTask, OrchestratorStep, Event, Discussion
    await db.execute(delete(OrchestratorStep))
    await db.execute(delete(OrchestratorTask))
    await db.execute(delete(SceneFrame))
    await db.execute(delete(Character))
    await db.execute(delete(Message))
    await db.execute(delete(Event))
    await db.execute(delete(Discussion))
    await db.commit()

async def update_project(db: AsyncSession, project_id: int, data: Dict[str, Any]) -> Optional[Project]:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().first()
    if project:
        for key, value in data.items():
            if hasattr(project, key) and value is not None:
                setattr(project, key, value)
        await db.commit()
        await db.refresh(project)
    return project

async def get_seasons(db: AsyncSession, project_id: int) -> List[Season]:
    result = await db.execute(
        select(Season).where(Season.project_id == project_id).order_by(Season.season_number)
    )
    return result.scalars().all()

async def get_episodes(db: AsyncSession, season_id: int) -> List[Episode]:
    result = await db.execute(
        select(Episode).where(Episode.season_id == season_id).order_by(Episode.episode_number)
    )
    return result.scalars().all()

async def get_episode(db: AsyncSession, season_id: int, ep_num: int) -> Optional[Episode]:
    result = await db.execute(
        select(Episode).where(Episode.season_id == season_id, Episode.episode_number == ep_num)
    )
    return result.scalars().first()

async def create_episode(db: AsyncSession, season_id: int, data: Dict[str, Any]) -> Episode:
    episode = Episode(season_id=season_id, **data)
    db.add(episode)
    await db.commit()
    await db.refresh(episode)
    return episode

async def update_episode(db: AsyncSession, episode_id: int, data: Dict[str, Any]) -> Optional[Episode]:
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    ep = result.scalars().first()
    if ep:
        for key, value in data.items():
            if hasattr(ep, key) and value is not None:
                setattr(ep, key, value)
        await db.commit()
        await db.refresh(ep)
    return ep

async def get_scenes(db: AsyncSession, episode_id: int) -> List[Scene]:
    result = await db.execute(
        select(Scene).where(Scene.episode_id == episode_id).order_by(Scene.scene_number)
    )
    return result.scalars().all()

async def create_scene(db: AsyncSession, episode_id: int, data: Dict[str, Any]) -> Scene:
    scene = Scene(episode_id=episode_id, **data)
    db.add(scene)
    await db.commit()
    await db.refresh(scene)
    return scene

async def update_scene(db: AsyncSession, scene_id: int, data: Dict[str, Any]) -> Optional[Scene]:
    result = await db.execute(select(Scene).where(Scene.id == scene_id))
    sc = result.scalars().first()
    if sc:
        for key, value in data.items():
            if hasattr(sc, key) and value is not None:
                setattr(sc, key, value)
        await db.commit()
        await db.refresh(sc)
    return sc

async def create_scene_version(db: AsyncSession, scene_id: int, data: Dict[str, Any]) -> SceneVersion:
    version = SceneVersion(scene_id=scene_id, **data)
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version

async def get_scene_versions(db: AsyncSession, scene_id: int) -> List[SceneVersion]:
    result = await db.execute(
        select(SceneVersion).where(SceneVersion.scene_id == scene_id).order_by(SceneVersion.version_number)
    )
    return result.scalars().all()

# ============================================
# Characters, Mood, Decisions
# ============================================

async def get_characters(db: AsyncSession, project_id: int) -> List[Character]:
    result = await db.execute(select(Character).where(Character.project_id == project_id))
    return result.scalars().all()

async def create_character(db: AsyncSession, project_id: int, data: Dict[str, Any]) -> Character:
    char = Character(project_id=project_id, **data)
    db.add(char)
    await db.commit()
    await db.refresh(char)
    return char

async def delete_character(db: AsyncSession, char_id: int):
    await db.execute(delete(Character).where(Character.id == char_id))
    await db.commit()

async def get_mood_board(db: AsyncSession, project_id: int) -> List[MoodBoard]:
    result = await db.execute(select(MoodBoard).where(MoodBoard.project_id == project_id))
    return result.scalars().all()

async def add_mood_item(db: AsyncSession, project_id: int, data: Dict[str, Any]) -> MoodBoard:
    item = MoodBoard(project_id=project_id, **data)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item

async def delete_mood_item(db: AsyncSession, item_id: int):
    await db.execute(delete(MoodBoard).where(MoodBoard.id == item_id))
    await db.commit()

async def get_decisions(db: AsyncSession, project_id: int) -> List[Decision]:
    result = await db.execute(select(Decision).where(Decision.project_id == project_id))
    return result.scalars().all()

async def create_decision(db: AsyncSession, project_id: int, data: Dict[str, Any]) -> Decision:
    dec = Decision(project_id=project_id, **data)
    db.add(dec)
    await db.commit()
    await db.refresh(dec)
    return dec

# ============================================
# Discussion & Logs
# ============================================

async def add_discussion(db: AsyncSession, data: Dict[str, Any]) -> Discussion:
    disc = Discussion(**data)
    db.add(disc)
    await db.commit()
    await db.refresh(disc)
    return disc

async def get_discussions(db: AsyncSession, limit: int = 100) -> List[Discussion]:
    result = await db.execute(
        select(Discussion).order_by(Discussion.timestamp.desc()).limit(limit)
    )
    return result.scalars().all()

async def add_med_log(db: AsyncSession, data: Dict[str, Any]) -> MedLog:
    log = MedLog(**data)
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log

async def get_med_logs(db: AsyncSession, limit: int = 100) -> List[MedLog]:
    result = await db.execute(
        select(MedLog).order_by(MedLog.timestamp.desc()).limit(limit)
    )
    return result.scalars().all()

async def add_event(db: AsyncSession, data: Dict[str, Any]) -> Event:
    event = Event(**data)
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event

async def get_events(db: AsyncSession, limit: int = 100) -> List[Event]:
    result = await db.execute(
        select(Event).order_by(Event.timestamp.desc()).limit(limit)
    )
    return result.scalars().all()

# ============================================
# Orchestrator
# ============================================

async def create_orchestrator_task(db: AsyncSession, data: Dict[str, Any]) -> OrchestratorTask:
    task = OrchestratorTask(**data)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task

async def get_orchestrator_task(db: AsyncSession, task_id: str) -> Optional[OrchestratorTask]:
    result = await db.execute(
        select(OrchestratorTask).where(OrchestratorTask.task_id == task_id)
    )
    return result.scalars().first()

async def update_orchestrator_task(db: AsyncSession, task_id: str, data: Dict[str, Any]) -> Optional[OrchestratorTask]:
    task = await get_orchestrator_task(db, task_id)
    if task:
        for key, value in data.items():
            if hasattr(task, key) and value is not None:
                setattr(task, key, value)
        await db.commit()
        await db.refresh(task)
    return task

async def get_active_orchestrator_tasks(db: AsyncSession) -> List[OrchestratorTask]:
    result = await db.execute(
        select(OrchestratorTask).where(OrchestratorTask.status.in_(["pending", "running"]))
    )
    return result.scalars().all()

async def add_orchestrator_step(db: AsyncSession, task_id: str, data: Dict[str, Any]) -> OrchestratorStep:
    step = OrchestratorStep(task_id=task_id, **data)
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step

async def get_orchestrator_steps(db: AsyncSession, task_id: str) -> List[OrchestratorStep]:
    result = await db.execute(
        select(OrchestratorStep).where(OrchestratorStep.task_id == task_id).order_by(OrchestratorStep.id)
    )
    return result.scalars().all()

async def update_orchestrator_step(db: AsyncSession, step_id: int, data: Dict[str, Any]) -> Optional[OrchestratorStep]:
    result = await db.execute(select(OrchestratorStep).where(OrchestratorStep.id == step_id))
    step = result.scalars().first()
    if step:
        for key, value in data.items():
            if hasattr(step, key) and value is not None:
                setattr(step, key, value)
        await db.commit()
        await db.refresh(step)
    return step

async def get_orchestrator_tasks(db: AsyncSession) -> List[OrchestratorTask]:
    result = await db.execute(select(OrchestratorTask).order_by(OrchestratorTask.created_at.desc()))
    return result.scalars().all()

# ============================================
# Analytics
# ============================================

async def get_production_analytics(db: AsyncSession) -> Dict[str, Any]:
    total_episodes = await db.scalar(select(func.count(Episode.id)))
    total_scenes = await db.scalar(select(func.count(Scene.id)))
    total_characters = await db.scalar(select(func.count(Character.id)))
    total_mood = await db.scalar(select(func.count(MoodBoard.id)))
    total_decisions = await db.scalar(select(func.count(Decision.id)))
    total_seasons = await db.scalar(select(func.count(Season.id)))
    
    # Count by status
    result = await db.execute(
        select(Episode.status, func.count(Episode.id)).group_by(Episode.status)
    )
    by_status = dict(result.all())

    return {
        "total_episodes": total_episodes or 0,
        "total_scenes": total_scenes or 0,
        "total_characters": total_characters or 0,
        "total_mood_items": total_mood or 0,
        "total_decisions": total_decisions or 0,
        "seasons": total_seasons or 0,
        "by_status": by_status
    }

# ============================================
# Passports & Init
# ============================================

async def get_passports(db: AsyncSession) -> List[Passport]:
    result = await db.execute(select(Passport))
    return result.scalars().all()

async def create_passport(db: AsyncSession, data: Dict[str, Any]) -> Passport:
    p = Passport(**data)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p

async def get_init_state(db: AsyncSession) -> Optional[InitState]:
    result = await db.execute(select(InitState).limit(1))
    return result.scalars().first()

async def update_init_state(db: AsyncSession, data: Dict[str, Any]):
    state = await get_init_state(db)
    if state:
        for key, value in data.items():
            if hasattr(state, key) and value is not None:
                setattr(state, key, value)
        await db.commit()
    else:
        new_state = InitState(**data)
        db.add(new_state)
        await db.commit()


# ============================================
# Scene Frames (Production Pipeline)
# ============================================

async def create_scene_frame(db: AsyncSession, data: Dict[str, Any]) -> SceneFrame:
    frame = SceneFrame(**data)
    db.add(frame)
    await db.commit()
    await db.refresh(frame)
    return frame

async def get_scene_frames(db: AsyncSession, season: int, episode: int, scene: int) -> List[SceneFrame]:
    result = await db.execute(
        select(SceneFrame).where(
            SceneFrame.season_num == season,
            SceneFrame.episode_num == episode,
            SceneFrame.scene_num == scene
        ).order_by(SceneFrame.frame_num)
    )
    return result.scalars().all()

async def get_all_scene_frames(db: AsyncSession) -> List[SceneFrame]:
    """Получить ВСЕ кадры storyboard."""
    result = await db.execute(
        select(SceneFrame).order_by(SceneFrame.season_num, SceneFrame.episode_num, SceneFrame.scene_num, SceneFrame.frame_num)
    )
    return result.scalars().all()

async def update_scene_frame(db: AsyncSession, frame_id: int, data: Dict[str, Any]) -> Optional[SceneFrame]:
    result = await db.execute(select(SceneFrame).where(SceneFrame.id == frame_id))
    frame = result.scalars().first()
    if frame:
        for key, value in data.items():
            if hasattr(frame, key) and value is not None:
                setattr(frame, key, value)
        from datetime import datetime
        frame.updated_at = datetime.now().isoformat()
        await db.commit()
        await db.refresh(frame)
    return frame


# ============================================
# Access Level Helpers
# ============================================

ACCESS_LEVEL_1 = "level_1"       # meta_critic — найм
ACCESS_LEVEL_2 = "level_2"       # critic, fixer — производство
ACCESS_LEVEL_3 = "level_3"       # med_otdel — наблюдение
ACCESS_LEVEL_PRODUCTION = "production"  # writer, director, dop, art, sound, storyboarder, hr

async def get_agents_by_level(db: AsyncSession, level: str) -> List[Agent]:
    """Получить агентов по уровню доступа."""
    result = await db.execute(select(Agent).where(Agent.access_level == level))
    return result.scalars().all()

async def get_production_agents(db: AsyncSession) -> List[Agent]:
    """Получить только production агентов."""
    result = await db.execute(select(Agent).where(Agent.access_level == ACCESS_LEVEL_PRODUCTION))
    return result.scalars().all()

async def get_critic_fixer_agents(db: AsyncSession) -> List[Agent]:
    """Получить агентов уровня 2 (critic/fixer)."""
    result = await db.execute(select(Agent).where(Agent.access_level == ACCESS_LEVEL_2))
    return result.scalars().all()

async def get_agent_access_level(db: AsyncSession, agent_id: str) -> Optional[str]:
    """Получить уровень доступа агента."""
    agent = await get_agent(db, agent_id)
    return agent.access_level if agent else None

async def get_agents_by_status(db: AsyncSession, status: str) -> List[Agent]:
    """Получить агентов по статусу."""
    result = await db.execute(select(Agent).where(Agent.status == status))
    return result.scalars().all()
