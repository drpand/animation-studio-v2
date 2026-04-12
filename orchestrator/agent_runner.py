"""
Agent Runner — запуск агентов через OpenRouter API с таймаутами.
Вынесено из orchestrator/executor.py для улучшения поддерживаемости.
"""
import asyncio
import json
import os

from config import OPENROUTER_API_KEY
from orchestrator.progress_tracker import tracker
from orchestrator.executor_helpers import _post_discussion, _load_full_project_context

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_FILE = os.path.join(PROJECT_ROOT, "orchestrator", "agent_registry.json")


def _load_registry() -> list:
    if os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _get_agent_timeout(agent_id: str) -> int:
    registry = _load_registry()
    for agent in registry:
        if agent.get("id") == agent_id:
            return agent.get("timeout", 90)
    return 90


def _get_agent_model(agent_id: str) -> str:
    registry = _load_registry()
    for agent in registry:
        if agent.get("id") == agent_id:
            return agent.get("model", "deepseek/deepseek-v3.2")
    return "deepseek/deepseek-v3.2"


async def _run_agent_step(agent_id: str, input_text: str, task_id: str) -> tuple[str, bool]:
    """
    Запустить агента с таймаутом и проверкой отмены.
    Возвращает (output, success).
    """
    if tracker.is_cancelled(task_id):
        return "", False

    model = _get_agent_model(agent_id)
    timeout = _get_agent_timeout(agent_id)

    await _post_discussion(
        f"[{agent_id.upper()}] Начало работы. Модель: {model}",
        "agent",
        agent_id
    )

    try:
        # Импортируем BaseAgent здесь чтобы избежать циклических импортов
        from agents.base_agent import BaseAgent, _load_constitution

        constitution = _load_constitution()
        project_context = _load_full_project_context()
        
        system_prompt = ""
        if constitution:
            system_prompt += f"[КОНСТИТУЦИЯ СТУДИИ]\n{constitution}\n\n"
        
        if project_context:
            system_prompt += f"[КОНТЕКСТ ПРОЕКТА]\n{project_context}\n\n"
        
        system_prompt += f"[РОЛЬ]\nТы {agent_id} анимационной студии. Работай по правилам Конституции и строго следуй контексту активного проекта (визуальный стиль, цветовая палитра, музыкальный референс).\n\n[ЗАДАЧА]\n{input_text}"

        async def _call_openrouter():
            import httpx
            async with httpx.AsyncClient(timeout=timeout + 30) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:7860",
                        "X-Title": "Animation Studio v2"
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": input_text[:8000]}
                        ]
                    }
                )
                data = resp.json()
                if resp.status_code >= 400:
                    error_obj = data.get("error", {}) if isinstance(data, dict) else {}
                    error_msg = error_obj.get("message") or data.get("message") or resp.text
                    raise Exception(f"OpenRouter {resp.status_code}: {error_msg}")
                if not isinstance(data, dict) or "choices" not in data or not data.get("choices"):
                    raise Exception(f"OpenRouter: неожиданный формат ответа")
                return data["choices"][0]["message"]["content"]

        result = await asyncio.wait_for(_call_openrouter(), timeout=timeout)

        if tracker.is_cancelled(task_id):
            return "", False

        await _post_discussion(
            f"[{agent_id.upper()}] Завершил работу. Результат: {len(result)} символов",
            "agent",
            agent_id
        )
        return result, True

    except asyncio.TimeoutError:
        await _post_discussion(
            f"[{agent_id.upper()}] Таймаут ({timeout} сек)",
            "system",
            agent_id
        )
        return f"[ТАЙМАУТ] Агент {agent_id} не ответил за {timeout} сек", False
    except Exception as e:
        await _post_discussion(
            f"[{agent_id.upper()}] Ошибка: {str(e)[:200]}",
            "system",
            agent_id
        )
        return f"[ОШИБКА] {str(e)[:500]}", False


async def _summarize_for_next_agent(text: str, next_agent_role: str, task_id: str) -> str:
    """Суммаризировать результат для следующего агента."""
    if not text or len(text) < 500:
        return text

    system = "Ты эксперт по суммаризации. Извлеки только то, что нужно следующему специалисту."
    user = f"""Извлеки из этого результата только то, что нужно агенту "{next_agent_role}" для работы.
Игнорируй всё остальное. Максимум 2000 символов.

Результат:
{text[:4000]}

Верни только суммаризированный текст."""

    try:
        from med_otdel.agent_memory import call_llm
        result, _ = await asyncio.wait_for(
            call_llm(system_prompt=system, user_prompt=user),
            timeout=120
        )
        return result.strip()[:2000]
    except Exception:
        return text[:2000]
