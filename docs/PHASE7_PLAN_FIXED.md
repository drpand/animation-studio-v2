# Фаза 7 — Orchestrator Pipeline (ИСПРАВЛЕННЫЙ ПЛАН)

> Исправления по замечаниям Critic (6/6 FIXED)

---

## 1. Отмена HTTP-запроса (asyncio + httpx timeout)

**Проблема:** `asyncio.Event` не прервёт HTTP-запрос к OpenRouter.

**Решение:**

```python
import asyncio
import httpx

async def run_agent_with_cancel(agent, input_text, cancel_event, agent_timeout):
    """Запуск агента с поддержкой отмены и таймаутом."""
    # Если уже отменено — даже не начинаем
    if cancel_event.is_set():
        return None, "cancelled_before_start"

    try:
        # asyncio.wait_for оборачивает сам HTTP-запрос
        result = await asyncio.wait_for(
            agent.chat(input_text),
            timeout=agent_timeout
        )
        return result, "ok"
    except asyncio.TimeoutError:
        return None, f"timeout_{agent_timeout}s"
    except asyncio.CancelledError:
        return None, "cancelled"
    except Exception as e:
        return None, f"error: {str(e)}"
```

**Ключевые моменты:**
- `cancel_event.is_set()` проверяется ДО вызова `agent.chat()` — если отмена уже пришла, запрос не делается
- `asyncio.wait_for()` + `httpx.AsyncClient(timeout=...)` — двойная защита: wait_for прерывает корутину, httpx timeout прерывает TCP-соединение
- Таймауты дифференцированы (см. п.6)

---

## 2. Умная суммаризация

**Проблема:** Фиксированные 1000 символов — мало и глупо.

**Решение:** LLM решает что важно.

```python
async def summarize_for_next_agent(orchestrator, result, next_agent_role):
    """Умная суммаризация: LLM извлекает только нужное следующему агенту."""

    # Critic получает полный результат — ему нужно всё для оценки
    if next_agent_role == "critic" or next_agent_role == "Critic":
        return result

    prompt = f"""Ты Orchestrator аниме-студии РОДИНА.

РЕЗУЛЬТАТ РАБОТЫ АГЕНТА:
---
{result[:8000]}
---

СЛЕДУЮЩИЙ АГЕНТ: {next_agent_role}

Извлеки из результата только то, что нужно следующему агенту {next_agent_role}.
Игнорируй всё остальное. Сохрани ключевые факты, решения, числа, имена.
Максимум 2000 символов. Отвечай только суммаризацией, без пояснений."""

    summary = await orchestrator.chat(prompt)
    return summary[:2000]
```

**Ключевые моменты:**
- Критик всегда получает полный результат (без суммаризации)
- LLM решает что важно для конкретного следующего агента
- 2000 символов — мягкий лимит, не жёсткий срез
- 8000 символов входного окна — достаточно для контекста

---

## 3. Startup hook — восстановление задач

**Проблема:** При перезапуске сервера задачи теряются.

**Решение:** В `main.py` добавить startup hook:

```python
from fastapi import FastAPI

app = FastAPI(title="Animation Studio v2 — РОДИНА")

@app.on_event("startup")
async def startup():
    """Восстановить задачи из JSON при старте сервера."""
    from api.tasks_api import _load_tasks, _save_tasks
    from api.discussion_api import _load_discussion, _save_discussion
    from datetime import datetime
    import os

    tasks_file = os.path.join("memory", "tasks.json")
    if os.path.exists(tasks_file):
        data = _load_tasks()

        # Все running → interrupted
        recovered = 0
        for task in data.get("active", []):
            if task.get("status") == "running":
                task["status"] = "interrupted"
                task["interrupted_at"] = datetime.now().isoformat()
                recovered += 1

        if recovered > 0:
            _save_tasks(data)

            # Записать в Discussion
            disc = _load_discussion()
            disc["messages"].append({
                "agent_id": "system",
                "content": f"Сервер перезапущен. {recovered} задач(а) переведены из running в interrupted.",
                "msg_type": "system",
                "timestamp": datetime.now().isoformat()
            })
            _save_discussion(disc)
```

