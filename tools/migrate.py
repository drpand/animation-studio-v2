"""
Migration Script — JSON → SQLite.
Запуск: python tools/migrate.py
"""
import os
import sys
import json
import asyncio

# Добавляем корень проекта в path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from database import (
    init_db, async_session,
    Project, Season, Episode, Scene, SceneVersion,
    Agent, AgentAttachment, AgentRule, Message,
    Event, Discussion, MedLog,
    Character, MoodBoard, Decision,
    OrchestratorTask, OrchestratorStep, Passport, InitState
)

MEMORY_DIR = os.path.join(PROJECT_ROOT, "memory")
BACKUP_DIR = os.path.join(MEMORY_DIR, "backup")


def load_json(filename):
    path = os.path.join(MEMORY_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def backup_json(filename):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    src = os.path.join(MEMORY_DIR, filename)
    dst = os.path.join(BACKUP_DIR, filename)
    if os.path.exists(src):
        import shutil
        shutil.copy2(src, dst)
        print(f"  Backup: {filename} -> backup/{filename}")


async def migrate():
    print("=== Migration: JSON to SQLite ===")
    print()

    # 1. Инициализация БД
    print("1. Initializing database...")
    await init_db()
    print("  Database tables created.")
    print()

    # 2. Projects
    print("2. Migrating projects...")
    project_data = load_json("project_memory.json")
    async with async_session() as session:
        if project_data:
            ap = project_data.get("active_project", {})
            project = Project(
                name=ap.get("name", "Animation Studio"),
                description=ap.get("description", ""),
                file=ap.get("file", ""),
                file_path=ap.get("file_path", ""),
                current_season=ap.get("current_season", 1),
                current_episode=ap.get("current_episode", 1),
                total_episodes=ap.get("total_episodes", 15),
                updated_at=ap.get("updated_at", ""),
                is_active=True,
            )
            session.add(project)
            await session.flush()

            # Seasons
            for s_data in project_data.get("seasons", []):
                season = Season(
                    project_id=project.id,
                    season_number=s_data.get("season_number", 1),
                    title=s_data.get("title", ""),
                    description=s_data.get("description", ""),
                )
                session.add(season)
                await session.flush()

                # Episodes
                for ep_data in s_data.get("episodes", []):
                    episode = Episode(
                        season_id=season.id,
                        episode_number=ep_data.get("episode_number", 1),
                        title=ep_data.get("title", ""),
                        description=ep_data.get("description", ""),
                        status=ep_data.get("status", "draft"),
                        created_at=ep_data.get("created_at", ""),
                        updated_at=ep_data.get("updated_at", ""),
                    )
                    session.add(episode)
                    await session.flush()

                    # Scenes
                    for sc_data in ep_data.get("scenes", []):
                        scene = Scene(
                            episode_id=episode.id,
                            scene_number=sc_data.get("scene_number", 1),
                            title=sc_data.get("title", ""),
                            description=sc_data.get("description", ""),
                            duration_seconds=sc_data.get("duration_seconds", 0),
                            status=sc_data.get("status", "draft"),
                            created_at=sc_data.get("created_at", ""),
                            updated_at=sc_data.get("updated_at", ""),
                        )
                        session.add(scene)
                        await session.flush()

                        # Scene versions
                        for v_data in sc_data.get("versions", []):
                            version = SceneVersion(
                                scene_id=scene.id,
                                version_number=v_data.get("version_number", 1),
                                content=v_data.get("content", ""),
                                comment=v_data.get("comment", ""),
                                created_at=v_data.get("created_at", ""),
                            )
                            session.add(version)

            # Characters
            for c_data in project_data.get("characters", []):
                char = Character(
                    project_id=project.id,
                    name=c_data.get("name", ""),
                    description=c_data.get("description", ""),
                    voice_id=c_data.get("voice_id", ""),
                    relations=c_data.get("relations", ""),
                    created_at=c_data.get("created_at", ""),
                )
                session.add(char)

            # Mood board
            for m_data in project_data.get("mood_board", []):
                mood = MoodBoard(
                    project_id=project.id,
                    url=m_data.get("url", ""),
                    description=m_data.get("description", ""),
                    tags=m_data.get("tags", ""),
                    created_at=m_data.get("created_at", ""),
                )
                session.add(mood)

            # Decisions
            for d_data in project_data.get("decision_log", []):
                decision = Decision(
                    project_id=project.id,
                    title=d_data.get("title", ""),
                    description=d_data.get("description", ""),
                    agent_id=d_data.get("agent_id", ""),
                    created_at=d_data.get("created_at", ""),
                )
                session.add(decision)

        await session.commit()
    print("  Projects, seasons, episodes, scenes, characters, mood_board, decisions migrated.")
    print()

    # 3. Agents
    print("3. Migrating agents...")
    agents_data = load_json("agents_state.json")
    async with async_session() as session:
        if agents_data:
            for agent_id, data in agents_data.items():
                agent = Agent(
                    agent_id=agent_id,
                    name=data.get("name", agent_id),
                    role=data.get("role", ""),
                    model=data.get("model", ""),
                    status=data.get("status", "idle"),
                    instructions=data.get("instructions", ""),
                )
                session.add(agent)
                await session.flush()

                # Attachments
                for att in data.get("attachment_objects", []):
                    attachment = AgentAttachment(
                        agent_id=agent_id,
                        filename=att.get("filename", ""),
                        original_name=att.get("original_name", ""),
                        content_type=att.get("content_type", ""),
                        size_bytes=att.get("size_bytes", 0),
                        extension=att.get("extension", ""),
                        uploaded_at=att.get("uploaded_at", ""),
                        is_text_readable=att.get("is_text_readable", False),
                        unreadable_reason=att.get("unreadable_reason", ""),
                    )
                    session.add(attachment)

                # Rules
                for rule in data.get("applied_rules", []):
                    agent_rule = AgentRule(
                        agent_id=agent_id,
                        pattern_key=rule if isinstance(rule, str) else rule.get("pattern_key", ""),
                    )
                    session.add(agent_rule)

                # Messages
                for msg in data.get("chat_history", []):
                    message = Message(
                        agent_id=agent_id,
                        role=msg.get("role", "user"),
                        content=msg.get("content", ""),
                        time=msg.get("time", ""),
                    )
                    session.add(message)

        await session.commit()
    print("  Agents, attachments, rules, messages migrated.")
    print()

    # 4. Events
    print("4. Migrating events...")
    events_data = load_json("events_bus.json")
    async with async_session() as session:
        if events_data:
            for e_data in events_data.get("events", []):
                event = Event(
                    task_id=e_data.get("task_id", ""),
                    agent_id=e_data.get("agent_id", ""),
                    event_type=e_data.get("event_type", ""),
                    result=e_data.get("result", ""),
                    status=e_data.get("status", ""),
                    target_agent_id=e_data.get("target_agent_id", ""),
                    timestamp=e_data.get("timestamp", ""),
                )
                session.add(event)
        await session.commit()
    print("  Events migrated.")
    print()

    # 5. Discussions
    print("5. Migrating discussions...")
    disc_data = load_json("discussion_log.json")
    async with async_session() as session:
        if disc_data:
            for d_data in disc_data.get("messages", []):
                discussion = Discussion(
                    agent_id=d_data.get("agent_id", ""),
                    content=d_data.get("content", ""),
                    msg_type=d_data.get("msg_type", "system"),
                    timestamp=d_data.get("timestamp", ""),
                )
                session.add(discussion)
        await session.commit()
    print("  Discussions migrated.")
    print()

    # 6. Med Logs
    print("6. Migrating med logs...")
    med_data = load_json("med_log.json")
    async with async_session() as session:
        if med_data:
            for entry in med_data.get("entries", []):
                log = MedLog(
                    action=entry.get("action", ""),
                    details=entry.get("details", ""),
                    agent_id=entry.get("agent_id", ""),
                    timestamp=entry.get("timestamp", ""),
                )
                session.add(log)
        await session.commit()
    print("  Med logs migrated.")
    print()

    # 7. Orchestrator Tasks
    print("7. Migrating orchestrator tasks...")
    orch_data = load_json("orchestrator_tasks.json")
    async with async_session() as session:
        if orch_data:
            for t_data in orch_data.get("tasks", []):
                task = OrchestratorTask(
                    task_id=t_data.get("task_id", ""),
                    description=t_data.get("description", ""),
                    status=t_data.get("status", "pending"),
                    current_step=t_data.get("current_step", 0),
                    result=t_data.get("result", ""),
                    created_at=t_data.get("created_at", ""),
                    completed_at=t_data.get("completed_at", ""),
                    cancelled=t_data.get("cancelled", False),
                )
                session.add(task)
                await session.flush()

                for s_data in t_data.get("steps", []):
                    step = OrchestratorStep(
                        task_id=task.task_id,
                        agent_id=s_data.get("agent_id", ""),
                        input=s_data.get("input", ""),
                        output=s_data.get("output", ""),
                        status=s_data.get("status", "pending"),
                        critic_passed=s_data.get("critic_passed", False),
                        critic_feedback=s_data.get("critic_feedback", ""),
                        fix_attempts=s_data.get("fix_attempts", 0),
                        error=s_data.get("error", ""),
                        started_at=s_data.get("started_at", ""),
                        completed_at=s_data.get("completed_at", ""),
                    )
                    session.add(step)

        await session.commit()
    print("  Orchestrator tasks migrated.")
    print()

    # 8. Passports
    print("8. Migrating passports...")
    passports_dir = os.path.join(MEMORY_DIR, "passports")
    async with async_session() as session:
        if os.path.exists(passports_dir):
            for fname in os.listdir(passports_dir):
                if fname.endswith(".json"):
                    with open(os.path.join(passports_dir, fname), "r", encoding="utf-8") as f:
                        p_data = json.load(f)
                    passport = Passport(
                        agent_id=p_data.get("agent_id", ""),
                        name=p_data.get("name", ""),
                        created_by=p_data.get("created_by", ""),
                        prompt_source=p_data.get("prompt_source", ""),
                        approved_by=p_data.get("approved_by", ""),
                        meta_critic_score=p_data.get("meta_critic_score", 0.0),
                        version=p_data.get("version", 1),
                        created_at=p_data.get("created_at", ""),
                    )
                    session.add(passport)
        await session.commit()
    print("  Passports migrated.")
    print()

    # 9. Init State
    print("9. Migrating init state...")
    init_data = load_json("init_state.json")
    async with async_session() as session:
        if init_data:
            state = InitState(
                status=init_data.get("status", "not_started"),
                project_description=init_data.get("project_description", ""),
                initialized_at=init_data.get("initialized_at", ""),
            )
            session.add(state)
        await session.commit()
    print("  Init state migrated.")
    print()

    # 10. Backup JSON files
    print("10. Backing up JSON files...")
    for fname in [
        "project_memory.json", "agents_state.json", "events_bus.json",
        "discussion_log.json", "med_log.json", "orchestrator_tasks.json",
        "init_state.json", "tasks.json", "critic_evaluations.json"
    ]:
        backup_json(fname)
    print()

    # 11. Verification
    print("11. Verification...")
    async with async_session() as session:
        from sqlalchemy import func
        counts = {
            "projects": await session.scalar(func.count(Project.id)),
            "seasons": await session.scalar(func.count(Season.id)),
            "episodes": await session.scalar(func.count(Episode.id)),
            "scenes": await session.scalar(func.count(Scene.id)),
            "agents": await session.scalar(func.count(Agent.id)),
            "messages": await session.scalar(func.count(Message.id)),
            "events": await session.scalar(func.count(Event.id)),
            "discussions": await session.scalar(func.count(Discussion.id)),
            "med_logs": await session.scalar(func.count(MedLog.id)),
            "characters": await session.scalar(func.count(Character.id)),
            "passports": await session.scalar(func.count(Passport.id)),
        }
        for table, count in counts.items():
            print(f"  {table}: {count}")
    print()
    print("=== Migration Complete ===")


if __name__ == "__main__":
    asyncio.run(migrate())
