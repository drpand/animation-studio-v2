# Animation Studio v2 — РОДИНА

AI-powered anime production studio. Web-based interface where each agent is a team member with their own role, chat, and production pipeline.

## Quick Start

```bash
# 1. Configure API keys
copy .env.example .env
# Edit .env and add your OpenRouter and Kie.ai API keys

# 2. Run
run.bat
# or: python main.py

# 3. Open browser
http://localhost:7860
```

## Features

### 🎬 Production Pipeline
- **Writer** — writes scripts from ideas
- **Director** — creative decisions, shot composition
- **HR/Casting** — extracts characters from scripts, no hallucinations
- **DOP** — lighting, camera angles, atmosphere
- **Art Director** — visual style, Kie.ai prompts
- **Sound Director** — music, voice, soundscapes
- **Storyboarder** — assembles frames from all departments
- **Critic + Fixer** — quality control after each step (max 3 rounds)

### 🔧 Frame Revision System
- **Edit prompt** directly in the frame modal
- **Regenerate** with edited prompt via Kie.ai
- **"On revision" button** — Art Director rewrites prompt → Kie.ai regenerates

### 🤖 CV Verification
- **CV Check** — Gemini vision model compares generated image against scene description
- Scores 0-10, lists matched/missing elements, mood assessment
- **Auto-fix cycle** — CV → Critic analyzes → Fixer rewrites prompt → Kie.ai regenerates → repeat (max 3 attempts)
- Full history of all attempts shown in UI

### 🏗️ Project Management
- **New Project** — create projects with name, description, genre, style, palette, music reference
- **Reset** — clears all frames, characters, messages for a fresh start
- **Multi-project** foundation (switching coming in v4)

### 🧠 MED-OTDEL (Self-Learning)
- Monitors agent health across the studio
- Auto-evolves prompts when agents fail repeatedly
- Chain analysis for agent-to-agent failures
- Studio-wide alert when 50%+ agents are in error state

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, Hypercorn |
| Database | SQLite (aiosqlite async) |
| LLM | OpenRouter API (Gemini, Claude, Qwen, GPT-4o) |
| Image Gen | Kie.ai Z-Image (ComfyUI fallback) |
| Frontend | Vanilla HTML/CSS/JS, no frameworks |

## API Endpoints

### Project
- `GET /api/project/` — active project
- `POST /api/project/create` — create new project
- `POST /api/project/reset` — clear all content
- `GET /api/project/list` — list all projects

### Orchestrator
- `POST /api/orchestrator/submit` — submit task
- `POST /api/orchestrator/scene-pipeline` — run full scene pipeline
- `GET /api/orchestrator/storyboard/frames` — get all storyboard frames
- `POST /api/orchestrator/revise-frame/{id}` — revise frame with Art Director + Kie.ai

### Tools
- `POST /api/tools/cv-check` — CV verification of a frame
- `POST /api/tools/cv-auto-fix/{id}` — auto-fix cycle (CV → Critic → Fixer → Kie.ai)
- `POST /api/tools/generate-image` — generate image via Kie.ai

### Agents
- `GET /api/agents/` — list all agents
- `POST /api/chat/{agent_id}` — chat with agent
- `POST /api/hr/create-agent` — HR creates new agent

## Project Structure

```
animation-studio-v2/
├── main.py                  # FastAPI server
├── run.bat                  # One-click launch
├── config.py                # API keys, settings
├── database.py              # SQLAlchemy models + session
├── crud.py                  # Database operations
├── models.py                # Pydantic schemas
├── constitution.md          # Studio constitution (shared rules)
│
├── agents/                  # Agent definitions
├── api/                     # REST endpoints
│   ├── agents_api.py
│   ├── chat_api.py
│   ├── orchestrator_api.py
│   ├── project_api.py
│   ├── cv_check_api.py      # CV verification
│   └── ...
├── orchestrator/            # Task chain, executor, registry
├── med_otdel/               # Self-learning system
├── tools/                   # Kie.ai, ComfyUI, ElevenLabs
├── static/                  # Frontend
│   ├── index.html
│   ├── style.css
│   └── app.js
└── memory/                  # Local storage
    ├── studio.db            # SQLite database
    ├── project_memory.json
    └── agents_state.json
```

## Configuration (.env)

```env
OPENROUTER_API_KEY=sk-or-v1-...
KIEAI_API_KEY=kie_...
ELEVENLABS_API_KEY=...
```

## License

Private project. All rights reserved.
