# ARIS — Autonomous Reasoning & Intelligence System

A fully autonomous personal AI assistant built with FastAPI, Gemini, and React.

## Phase 1 — Core Brain ✅

### Stack
- **Backend:** FastAPI + Python 3.11
- **Primary AI:** Gemini 2.5 Flash
- **Fallback AI:** Ollama (llama3.2) — works fully offline
- **Short-term memory:** In-memory conversation store (per session)
- **Long-term memory:** SQLite via SQLAlchemy
- **Semantic memory:** ChromaDB + nomic-embed-text (Ollama)
- **Frontend:** React + Vite

### Features
- Multi-turn conversation with full memory
- Persistent memory across server restarts
- Semantic (vector) search across all past sessions
- User profile with adaptive persona
- Safety guardrails with confirmation flow
- Clean dark-mode chat UI

### Run Locally

**Backend:**
```bash
cd backend
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm run dev
```

**Requires:**
- Gemini API key in `.env`
- Ollama running locally with `llama3.2` and `nomic-embed-text`

### API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Server health + stats |
| POST | /chat | Main chat endpoint |
| GET | /profile | User profile |
| PUT | /profile | Update profile field |
| GET | /memory/{id} | Inspect session history |
| GET | /sessions | List all sessions |
| GET | /semantic-memory | Vector memory stats |
| GET | /safety | Safety config |

## Phase 2 — Coming Soon
- Agent system (web search, file ops, code execution)
- Voice interface
- Docker deployment
- Mobile app