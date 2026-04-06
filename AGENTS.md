# AGENTS.md

Compact instruction file for OpenCode agents working on Animation Studio v2.

## Quick Start

```bash
# Start server (Windows)
run.bat
# or: python main.py

# Server runs on http://localhost:7860
# Logs: logs/app.log
```

**Python 3.13 on Windows:** `main.py` sets `WindowsSelectorEventLoopPolicy` automatically.

## Environment Setup

Copy `.env.example` to `.env` and fill:
- `OPENROUTER_API_KEY` (required)
- `KIEAI_API_KEY` (for image generation)
- `COMFYUI_URL` (default: `http://localhost:8188`)
- `ELEVENLABS_API_KEY` (for voice generation)

## Architecture

**Backend:** FastAPI + Hypercorn (async), SQLite + SQLAlchemy async  
**Frontend:** Vanilla HTML/CSS/JS in `static/`  
**AI:** OpenRouter API for all agents  
**Image Gen:** Kie.ai Z-Image (primary), ComfyUI (fallback)

### Key Entry Points

- `main.py` — FastAPI server, lifespan hooks, МЕД-ОТДЕЛ background monitor (30s interval)
- `config.py` — loads `.env`, defines all constants
- `database.py` — SQLAlchemy async models (20+ tables), `init_db()`, `get_session()`
- `agents/base_agent.py` — base class for all agents, OpenRouter integration, state management

### Critical Files

- `constitution.md` — **IMMUTABLE** studio rules, all agents must follow
- `orchestrator/agent_registry.json` — 8 agents with capabilities, models, timeouts
- `agents/instructions.json` — system instructions per agent role
- `memory/agents_state.json` — agent state (model, status, chat history)
- `memory/project_memory.json` — active project context

## Agent System

10 AI agents, each with role, model (configurable via OpenRouter), and instructions:

| Agent | Role | Default Model |
|-------|------|---------------|
| Orchestrator | Task chain builder | `qwen/qwen3.5-9b` |
| Writer | Script adaptation | `deepseek/deepseek-v3.2` |
| Director | Visual strategy | `deepseek/deepseek-v3.2` |
| Critic | Quality evaluation | `deepseek/deepseek-v3.2` |
| Fixer | Fix based on Critic feedback | `deepseek/deepseek-v3.2` |
| Storyboarder | Frame breakdown with timing | `deepseek/deepseek-v3.2` |
| DOP | Lighting, camera, atmosphere | `deepseek/deepseek-v3.2` |
| Art Director | Style, color, Kie.ai prompts | `deepseek/deepseek-v3.2` |
| Sound Director | Music, voice, soundscapes | `deepseek/deepseek-v3.2` |
| HR Agent | Creates new agents on demand | `deepseek/deepseek-v3.2` |

**Agent statuses:** `idle`, `working`, `waiting`, `error`

## Production Pipeline

Full scene pipeline with Critic/Fixer at each step (max 3 attempts):

1. Writer → scene description
2. Director → creative decisions
3. HR (Casting) → character cards (auto-pattern `character_consistency`)
4. DOP + Art Director + Sound Director (parallel) → each writes their part
5. Storyboarder → assembles frame prompts
6. Art Director → sends to Kie.ai → image generation
7. CV Check (Gemini Vision) → auto-fix cycle if score < 8 (max 3 attempts)
8. Storyboarder → assembles final scene

**Endpoint:** `POST /api/orchestrator/scene-pipeline`

## МЕД-ОТДЕЛ (Self-Learning System)

Background monitor runs every 30 seconds (started in `main.py` lifespan).

### Three Modes

| Mode | Trigger | Action |
|------|---------|--------|
| `agent_heal` | 2+ consecutive fails by one agent | Evolve agent prompt (v1→v2→v3) |
| `chain_heal` | Fails at agent→agent boundary (same `task_id`) | Evolve receiving agent's prompt |
| `studio_alert` | 50%+ agents in `error` status | Pause studio, notify user |

