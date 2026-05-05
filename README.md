# ARIS — Autonomous Reasoning & Intelligence System

A fully autonomous personal AI assistant built with FastAPI, Gemini, Ollama, and React.

---

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

---

## Phase 2 — Communication Layer ✅

### Stack additions
- **Google OAuth2:** google-auth, google-auth-oauthlib
- **Gmail API:** google-api-python-client
- **Google Calendar API:** google-api-python-client
- **Task Management:** Todoist API (todoist-api-python)
- **Relationship Memory:** ChromaDB (extended)
- **Intent Router:** Gemini function calling + keyword fallback
- **Smart model routing:** llama3.2 / mistral / gemma3:4b by task type

### Features
- **Gmail** — read inbox (with category filtering), search, send, draft emails
- **Google Calendar** — fetch today/week events, create events, conflict detection
- **Todoist** — create, read, complete, delete tasks via natural language
- **Relationship Memory** — store people with birthdays, notes, last contact nudges
- **Natural Language Router** — ARIS detects intent and calls the right integration automatically
- **Smart Model Routing** — right Ollama model for the right job, Gemini as fallback only
- **Daily Briefing** — morning summary of calendar + emails + tasks + contacts
- **Frontend upgrades** — quick action buttons, briefing modal, integration status bar, structured cards

### New API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /auth/google/login | Start Google OAuth2 flow |
| GET | /auth/status | Check Google connection status |
| GET | /briefing | Full morning briefing |
| GET | /integrations/gmail/inbox | Read inbox (supports category filter) |
| GET | /integrations/gmail/search | Search emails |
| GET | /integrations/gmail/message/{id} | Get single email |
| POST | /integrations/gmail/send | Send email |
| POST | /integrations/gmail/draft | Create draft |
| GET | /integrations/calendar/today | Today's events |
| GET | /integrations/calendar/week | This week's events |
| POST | /integrations/calendar/create | Create event |
| DELETE | /integrations/calendar/{id} | Delete event |
| GET | /integrations/calendar/conflicts | Check time slot conflicts |
| GET | /integrations/tasks | Get all tasks |
| GET | /integrations/tasks/today | Tasks due today |
| GET | /integrations/tasks/overdue | Overdue tasks |
| POST | /integrations/tasks | Create task |
| PUT | /integrations/tasks/{id} | Update task |
| POST | /integrations/tasks/{id}/complete | Complete task |
| DELETE | /integrations/tasks/{id} | Delete task |
| GET | /integrations/tasks/projects | List projects |
| GET | /relationships | All saved people |
| POST | /relationships | Add/update person |
| GET | /relationships/{name} | Get person by name |
| GET | /relationships/search | Semantic people search |
| GET | /relationships/neglected | Contacts not reached in N days |
| GET | /relationships/birthdays | Upcoming birthdays |
| PUT | /relationships/{name}/contact | Update last contact date |
| DELETE | /relationships/{name} | Remove person |

### Phase 1 API Endpoints
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

---

## Run Locally

### Prerequisites
- Python 3.11+
- Node.js 18+
- Ollama running locally with `llama3.2`, `mistral`, `gemma3:4b`, `nomic-embed-text`
- Gemini API key
- Google Cloud project with Gmail + Calendar APIs enabled
- Todoist account + API token

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Environment Variables
Create `backend/.env`:
```env
GEMINI_API_KEY=your_gemini_api_key
OLLAMA_BASE_URL=http://localhost:11434
PRIMARY_MODEL=gemini-2.5-flash
FALLBACK_MODEL=llama3.2
ARIS_TRUST_LEVEL=ask
TODOIST_API_TOKEN=your_todoist_token
OLLAMA_CHAT_MODEL=llama3.2
OLLAMA_WRITE_MODEL=mistral
OLLAMA_REASON_MODEL=gemma3:4b
```

### Google OAuth Setup
1. Create a Google Cloud project
2. Enable Gmail API + Google Calendar API
3. Create OAuth2 credentials → download as `backend/credentials.json`
4. Add your email as a test user in OAuth consent screen
5. Visit `http://localhost:8000/auth/google/login` to authenticate

> `credentials.json` and `token.json` are gitignored — never commit them.

---

## Project Structure
ARIS/
├── backend/
│   ├── main.py                  # FastAPI app + all routes
│   ├── database.py              # SQLite long-term memory
│   ├── semantic_memory.py       # ChromaDB vector memory
│   ├── user_profile.py          # User profile + adaptive prompt
│   ├── safety.py                # Content filter + guardrails
│   ├── auth/
│   │   └── google_auth.py       # Google OAuth2 flow
│   ├── integrations/
│   │   ├── gmail.py             # Gmail integration
│   │   ├── calendar.py          # Google Calendar integration
│   │   ├── tasks.py             # Todoist integration
│   │   ├── relationships.py     # Relationship memory
│   │   └── router.py            # Natural language intent router
│   └── credentials.example.json # OAuth credentials template
├── frontend/
│   └── src/
│       ├── App.jsx              # Main React UI
│       └── App.css              # Styles
└── README.md

---

## Phase 3 — Coming Soon
- 🔍 Web search — ARIS browses the internet for you
- 🖥️ System control — open apps, control your PC
- 📊 Data analysis — analyze files, CSVs, generate charts
- 🤖 Autonomous agents — ARIS completes multi-step tasks on its own
- 📱 Mobile PWA — access ARIS from your phone
- 🐳 Docker deployment