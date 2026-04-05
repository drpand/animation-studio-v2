# Animation Studio v2 — QWEN Context

## Project Overview

**Animation Studio v2 "РОДИНА"** — локальный веб-офис с AI-агентами для производства аниме-сериала. Это не Telegram-бот — полноценный веб-интерфейс в браузере на `localhost:7860`.

### Purpose
Производство аниме-сериала "РОДИНА" для YouTube:
- 15 эпизодов, сезон 1
- Формат: строго 3 минуты на серию (±10 сек)
- Стиль: 2.5D аниме, референс Satoshi Kon
- Палитра Гоа: красная пыль, синее море, фиолетовые ночи

### Architecture
```
Frontend: Чистый HTML/CSS/JS (static/)
Backend:  Python + FastAPI + Hypercorn (main.py)
Database: SQLite через SQLAlchemy Async (studio.db)
AI:       OpenRouter API (10+ агентов с разными LLM моделями)
```

### Key Features
- **10 AI-агентов** — каждый со своей ролью (Director, Writer, Critic, DOP и др.)
- **МЕД-ОТДЕЛ** — система самообучения: эволюция промптов, анализ цепочек, мониторинг студии
- **Orchestrator** — автоматическое распределение задач между агентами
- **Production Pipeline** — полный конвейер сцены с Critic/Fixer на каждом этапе
- **HR Agent** — создание временных агентов под специфические задачи
- **Multi-project support** — переключение между проектами, эпизодная структура
- **File attachments** — агенты могут работать с PDF, TXT, MD, JSON файлами

---

## Building and Running

### Quick Start
```bash
# Запуск (Windows)
run.bat
```

Или вручную:
```bash
# Создать venv (первый раз)
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Запустить сервер
python main.py
# Или напрямую через hypercorn:
python -m hypercorn main:app --bind 0.0.0.0:7860
```

Сервер доступен по адресу: `http://localhost:7860`

### Dependencies
```
fastapi>=0.115.0
hypercorn>=0.17.0
httpx>=0.27.0
python-multipart>=0.0.9
pypdf>=5.0.0
sqlalchemy[asyncio]>=2.0.0
aiosqlite>=0.20.0
```

### Environment Variables (.env)
```
OPENROUTER_API_KEY=sk-or-v1-...
COMFYUI_URL=http://localhost:8188
COMFYUI_POLL_ATTEMPTS=150
COMFYUI_POLL_INTERVAL_SEC=5
ELEVENLABS_API_KEY=...
KIEAI_API_KEY=...
RATE_LIMIT_REQUESTS_PER_MIN=10
AUTH_USERNAME=admin
AUTH_PASSWORD=rodina2026
```

---

## File Structure

