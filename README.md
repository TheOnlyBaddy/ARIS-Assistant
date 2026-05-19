# ARIS — Autonomous Reasoning & Intelligence System

A fully autonomous personal AI assistant built with FastAPI, Gemini, Whisper, and React.  
Talks to you. Sees your screen. Manages your life.

---

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | Core Brain — chat, memory, safety | ✅ Complete |
| 2 | Communication Layer — Gmail, Calendar, Todoist | ✅ Complete |
| 3 | Voice & Vision — mic, STT, TTS, screen/camera/OCR | ✅ Complete |

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
- Dark-mode chat UI

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
- **Gmail** — read inbox, search, send, draft emails
- **Google Calendar** — fetch today/week events, create events, conflict detection
- **Todoist** — create, read, complete, delete tasks via natural language
- **Relationship Memory** — store people with birthdays, notes, last contact nudges
- **Natural Language Router** — ARIS detects intent and calls the right integration automatically
- **Smart Model Routing** — right Ollama model for the right job, Gemini as fallback
- **Daily Briefing** — morning summary of calendar, emails, tasks, contacts
- **Frontend** — quick action buttons, briefing modal, integration status bar, structured cards

### API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /auth/google/login | Start Google OAuth2 flow |
| GET | /auth/status | Check Google connection status |
| GET | /briefing | Full morning briefing |
| GET | /integrations/gmail/inbox | Read inbox |
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

---

## Phase 3 — Voice & Vision ✅

### Stack additions
- **Speech-to-Text:** OpenAI Whisper (local, runs offline)
- **Text-to-Speech:** pyttsx3 — Microsoft Zira (local, no API cost)
- **Screen Vision:** Gemini Vision (gemini-2.5-flash) — captures and describes your screen
- **Camera Vision:** OpenCV + Gemini Vision — captures and describes webcam feed
- **OCR:** Gemini Vision — reads and summarizes text from screen or image
- **Emotion Detection:** Whisper tone analysis — detects emotion in speech
- **Audio output:** Auto-selects best available audio device

### Features
- **Voice pipeline** — wake word → record → Whisper STT → ARIS brain → pyttsx3 TTS, fully local
- **Emotion awareness** — detects how you sound (neutral, happy, stressed, tired) and responds accordingly
- **Live transcription** — shows what ARIS heard as a chat message in real time
- **See My Screen** — ARIS captures your screen and gives a natural language description
- **Use Camera** — ARIS captures your webcam and describes what it sees
- **Scan Text (OCR)** — ARIS reads all visible text from your screen and summarizes it
- **Vision result cards** — captured images shown inline in the chat bubble
- **Voice status badge** — live indicator in header and sidebar: Listening / Recording / Thinking / Speaking
- **Mic button** — toggle voice mode directly from the input bar
- **Emotion tag** — ARIS messages show detected emotion when voice is active

### API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /voice/start | Start voice pipeline (wake word + STT + TTS loop) |
| POST | /voice/stop | Stop voice pipeline |
| GET | /voice/status | Poll current voice state, last heard, last reply, emotion |
| GET | /vision/screen | Capture + describe screen |
| GET | /vision/camera | Capture + describe webcam |
| GET | /vision/ocr | OCR screen or image, returns summarized text |
| GET | /vision/image | Serve a captured image by path |

---

## Run Locally

### Prerequisites
- Python 3.11+
- Node.js 18+
- Ollama running locally with `llama3.2`, `mistral`, `gemma3:4b`, `nomic-embed-text`
- Gemini API key
- Google Cloud project with Gmail + Calendar APIs enabled
- Todoist account + API token
- Webcam (optional, for camera vision)
- Microphone (for voice mode)

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

Open `http://localhost:5173` in your browser.

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
4. Add your email as a test user in the OAuth consent screen
5. Visit `http://localhost:8000/auth/google/login` to authenticate

> `credentials.json` and `token.json` are gitignored — never commit them.

---

## Project Structure

```
ARIS/
├── backend/
│   ├── main.py                    # FastAPI app + all routes
│   ├── database.py                # SQLite long-term memory
│   ├── semantic_memory.py         # ChromaDB vector memory
│   ├── user_profile.py            # User profile + adaptive prompt
│   ├── safety.py                  # Content filter + guardrails
│   ├── auth/
│   │   └── google_auth.py         # Google OAuth2 flow
│   ├── integrations/
│   │   ├── gmail.py               # Gmail integration
│   │   ├── calendar.py            # Google Calendar integration
│   │   ├── tasks.py               # Todoist integration
│   │   ├── relationships.py       # Relationship memory
│   │   └── router.py              # Natural language intent router
│   ├── voice/
│   │   ├── pipeline.py            # Wake word → STT → brain → TTS loop
│   │   ├── stt.py                 # Whisper speech-to-text
│   │   ├── tts.py                 # pyttsx3 text-to-speech
│   │   └── emotion.py             # Tone/emotion detection
│   ├── vision/
│   │   ├── screen.py              # Screen capture + Gemini Vision
│   │   ├── camera.py              # Webcam capture + Gemini Vision
│   │   └── ocr.py                 # OCR via Gemini Vision
│   └── credentials.example.json   # OAuth credentials template
├── frontend/
│   └── src/
│       ├── App.jsx                # Main React UI
│       ├── App.css                # Styles
│       └── index.css              # Base reset + CSS variables
└── README.md
```

---

## .gitignore

Make sure your `.gitignore` includes:
```
# Secrets
backend/.env
backend/credentials.json
backend/token.json

# Vision captures (can be large)
backend/vision/screenshots/
backend/vision/captures/

# Python
__pycache__/
*.pyc
venv/
.venv/

# Node
node_modules/
dist/

# DB & vector store
*.db
backend/chroma_store/

# OS
.DS_Store
Thumbs.db
```

---

## Phase 4 — Planned
- 🔍 Web search — ARIS browses the internet for you
- 🖥️ System control — open apps, control your PC
- 📊 Data analysis — analyze files, CSVs, generate charts
- 🤖 Autonomous agents — ARIS completes multi-step tasks on its own
- 📱 Mobile PWA — access ARIS from your phone
- 🐳 Docker deployment