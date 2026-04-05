"""
Database — SQLite через SQLAlchemy (Async).
Все таблицы, CRUD методы, инициализация.
"""
import os
from datetime import datetime
from sqlalchemy import event, Column, Integer, String, Text, Boolean, REAL, DateTime, ForeignKey, Index, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config import DATABASE_URL

# Resolve absolute path for SQLite
if "sqlite" in DATABASE_URL:
    import re
    match = re.search(r"sqlite\+aiosqlite:///(.+)", DATABASE_URL)
    if match:
        db_path = match.group(1)
        if not os.path.isabs(db_path):
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_path)
        DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"

Base = declarative_base()

# ============================================
# SQLAlchemy Models
# ============================================

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    file = Column(String(255), default="")
    file_path = Column(String(500), default="")
    current_season = Column(Integer, default=1)
    current_episode = Column(Integer, default=1)
    total_episodes = Column(Integer, default=15)
    updated_at = Column(String(30), default="")
    is_active = Column(Boolean, default=False)

    seasons = relationship("Season", back_populates="project", cascade="all, delete-orphan")
    characters = relationship("Character", back_populates="project", cascade="all, delete-orphan")
    mood_board = relationship("MoodBoard", back_populates="project", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="project", cascade="all, delete-orphan")


class Season(Base):
    __tablename__ = "seasons"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    season_number = Column(Integer, nullable=False)
    title = Column(String(100), default="")
    description = Column(Text, default="")

    project = relationship("Project", back_populates="seasons")
    episodes = relationship("Episode", back_populates="season", cascade="all, delete-orphan")

    __table_args__ = (Index("idx_season_project", "project_id"),)


class Episode(Base):
    __tablename__ = "episodes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    episode_number = Column(Integer, nullable=False)
    title = Column(String(200), default="")
    description = Column(Text, default="")
    status = Column(String(30), default="draft")
    created_at = Column(String(30), default="")
    updated_at = Column(String(30), default="")

    season = relationship("Season", back_populates="episodes")
    scenes = relationship("Scene", back_populates="episode", cascade="all, delete-orphan")

    __table_args__ = (Index("idx_episode_season", "season_id"), Index("idx_episode_status", "status"))


class Scene(Base):
    __tablename__ = "scenes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    episode_id = Column(Integer, ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False)
    scene_number = Column(Integer, nullable=False)
    title = Column(String(200), default="")
    description = Column(Text, default="")
    duration_seconds = Column(Integer, default=0)
    status = Column(String(30), default="draft")
    created_at = Column(String(30), default="")
    updated_at = Column(String(30), default="")

    episode = relationship("Episode", back_populates="scenes")
    versions = relationship("SceneVersion", back_populates="scene", cascade="all, delete-orphan")

    __table_args__ = (Index("idx_scene_episode", "episode_id"),)


class SceneVersion(Base):
    __tablename__ = "scene_versions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False)
    content = Column(Text, default="")
    comment = Column(String(500), default="")
    created_at = Column(String(30), default="")

    scene = relationship("Scene", back_populates="versions")


class Agent(Base):
    __tablename__ = "agents"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    role = Column(String(200), default="")
    model = Column(String(100), default="")
    status = Column(String(20), default="idle")
    instructions = Column(Text, default="")
    access_level = Column(String(20), default="production")  # level_1, level_2, level_3, production
    created_at = Column(String(30), default="")
    updated_at = Column(String(30), default="")

    attachments = relationship("AgentAttachment", back_populates="agent", cascade="all, delete-orphan")
    rules = relationship("AgentRule", back_populates="agent", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="agent", cascade="all, delete-orphan")


class AgentAttachment(Base):
    __tablename__ = "agent_attachments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(50), ForeignKey("agents.agent_id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    original_name = Column(String(255), default="")
    content_type = Column(String(100), default="")
    size_bytes = Column(Integer, default=0)
    extension = Column(String(10), default="")
    uploaded_at = Column(String(30), default="")
    is_text_readable = Column(Boolean, default=False)
    unreadable_reason = Column(String(200), default="")

    agent = relationship("Agent", back_populates="attachments")

    __table_args__ = (Index("idx_attachment_agent", "agent_id"),)


class AgentRule(Base):
    __tablename__ = "agent_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(50), ForeignKey("agents.agent_id", ondelete="CASCADE"), nullable=False)
    pattern_key = Column(String(50), nullable=False)
    applied_at = Column(String(30), default="")

    agent = relationship("Agent", back_populates="rules")


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(50), ForeignKey("agents.agent_id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, default="")
    time = Column(String(30), default="")

    agent = relationship("Agent", back_populates="messages")

    __table_args__ = (Index("idx_message_agent", "agent_id"), Index("idx_message_time", "time"))


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(50), nullable=False, index=True)
    agent_id = Column(String(50), nullable=False, index=True)
    event_type = Column(String(50), default="")
    result = Column(Text, default="")
    status = Column(String(20), default="")
    target_agent_id = Column(String(50), default="")
    timestamp = Column(String(30), default="")

    __table_args__ = (
        Index("idx_event_task", "task_id"),
        Index("idx_event_agent", "agent_id"),
        Index("idx_event_timestamp", "timestamp"),
    )