```
animation-studio-v2/
├── main.py                  # FastAPI сервер, точка входа, lifespan hooks
├── run.bat                  # Запуск одной кнопкой
├── config.py                # API ключи, настройки, константы
├── database.py              # SQLAlchemy модели (20+ таблиц), async session
├── models.py                # Pydantic схемы для API валидации
├── crud.py                  # CRUD операции для БД
├── auth.py                  # HTTP Basic Auth middleware
├── constitution.md          # КОНСТИТУЦИЯ СТУДИИ — фундаментальные правила
├── requirements.txt         # Python зависимости
│
├── agents/                  # AI-агенты
│   ├── base_agent.py        # Базовый класс: OpenRouter chat, attachments, state
│   ├── orchestrator.py      # Дирижёр — анализ задачи, построение цепочки
│   ├── director.py          # Режиссёр — визуальная стратегия
│   ├── writer.py            # Сценарист — 3-act structure, YouTube формат
│   ├── critic.py            # Критик — оценка качества
│   ├── fixer.py             # Фиксер — исправление по замечаниям
│   ├── storyboarder.py      # Раскадровщик — кадры с таймингом
│   ├── dop.py               # Оператор — свет, угол, атмосфера
│   ├── art_director.py      # Арт-директор — стиль, цвет, промпты для Kie.ai
│   ├── sound_director.py    # Звук — музыка, лейтмотивы, эффекты
│   ├── hr_agent.py          # HR — создание новых агентов
│   └── instructions.json    # Системные инструкции для каждой роли
│
├── med_otdel/               # МЕД-ОТДЕЛ — самообучение
│   ├── med_core.py          # Оркестратор 3 режимов (agent_heal, chain_heal, studio_alert)
│   ├── agent_memory.py      # Память агентов, порог эволюции
│   ├── chain_analyzer.py    # Анализ цепочек агент→агент
│   ├── meta_critic.py       # Надзиратель за качеством Critic
│   ├── rule_builder.py      # Автосоздание паттернов
│   ├── studio_monitor.py    # Мониторинг здоровья студии
│   ├── patterns.json        # Паттерны для эволюции
│   └── versions/            # Версии промптов V1→V2→V3
│
├── orchestrator/            # Автоматическое управление задачами
│   ├── agent_registry.json  # Реестр 8 агентов с capabilities
│   ├── task_chain.py        # Модели TaskChain, AgentStep
│   ├── executor.py          # Ядро выполнения: agent→summarize→critic→fixer
│   └── progress_tracker.py  # Хранение задач, thread-safe
│
├── api/                     # API роуты FastAPI
│   ├── agents_api.py        # CRUD агентов
│   ├── chat_api.py          # Чат с агентом (OpenRouter)
│   ├── tasks_api.py         # Управление задачами
│   ├── med_otdel_api.py     # МЕД-ОТДЕЛ endpoints
│   ├── hr_api.py            # HR agent endpoints
│   ├── hr_init_api.py       # Инициализация агентов
│   ├── tools_api.py         # Внешние инструменты (Kie.ai, ComfyUI)
│   ├── discussion_api.py    # Discussion канал агентов
│   ├── orchestrator_api.py  # Orchestrator endpoints (5 шт)
│   ├── project_api.py       # Управление проектами
│   ├── episodes_api.py      # Эпизоды и сезоны
│   └── characters_api.py    # Персонажи
│
├── static/                  # Фронтенд
│   ├── index.html           # Главная — вид офиса
│   ├── init.html            # Страница инициализации проекта
│   ├── style.css            # Стили
│   └── app.js               # Логика интерфейса
│
├── memory/                  # Локальная память
│   ├── studio.db            # SQLite база данных
│   ├── agents_state.json    # Состояние агентов (модели, статус, история)
│   ├── project_memory.json  # Активный проект, эпизоды, персонажи
│   ├── tasks.json           # Очередь задач
│   ├── events_bus.json      # Шина событий для МЕД-ОТДЕЛА
│   ├── med_log.json         # Лог действий МЕД-ОТДЕЛА
│   ├── critic_evaluations.json  # Оценки критика
│   ├── discussion_log.json  # Лог обсуждений
│   ├── orchestrator_tasks.json  # Задачи оркестратора
│   ├── attachments/         # Прикреплённые файлы агентов
│   ├── passports/           # Паспорта агентов (кто создал,评分)
│   ├── tools_cache/         # Кэш внешних инструментов
│   └── backup/              # Бэкапы
│
├── utils/                   # Утилиты
│   └── logger.py            # Логирование (logs/app.log)
│
└── tools/                   # Внешние инструменты
    └── (kie_ai, comfyui и др.)
```

---

## Agents Registry

| Agent | Role | Default Model |
|-------|------|---------------|
| **Orchestrator** | Дирижёр — управляет цепочками задач | `qwen/qwen3.5-9b` |
| **Director** | Режиссёр — визуальная стратегия | `deepseek/deepseek-v3.2` |
| **Writer** | Сценарист — адаптация сценария | `deepseek/deepseek-v3.2` |
| **Critic** | Критик — оценка и обратная связь | `deepseek/deepseek-v3.2` |
| **Fixer** | Фиксер — исправление замечаний | `deepseek/deepseek-v3.2` |
| **Storyboarder** | Раскадровщик — кадры с таймингом | `deepseek/deepseek-v3.2` |
| **DOP** | Оператор — свет, камера, атмосфера | `deepseek/deepseek-v3.2` |
| **Art Director** | Стиль, цвет, промпты для Kie.ai | `deepseek/deepseek-v3.2` |
| **Sound Director** | Музыка, лейтмотивы, звуки | `deepseek/deepseek-v3.2` |
| **HR Agent** | Создание новых агентов под задачу | `deepseek/deepseek-v3.2` |

### Agent Status Values
- `idle` — готов к задаче
- `working` — выполняет задачу
- `waiting` — ждёт ответа/результата
- `error` — провал оценки (МЕД-ОТДЕЛ лечит)

---

## Key API Endpoints

### Agents
- `GET /api/agents` — список всех агентов
- `GET /api/agents/{id}` — получить агента
- `PUT /api/agents/{id}` — обновить модель/инструкции
- `POST /api/agents/{id}/upload` — прикрепить файл