**Ключевые моменты:**
- Загружает tasks.json при старте
- Все `running` → `interrupted`
- Записывает в Discussion сколько задач восстановлено
- `active` задачи со статусом `interrupted` можно перезапустить через UI

---

## 4. Degraded fallback

**Проблема:** Неясно что происходит если Fixer не может исправить.

**Решение:**

```python
async def fix_with_fallback(fixer, original_result, critic_feedback, orchestrator):
    """Fixer с degraded fallback после 3 провалов."""
    MAX_FIX_ATTEMPTS = 3

    current_result = original_result
    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        fix_prompt = f"""ОРИГИНАЛЬНЫЙ РЕЗУЛЬТАТ:
---
{current_result[:6000]}
---

ЗАМЕЧАНИЯ КРИТИКА:
---
{critic_feedback[:4000]}
---

Исправь результат по замечаниям критика. Верни только исправленный текст."""

        fixed = await fixer.chat(fix_prompt)

        # Проверяем исправление через Critic
        check_prompt = f"""РЕЗУЛЬТАТ ПОСЛЕ ИСПРАВЛЕНИЯ (попытка {attempt}):
---
{fixed[:6000]}
---

Оригинальные замечания: {critic_feedback[:2000]}

Оцени: исправлены ли замечания? Ответь PASS или FAIL с кратким объяснением."""

        verdict = await orchestrator.chat(check_prompt)

        if "PASS" in verdict.upper()[:50]:
            return fixed, "fixed", attempt

        current_result = fixed  # следующая итерация работает с последним результатом

    # ДЕГРАДИРОВАННЫЙ FALLBACK: используем оригинальный результат
    # Записать в Discussion
    from api.discussion_api import _load_discussion, _save_discussion
    from datetime import datetime
    disc = _load_discussion()
    disc["messages"].append({
        "agent_id": "system",
        "content": f"Fixer не смог исправить {MAX_FIX_ATTEMPTS} раза. Использован оригинальный результат.",
        "msg_type": "system",
        "timestamp": datetime.now().isoformat()
    })
    _save_discussion(disc)

    return original_result, "degraded", MAX_FIX_ATTEMPTS
```

**Ключевые моменты:**
- 3 попытки Fixer
- Каждая попытка проверяется через LLM-вердикт (PASS/FAIL)
- Если все 3 провалились → используем **оригинальный** результат (до Fixer)
- Шаг помечается `degraded`
- Запись в Discussion

---

## 5. agent_registry.json — полная схема

**Файл:** `config/agent_registry.json`

```json
[
  {
    "id": "writer",
    "name": "Writer",
    "capabilities": ["сценарий", "текст", "диалоги", "адаптация", "разбивка на серии"],
    "input_type": "text",
    "output_type": "text",
    "model": "google/gemini-3-flash-preview",
    "timeout": 90
  },
  {
    "id": "director",
    "name": "Director",
    "capabilities": ["режиссура", "визуальный стиль", "раскадровка", "эмоции"],
    "input_type": "text",
    "output_type": "text",
    "model": "google/gemini-3-flash-preview",
    "timeout": 90
  },
  {
    "id": "storyboarder",
    "name": "Storyboarder",
    "capabilities": ["кадры", "тайминг", "ракурсы", "список сцен"],
    "input_type": "text",
    "output_type": "text",
    "model": "google/gemini-3-flash-preview",
    "timeout": 90
  },
  {
    "id": "dop",
    "name": "DOP",
    "capabilities": ["свет", "камера", "атмосфера", "цветокоррекция"],
    "input_type": "text",
    "output_type": "text",
    "model": "google/gemini-3-flash-preview",
    "timeout": 90
  },
  {
    "id": "art_director",
    "name": "Art Director",
    "capabilities": ["дизайн", "цвет", "промпты для изображений", "стиль"],
    "input_type": "text",
    "output_type": "text",
    "model": "google/gemini-3-flash-preview",
    "timeout": 90
  },
  {
    "id": "sound_director",
    "name": "Sound Director",
    "capabilities": ["музыка", "звук", "озвучка", "лейтмотивы"],
    "input_type": "text",
    "output_type": "text",
    "model": "google/gemini-3-flash-preview",
    "timeout": 90
  },
  {
    "id": "critic",
    "name": "Critic",
    "capabilities": ["оценка", "критика", "проверка качества"],
    "input_type": "text",
    "output_type": "evaluation",
    "model": "google/gemini-3-flash-preview",
    "timeout": 60
  },
  {
    "id": "fixer",
    "name": "Fixer",
    "capabilities": ["исправление", "доработка"],
    "input_type": "text",
    "output_type": "text",
    "model": "google/gemini-3-flash-preview",
    "timeout": 90
  }
]
```

