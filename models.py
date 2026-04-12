"""
Models — Pydantic схемы для валидации ответов LLM и API.
"""
from pydantic import BaseModel, Field
from typing import Optional, List


# ============================================
# Agent Schemas
# ============================================

class AgentOut(BaseModel):
    agent_id: str
    name: str
    role: str
    model: str
    status: str
    instructions: str = ""
    access_level: Optional[str] = "production"

    class Config:
        from_attributes = True


class AgentUpdate(BaseModel):
    model: Optional[str] = None
    instructions: Optional[str] = None
    status: Optional[str] = None


# ============================================
# Chat Schemas
# ============================================

class ChatMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


class ChatResponse(BaseModel):
    reply: str
    agent_id: str
    status: str


# ============================================
# Project Schemas
# ============================================

class ProjectOut(BaseModel):
    name: str
    description: str = ""
    file: str = ""
    file_path: str = ""
    current_season: int = 1
    current_episode: int = 1
    total_episodes: int = 15


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    current_season: Optional[int] = None
    current_episode: Optional[int] = None
    total_episodes: Optional[int] = None


# ============================================
# Episode/Scene Schemas
# ============================================

class EpisodeCreate(BaseModel):
    season: int = 1
    title: str = ""
    description: str = ""


class EpisodeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class SceneCreate(BaseModel):
    season: int = 1
    episode: int = 1
    scene_number: int = 1
    title: str = ""
    description: str = ""
    duration_seconds: int = 0
    status: str = "draft"


class SceneUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    duration_seconds: Optional[int] = None
    status: Optional[str] = None


class SceneVersionCreate(BaseModel):
    season: int
    episode: int
    scene: int
    content: str
    comment: str = ""


# ============================================
# Character/Mood/Decision Schemas
# ============================================

class CharacterCreate(BaseModel):
    name: str
    description: str = ""
    voice_id: str = ""
    relations: str = ""


class MoodItemCreate(BaseModel):
    url: str = ""
    description: str = ""
    tags: str = ""


class DecisionCreate(BaseModel):
    title: str
    description: str = ""
    agent_id: str = ""


# ============================================
# Orchestrator Schemas
# ============================================

class SubmitTaskRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=2000)


class InterveneRequest(BaseModel):
    action: str  # cancel, pause, resume


# ============================================
# MED-OTDEL Schemas
# ============================================

class EvaluateRequest(BaseModel):
    agent_id: str
    task_description: str = ""


class FixRequest(BaseModel):
    agent_id: str
    original_result: str
    critic_feedback: str


class PatternRequest(BaseModel):
    agent_id: str
    pattern_key: str


# ============================================
# HR Schemas
# ============================================

class CreateAgentRequest(BaseModel):
    task_description: str
    agent_name: str = ""
    agent_role: str = ""


# ============================================
# LLM Validation Schemas
# ============================================

class LLMResponse(BaseModel):
    """Базовая схема для валидации ответов LLM."""
    content: str
    error: Optional[str] = None


class CriticEvaluation(BaseModel):
    """Схема для валидации оценки Critic."""
    score: int = Field(..., ge=0, le=10)
    passed: bool
    feedback: str


class TaskChainResult(BaseModel):
    """Схема для валидации результата Orchestrator."""
    task_id: str
    status: str
    result: str = ""
    steps_completed: int = 0
    steps_total: int = 0