### Chat
- `POST /api/chat/{agent_id}` — отправить сообщение, получить ответ

### Orchestrator
- `POST /api/orchestrator/submit` — отправить задачу
- `GET /api/orchestrator/status/{task_id}` — статус задачи
- `POST /api/orchestrator/intervene/{task_id}` — вмешаться
- `GET /api/orchestrator/history` — история задач
- `GET /api/orchestrator/registry` — реестр агентов

### МЕД-ОТДЕЛ
- `POST /api/med-otdel/evaluate` — оценить результат агента

### Project
- `GET /api/project` — текущий проект
- `PUT /api/project` — обновить проект
- `POST /api/project/upload-script` — загрузить сценарий

### Episodes
- `POST /api/episodes` — создать эпизод
- `GET /api/episodes` — список эпизодов
- `PUT /api/episodes/{id}` — обновить эпизод

### Characters
- `POST /api/characters` — создать персонажа
- `GET /api/characters` — список персонажей

---

## Development Conventions

### Working Cycle (обязательный)
Каждая задача проходит цикл:
1. **Plan** — план реализации
2. **Critic** — автоматическая оценка плана
3. **Fixer** — автоматическое исправление замечаний
4. **Critic** — перепроверка
5. **Максимум 3 круга** Critic/Fixer, затем стоп и вопрос пользователю
6. **"ок" от пользователя** → Build (реализация)

### Code Style
- Python 3.11+ с async/await
- SQLAlchemy async модели
- Pydantic для валидации
- UTF-8 encoding везде
- Atomic file writes через `os.replace()`
- Thread-safe операции с `_state_lock`

### Architecture Patterns
- **Event Bus** — все результаты задач пишутся в `events_bus.json`
- **МЕД-ОТДЕЛ** — фоновый мониторинг каждые 30 секунд
- **Critic/Fixer Cycle** — макс 3 попытки исправления на каждом шаге
- **Summarization** — между шагами цепочки LLM извлекает нужное для следующего агента
- **Degraded Fallback** — если Fixer не справился → оригинальный результат

### Database
- SQLite с WAL mode
- `busy_timeout=5000` для конкурентного доступа
- 20+ таблиц: projects, seasons, episodes, scenes, agents, messages, events, characters и др.
- Async session через `async_sessionmaker`

### Memory
- JSON файлы для быстрого доступа (agents_state.json, project_memory.json)
- SQLite для структурированных данных
- Atomic writes для предотвращения corruption

### Security
- `.env` для всех секретов (НИКОГДА не коммитить)
- HTTP Basic Auth middleware (пока отключён для локальной разработки)
- Rate limiting configurable через `RATE_LIMIT_REQUESTS_PER_MIN`

---

## Key Integration Points

### External Tools (Фаза 6)
| Tool | Purpose | Status |
|------|---------|--------|
| ComfyUI `localhost:8188` | Генерация изображений | Planned |
| Kie.ai | Генерация изображений через API | Planned |
| ElevenLabs | Генерация голосов персонажей | Planned |
| Kling AI | Генерация видео | Planned |
| Suno | Создание музыки | Planned |

### OpenRouter Models
Все агенты используют OpenRouter API. Модели можно менять через UI:
- `qwen/qwen3.5-9b`
- `deepseek/deepseek-v3.2`
- `google/gemini-3-flash-preview`
- `claude-opus-4-5` (и другие)

---

## Testing

Нет формального test suite. Тестирование через:
1. Ручная проверка UI в браузере `http://localhost:7860`
2. Тестовые скрипты в корне (`test_*.py`)
3. Playwright для e2e тестов (через @tester agent)

---

## Common Commands

```bash
# Запустить сервер
python main.py

# Проверить здоровье
curl http://localhost:7860/health

# Посмотреть логи
type logs\app.log

# Проверить состояние агентов
type memory\agents_state.json

# Проверить активный проект
type memory\project_memory.json
```

---

## Important Notes

- **Port 7860** выбран чтобы не конфликтовать с ComfyUI (8188)
- **constitution.md** — НЕИЗМЕНЯЕМАЯ часть, все агенты обязаны её учитывать
- **МЕД-ОТДЕЛ** — главная фича самообучения, адаптируется из v1 `agent_memory.py`
- **Supabase** — запланирован на второй этап, сейчас SQLite
- **Python 3.13** на Windows требует `WindowsSelectorEventLoopPolicy`
- **Cyrillic** — везде UTF-8, кастомный `UTF8JSONResponse` для корректного вывода