class Discussion(Base):
    __tablename__ = "discussions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(50), default="", index=True)
    content = Column(Text, default="")
    msg_type = Column(String(20), default="system")
    timestamp = Column(String(30), default="")

    __table_args__ = (Index("idx_discussion_timestamp", "timestamp"),)


class MedLog(Base):
    __tablename__ = "med_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(100), default="")
    details = Column(Text, default="")
    agent_id = Column(String(50), default="")
    timestamp = Column(String(30), default="")


class Character(Base):
    __tablename__ = "characters"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    voice_id = Column(String(100), default="")
    relations = Column(Text, default="")
    created_at = Column(String(30), default="")

    project = relationship("Project", back_populates="characters")


class MoodBoard(Base):
    __tablename__ = "mood_board"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    url = Column(String(500), default="")
    description = Column(Text, default="")
    tags = Column(String(200), default="")
    created_at = Column(String(30), default="")

    project = relationship("Project", back_populates="mood_board")


class Decision(Base):
    __tablename__ = "decisions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    agent_id = Column(String(50), default="")
    created_at = Column(String(30), default="")

    project = relationship("Project", back_populates="decisions")


class OrchestratorTask(Base):
    __tablename__ = "orchestrator_tasks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, default="")
    status = Column(String(20), default="pending")
    current_step = Column(Integer, default=0)
    result = Column(Text, default="")
    created_at = Column(String(30), default="")
    completed_at = Column(String(30), default="")
    cancelled = Column(Boolean, default=False)

    steps = relationship("OrchestratorStep", back_populates="task", cascade="all, delete-orphan")


class OrchestratorStep(Base):
    __tablename__ = "orchestrator_steps"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(50), ForeignKey("orchestrator_tasks.task_id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(String(50), default="")
    input = Column(Text, default="")
    output = Column(Text, default="")
    status = Column(String(20), default="pending")
    critic_passed = Column(Boolean, default=False)
    critic_feedback = Column(Text, default="")
    fix_attempts = Column(Integer, default=0)
    error = Column(Text, default="")
    started_at = Column(String(30), default="")
    completed_at = Column(String(30), default="")

    task = relationship("OrchestratorTask", back_populates="steps")


class Passport(Base):
    __tablename__ = "passports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(50), nullable=False, index=True)
    name = Column(String(100), default="")
    created_by = Column(String(50), default="")
    prompt_source = Column(String(255), default="")
    approved_by = Column(String(50), default="")
    meta_critic_score = Column(REAL, default=0.0)
    version = Column(Integer, default=1)
    created_at = Column(String(30), default="")


class InitState(Base):
    __tablename__ = "init_state"
    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(20), default="not_started")
    project_description = Column(Text, default="")
    initialized_at = Column(String(30), default="")


class SceneFrame(Base):
    """Кадр сцены в производственном конвейере."""
    __tablename__ = "scene_frames"
    id = Column(Integer, primary_key=True, autoincrement=True)
    season_num = Column(Integer, nullable=False)
    episode_num = Column(Integer, nullable=False)
    scene_num = Column(Integer, nullable=False)
    frame_num = Column(Integer, nullable=False)
    status = Column(String(20), default="draft")  # draft -> in_review -> approved -> final
    writer_text = Column(Text, default="")
    director_notes = Column(Text, default="")
    characters_json = Column(Text, default="")
    dop_prompt = Column(Text, default="")
    art_prompt = Column(Text, default="")
    sound_prompt = Column(Text, default="")
    final_prompt = Column(Text, default="")
    image_url = Column(String(500), default="")
    critic_feedback = Column(Text, default="")
    user_status = Column(String(20), default="pending")  # pending, approved, revision
    user_comment = Column(Text, default="")
    cv_score = Column(Integer, default=0)  # 0-10 оценка CV проверки
    cv_description = Column(Text, default="")  # что видит CV модель
    cv_details = Column(Text, default="")  # JSON: что совпало/не совпало
    created_at = Column(String(30), default="")
    updated_at = Column(String(30), default="")

    __table_args__ = (
        Index("idx_frame_scene", "season_num", "episode_num", "scene_num"),
    )


# ============================================
# Database Engine & Session
# ============================================

# DATABASE_URL = "sqlite+aiosqlite:///./memory/studio.db"
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"timeout": 30},
)

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Создать все таблицы если их нет."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Получить сессию БД (для FastAPI Depends)."""
    async with async_session() as session:
        yield session
