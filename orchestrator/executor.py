"""
Orchestrator Executor — ядро выполнения цепочки задач.
Тонкая обёртка для обратной совместимости.
Вся логика вынесена в отдельные модули:
  - cv_checker.py — CV проверка изображений
  - critic_fixer.py — Critic/Fixer циклы
  - prompt_builder.py — парсинг JSON, построение промптов, санитизация
  - agent_runner.py — запуск агентов через OpenRouter
  - pipeline_manager.py — execute_chain, run_casting, run_full_casting, run_scene_pipeline
"""

# Prompt builder exports
from orchestrator.prompt_builder import (
    _extract_json,
    _extract_json_array,
    _extract_names_to_remove,
    _safe_text,
    _safe_text_list,
    _sanitize_image_text,
    _pick_visual_phrase,
    _build_strict_image_parts,
    _compose_image_prompt,
    _build_strict_image_prompt,
    _contains_panda,
    _sanitize_subject_leakage,
    _sanitize_entity_leakage,
    _build_kieai_prompt,
)

# Executor helpers exports
from orchestrator.executor_helpers import (
    _post_discussion,
    _load_full_project_context,
)

# Agent runner exports
from orchestrator.agent_runner import (
    _run_agent_step,
    _summarize_for_next_agent,
    _load_registry,
    _get_agent_timeout,
    _get_agent_model,
)

# Critic/Fixer exports
from orchestrator.critic_fixer import (
    _run_critic,
    _run_fixer,
    run_step_with_critic,
)

# CV Checker exports
from orchestrator.cv_checker import (
    _cv_auto_check,
    _check_character_consistency,
)

# Pipeline Manager exports
from orchestrator.pipeline_manager import (
    execute_chain,
    run_casting,
    run_full_casting,
    run_scene_pipeline,
    _create_character_pattern,
    _generate_and_review,
)