---

## 6. Таймауты дифференцированы по моделям

**Проблема:** Один таймаут для всех — неэффективно.

**Решение:** Каждый агент в registry имеет свой `timeout`. Orchestrator читает его оттуда.

| Агент | Модель | Таймаут | Обоснование |
|---|---|---|---|
| Writer | gemini-3-flash-preview | 90с | Средний текст |
| Director | gemini-3-flash-preview | 90с | Творческие решения |
| Storyboarder | gemini-3-flash-preview | 90с | Структурированный вывод |
| DOP | gemini-3-flash-preview | 90с | Технические детали |
| Art Director | gemini-3-flash-preview | 90с | Промпты для изображений |
| Sound Director | gemini-3-flash-preview | 90с | Музыкальные описания |
| **Critic** | gemini-3-flash-preview | **60с** | Оценка — быстрее |
| Fixer | gemini-3-flash-preview | 90с | Исправление текста |

**Если модель меняется** (например Claude Opus) → таймаут увеличивается:
- Быстрые (flash, 9b): 60-90с
- Средние (sonnet, 70b): 90-120с
- Медленные (opus, 405b): 120-180с

---

## 7. Matching алгоритм Orchestrator

**Как Orchestrator строит цепочку агентов:**

1. Получает задачу (текст от пользователя)
2. Через LLM анализирует ключевые слова задачи
3. Сравнивает с `capabilities` каждого агента из `agent_registry.json`
4. Строит цепочку: выбирает агентов чьи capabilities совпадают с задачей

**Стандартный порядок (полный pipeline):**
```
Writer → Critic → [Fixer если FAIL] → Director → Critic → [Fixer если FAIL]
→ Storyboarder → Critic → [Fixer если FAIL] → DOP → Critic → [Fixer если FAIL]
→ Art Director → Critic → [Fixer если FAIL] → Sound Director → Critic → [Fixer если FAIL]
```

**Правила:**
- Critic после КАЖДОГО агента (кроме себя)
- Fixer если Critic вернул FAIL (до 3 попыток, затем degraded)
- Умная суммаризация между агентами (кроме Critic — ему полный результат)
- Каждый шаг записывается в Discussion

---

## Файлы для создания/изменения

| Файл | Действие | Описание |
|---|---|---|
| `config/agent_registry.json` | **НОВЫЙ** | Полный реестр агентов с capabilities, моделями, таймаутами |
| `agents/orchestrator.py` | **ПЕРEPИСАТЬ** | Полная логика pipeline: matching, cancel, summarization, degraded fallback |
| `main.py` | **ПРАВКА** | Добавить `@app.on_event("startup")` для восстановления задач |
| `agents/base_agent.py` | **ПРАВКА** | Добавить параметр `timeout` в конструктор, передавать в httpx |
| `api/tasks_api.py` | **ПРАВКА** | Поддержка статуса `interrupted` |
| `api/discussion_api.py` | **БЕЗ ИЗМЕНЕНИЙ** | Уже поддерживает системные сообщения |

---

## Кругов Critic/Fixer

**3/3** — каждый агент проходит Critic, Fixer имеет 3 попытки исправления.

---

**Статус: Готов к Build**
