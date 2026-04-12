"""
Orchestrator API — управление цепочками задач.
Префикс роутов задаётся в main.py: /api/orchestrator

This file is now a thin wrapper that imports from the modularized api/orchestrator/ package
for backward compatibility.
"""
from api.orchestrator import router  # noqa: F401
from api.orchestrator.helpers import (  # noqa: F401
    _producer_tasks,
    _running_pipelines,
    _running_pipelines_lock,
    extract_edit_hints,
    extract_prompt_parts,
    build_task_chain,
    execute_chain,
    is_cancelled,
    PROJECT_ROOT,
    REGISTRY_FILE,
)
from api.orchestrator.producer import ScenePipelineRequest  # noqa: F401