**Event bus:** `memory/events_bus.json` — all task results written here  
**Logs:** `memory/med_log.json`  
**Prompt versions:** `med_otdel/versions/{agent}.json` (no rollback, only forward)

## Database

SQLite with WAL mode, `busy_timeout=5000` for concurrent access.

**Key tables:** projects, seasons, episodes, scenes, agents, messages, events, characters, storyboard_frames, med_logs

**Session:** Use `async with get_session() as db:` for all DB operations.

## Common Patterns

### Atomic JSON Writes

All JSON state files use atomic writes via `tempfile.mkstemp()` + `os.replace()` to prevent corruption.

### Critic/Fixer Cycle

Max 3 attempts per step. If Fixer fails after 3 rounds → degraded fallback (use original result).

### Summarization Between Steps

Orchestrator uses LLM to extract relevant info from previous step's output before passing to next agent.

### CV Auto-Check

After Kie.ai generates image, Gemini Vision checks against scene description. If score < 8, auto-fix cycle runs (Critic → Fixer → Kie.ai regenerate, max 3 attempts).

## Testing

No formal test suite. Test via:
1. Manual UI testing at `http://localhost:7860`
2. Ad-hoc test scripts in `tools/` (e.g., `check_*.py`)
3. E2e test reports in `docs/`

## Important Quirks

- **UTF-8 everywhere:** Custom `UTF8JSONResponse` in `main.py` for correct Cyrillic rendering
- **Port 7860:** Chosen to avoid conflict with ComfyUI (8188)
- **constitution.md is immutable:** All agents must respect it, never modify
- **No venv in repo:** `run.bat` checks for venv, installs deps if missing
- **Thread-safe state:** `_state_lock` in base_agent.py, `_bus_lock` in med_core.py
- **Kie.ai polling:** Default 60 attempts × 2s = 2min timeout for image generation
- **ComfyUI polling:** Default 150 attempts × 5s = 12.5min timeout (fallback only)

## API Structure

All routes in `api/` with prefixes set in `main.py`:
- `/api/agents` — CRUD agents
- `/api/chat/{agent_id}` — chat with agent
- `/api/orchestrator` — task submission, status, history
- `/api/project` — project management
- `/api/episodes` — episodes/seasons
- `/api/characters` — character cards
- `/api/tools` — Kie.ai, ComfyUI, CV check
- `/api/med-otdel` — МЕД-ОТДЕЛ evaluation

## File Attachments

Agents can receive files (PDF, TXT, MD, JSON, images). Stored in `memory/attachments/`.

**PDF extraction:** Uses `pypdf.PdfReader` in `base_agent.py`

## Multi-Project Support

Projects stored in DB (`projects` table). Active project in `memory/project_memory.json`.

**Structure:** Project → Seasons → Episodes → Scenes → Frames

## Known Issues

- Auth middleware disabled in `main.py` (line 130) for local dev
- Supabase integration planned but not implemented (SQLite only)
- External tools (ElevenLabs, Suno, Kling AI) planned but not integrated yet

## Development Notes

- All agent instructions start empty, loaded from `agents/instructions.json` or DB
- Project context auto-injected from active project file
- Discussion channel logs all orchestrator actions to `memory/discussion_log.json`
- Backup files in `memory/backup/` for recovery
- Static files served with no-cache headers via `NoCacheStaticFiles` class

## Debugging

```bash
# Check agent state
type memory\agents_state.json

# Check active project
type memory\project_memory.json

# Check МЕД-ОТДЕЛ logs
type memory\med_log.json

# Check orchestrator tasks
type memory\orchestrator_tasks.json

# View server logs
type logs\app.log
```

## References

- `README.md` — user-facing overview
- `project.md` — detailed project bible (652 lines)
- `QWEN.md` — comprehensive context doc for AI agents
- `constitution.md` — studio rules (25 lines, immutable)
- `.kieai-plan.md`, `.kieai-rule-builder-plan.md` — planning docs (ignore for code work)
