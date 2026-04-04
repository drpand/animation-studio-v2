"""
Orchestrator Task Chain — модели данных для цепочек задач.
"""
import uuid
from datetime import datetime
from typing import Optional


class AgentStep:
    """Один шаг в цепочке."""

    def __init__(self, agent_id: str, input_text: str = ""):
        self.agent_id = agent_id
        self.input = input_text
        self.output = ""
        self.status = "pending"  # pending, running, completed, failed, degraded, cancelled
        self.critic_passed = False
        self.critic_feedback = ""
        self.fix_attempts = 0
        self.error = ""
        self.started_at = ""
        self.completed_at = ""

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "input": self.input[:2000],
            "output": self.output[:5000],
            "status": self.status,
            "critic_passed": self.critic_passed,
            "critic_feedback": self.critic_feedback[:500],
            "fix_attempts": self.fix_attempts,
            "error": self.error[:500],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentStep":
        step = cls(data.get("agent_id", ""), data.get("input", ""))
        step.output = data.get("output", "")
        step.status = data.get("status", "pending")
        step.critic_passed = data.get("critic_passed", False)
        step.critic_feedback = data.get("critic_feedback", "")
        step.fix_attempts = data.get("fix_attempts", 0)
        step.error = data.get("error", "")
        step.started_at = data.get("started_at", "")
        step.completed_at = data.get("completed_at", "")
        return step


class TaskChain:
    """Полная цепочка задачи."""

    def __init__(self, description: str):
        self.task_id = f"task_{uuid.uuid4().hex[:8]}"
        self.description = description
        self.steps: list[AgentStep] = []
        self.status = "pending"  # pending, running, completed, failed, interrupted, cancelled
        self.current_step = 0
        self.result = ""
        self.created_at = datetime.now().isoformat()
        self.completed_at = ""
        self.cancelled = False

    def add_step(self, agent_id: str, input_text: str = "") -> AgentStep:
        step = AgentStep(agent_id, input_text)
        self.steps.append(step)
        return step

    def get_current_step(self) -> Optional[AgentStep]:
        if 0 <= self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def progress(self) -> float:
        if not self.steps:
            return 0.0
        return (self.current_step / len(self.steps)) * 100

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "current_step": self.current_step,
            "result": self.result[:5000],
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "cancelled": self.cancelled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskChain":
        chain = cls(data.get("description", ""))
        chain.task_id = data.get("task_id", chain.task_id)
        chain.steps = [AgentStep.from_dict(s) for s in data.get("steps", [])]
        chain.status = data.get("status", "pending")
        chain.current_step = data.get("current_step", 0)
        chain.result = data.get("result", "")
        chain.created_at = data.get("created_at", "")
        chain.completed_at = data.get("completed_at", "")
        chain.cancelled = data.get("cancelled", False)
        return chain
