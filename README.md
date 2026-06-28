# ARIS — Autonomous Reasoning & Intelligence System

A fully autonomous personal AI assistant built with FastAPI, Gemini, Whisper, and React.  
Talks to you. Sees your screen. Controls your PC. Manages your life.

---

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 0 | Environment Setup | ✅ Complete |
| 1 | Core Brain — chat, memory, safety | ✅ Complete |
| 2 | Communication Layer — Gmail, Calendar, Todoist | ✅ Complete |
| 3 | Voice & Vision — mic, STT, TTS, screen/camera/OCR | ✅ Complete |
| 4 | Device & Computer Control — PC, files, system, browser | ✅ Complete |
| 5 | Autonomous Agents & Workflows | 🔜 Next |
| 6 | Self-improvement & Advanced Reasoning | 🔜 Planned |

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
- **Wake Word:** OpenWakeWord ("hey_jarvis", threshold 0.1)
- **Screen Vision:** Gemini Vision (gemini-2.5-flash)
- **Camera Vision:** OpenCV + Gemini Vision
- **OCR:** Gemini Vision — reads and summarizes text from screen or image
- **Emotion Detection:** Rule-based hybrid (audio energy + keyword matching)
- **Audio:** Auto-selects best available output device by name

### Features
- **Voice pipeline** — wake word → record → Whisper STT → ARIS brain → TTS, fully local
- **Emotion awareness** — detects how you sound and responds accordingly
- **Live transcription** — shows what ARIS heard as a chat message in real time
- **See My Screen** — ARIS captures your screen and gives a natural language description
- **Use Camera** — ARIS captures your webcam and describes what it sees
- **Scan Text (OCR)** — reads all visible text from screen and summarizes it
- **Vision result cards** — captured images shown inline in the chat bubble
- **Voice status badge** — live indicator: Listening / Recording / Thinking / Speaking
- **Mic button** — toggle voice mode directly from the input bar

### API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /voice/start | Start voice pipeline |
| POST | /voice/stop | Stop voice pipeline |
| GET | /voice/status | Poll voice state, emotion, last heard/reply |
| POST | /voice/speak | Manually trigger TTS |
| POST | /voice/transcribe | Transcribe uploaded audio file |
| GET | /vision/screen | Capture + describe screen |
| GET | /vision/camera | Capture + describe webcam |
| GET | /vision/ocr | OCR screen or image |

---

## Phase 4 — Device & Computer Control ✅

### Stack additions
- **PC Automation:** PyAutoGUI — mouse, keyboard, screenshots
- **Windows API:** pywin32 — window management
- **System Monitoring:** psutil — CPU, RAM, disk, battery, processes
- **Browser Automation:** Playwright (Chromium) — single dedicated thread pattern
- **Clipboard:** pyperclip — read/write clipboard
- **Notifications:** plyer — Windows toast notifications
- **Safety:** SQLite audit log for all control actions

### Features

#### 🖱️ PC Control
- Move mouse, click, double-click, right-click, scroll
- Type text, press keys, hotkey combos (Ctrl+C, Alt+Tab, Win+D etc.)
- Open apps by name — 18 apps mapped (Chrome, Spotify, VS Code, Notepad etc.)
- Close, minimize, maximize, focus windows by title
- List all open windows

#### 📁 File Management
- List directory contents (folders first, with size + modified date)
- Create files with content, create folders
- Read file contents (with truncation limit)
- Write / append to files
- Rename, move, copy files and folders
- Delete with confirmation required
- Search files by name or extension recursively
- Open files with default app, open folders in Explorer

#### 📊 System Monitoring
- CPU usage, core count, frequency
- RAM total / used / free / percent
- Disk usage per drive with free space
- Battery level, charging status
- Network bytes sent/received
- Running process list (sort by CPU, RAM, or name)
- Kill process by name or PID (confirmation required)
- SSE live stream endpoint (updates every 2s)

#### 🌐 Browser Automation
- Open any URL in Chromium (visible browser)
- Search Google and extract results
- Click elements by selector, text, or coordinates
- Fill form fields, submit with Enter
- Extract visible page text
- Take browser screenshots
- Single dedicated background thread + queue (fixes Windows asyncio conflict)

#### 📋 Clipboard & Notifications
- Read current clipboard content
- Write any text to clipboard
- Send Windows desktop toast notifications
- Notification history log

#### 🧠 Natural Language Control (25+ intents)
- "Open Spotify" → launches app
- "What's my CPU usage?" → system stats
- "Search for Python tutorials" → browser search
- "Create a file called notes.txt on my desktop" → file creation
- "Kill Chrome" → process kill (with confirmation)
- "Take a screenshot" → captures screen
- "Copy this to clipboard" → clipboard write
- Gemini function calling + keyword fallback

#### 🛡️ Safety Layer
- Confirmation required before: delete file, kill process, close app, overwrite file
- Every control action logged to `audit_log.db` with timestamp
- Audit log viewable via `/control/audit`

#### 🖥️ Frontend System Dashboard
- Live CPU and RAM circular gauges (colour-coded: green → amber → red)
- Battery gauge with charging indicator
- Disk usage bars per drive
- Running process table (sort by CPU/RAM/name)
- Auto-refreshes every 3 seconds
- Ollama model pills in sidebar with role badges (chat / write / reason)

### LLM Routing Strategy
| Request type | Model | Reason |
|---|---|---|
| Complex questions, explanations, writing | Gemini 2.5 Flash | Best reasoning quality |
| Email data, calendar, files, system stats | gemma3:4b | Best at data summarization |
| Email writing, summaries | mistral | Best prose quality |
| General chat, simple questions | llama3.2 | Fast, lightweight, local |
| Any model down | Gemini | Emergency fallback |

### API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /control/pc/mouse/move | Move mouse to coordinates |
| POST | /control/pc/mouse/click | Click at position |
| POST | /control/pc/keyboard/type | Type text |
| POST | /control/pc/keyboard/hotkey | Press key combo |
| POST | /control/pc/app/open | Open application by name |
| POST | /control/pc/window/close | Close window by title |
| POST | /control/pc/window/minimize | Minimize window |
| POST | /control/pc/window/maximize | Maximize window |
| GET | /control/pc/window/list | List all open windows |
| POST | /control/pc/screenshot | Take screenshot |
| GET | /control/pc/clipboard | Read clipboard |
| POST | /control/pc/clipboard | Write clipboard |
| POST | /control/files/list | List directory |
| POST | /control/files/create | Create file |
| POST | /control/files/folder | Create folder |
| POST | /control/files/read | Read file contents |
| POST | /control/files/write | Write to file |
| POST | /control/files/rename | Rename file/folder |
| POST | /control/files/move | Move file/folder |
| POST | /control/files/copy | Copy file/folder |
| POST | /control/files/delete | Delete (confirmation required) |
| POST | /control/files/search | Search files by name/extension |
| POST | /control/files/open | Open with default app |
| GET | /control/system | Full system snapshot |
| GET | /control/system/cpu | CPU usage |
| GET | /control/system/ram | RAM usage |
| GET | /control/system/disk | Disk usage |
| GET | /control/system/battery | Battery status |
| GET | /control/system/network | Network stats |
| GET | /control/system/stream | SSE live stats stream |
| POST | /control/system/processes | List processes |
| POST | /control/system/kill | Kill process (confirmation required) |
| GET | /control/system/ollama | Ollama + Gemini model status |
| POST | /control/browser/open | Open URL in Chromium |
| POST | /control/browser/search | Google search + results |
| POST | /control/browser/click | Click element |
| POST | /control/browser/fill | Fill form field |
| POST | /control/browser/text | Extract page text |
| POST | /control/browser/screenshot | Browser screenshot |
| GET | /control/browser/info | Current page title + URL |
| POST | /control/browser/close | Close browser |
| POST | /control/notify | Send desktop notification |
| GET | /control/notify/history | Notification history |
| GET | /control/audit | Control action audit log |
| GET | /auth/google/login | Start Google OAuth |
| GET | /auth/google/callback | OAuth callback |
| GET | /auth/google/status | Auth status |
| POST | /auth/google/logout | Disconnect Google |

---

## Run Locally

### Prerequisites
- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.com) installed and running
- Gemini API key
- Google Cloud project with OAuth credentials
- Todoist API token
- Webcam (optional, for camera vision)
- Microphone (for voice mode)

### 1. Clone & install

```powershell
git clone https://github.com/TheOnlyBaddy/ARIS-Assistant.git
cd ARIS-Assistant

# Backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd ..\frontend
npm install
```

### 2. Pull Ollama models

```powershell
ollama pull llama3.2
ollama pull mistral
ollama pull gemma3:4b
ollama pull nomic-embed-text
```

### 3. Install Playwright browser

```powershell
playwright install chromium
```

### 4. Environment variables

Create `backend/.env`:

```env
GEMINI_API_KEY=your_gemini_api_key
TODOIST_API_TOKEN=your_todoist_token
PRIMARY_MODEL=gemini-2.5-flash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=llama3.2
OLLAMA_WRITE_MODEL=mistral
OLLAMA_REASON_MODEL=gemma3:4b
ARIS_TRUST_LEVEL=ask
```

### 5. Google OAuth setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Enable Gmail API + Google Calendar API
3. Create OAuth 2.0 credentials (Web application)
4. Add `http://localhost:8000/auth/google/callback` to authorized redirect URIs
5. Download as `credentials.json` → place in `backend/`
6. Add your email as a test user in the OAuth consent screen
7. Click **Connect Google** in the ARIS sidebar to authenticate

### 6. Run

```powershell
# Terminal 1 — Backend
cd backend
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

---

## Project Structure

```
ARIS/
├── backend/
│   ├── main.py                    # FastAPI app + all routes
│   ├── database.py                # SQLite long-term memory
│   ├── semantic_memory.py         # ChromaDB vector memory
│   ├── user_profile.py            # User profile + adaptive prompt
│   ├── safety.py                  # Safety guardrails + audit log
│   ├── auth/
│   │   └── google_auth.py         # Google OAuth2 + frontend login/logout
│   ├── integrations/
│   │   ├── gmail.py               # Gmail integration
│   │   ├── calendar.py            # Google Calendar integration
│   │   ├── tasks.py               # Todoist integration
│   │   ├── relationships.py       # Relationship memory
│   │   └── router.py              # Intent router (25+ intents)
│   ├── voice/
│   │   ├── pipeline.py            # Wake word → STT → brain → TTS
│   │   ├── stt.py                 # Whisper STT
│   │   ├── tts.py                 # Kokoro + pyttsx3 TTS
│   │   └── emotion.py             # Voice emotion detection
│   ├── vision/
│   │   ├── screen.py              # Screen capture + Gemini Vision
│   │   ├── camera.py              # Webcam + Gemini Vision
│   │   └── ocr.py                 # OCR via Gemini Vision
│   └── control/
│       ├── __init__.py
│       ├── pc.py                  # Mouse, keyboard, apps, clipboard
│       ├── files.py               # File & folder management
│       ├── system.py              # System monitoring + process control
│       ├── browser.py             # Playwright browser automation
│       └── notify.py              # Windows desktop notifications
├── frontend/
│   └── src/
│       ├── App.jsx                # Main React UI + tab system
│       ├── App.css                # All styles
│       ├── index.css              # Base reset + CSS variables
│       └── components/
│           ├── GoogleAuthButton.jsx   # Google login/logout UI
│           └── SystemDashboard.jsx   # Live system stats dashboard
└── README.md
```

---

## Hardware Tested On

- CPU: Intel i5-12450HX (8P + 4E cores, 12 logical)
- GPU: NVIDIA RTX 4060 Laptop (8GB VRAM), CUDA 12.x
- RAM: 24GB DDR5
- Storage: 476GB NVMe + 953GB HDD
- OS: Windows 11
- Mic: Kreo Sonik USB
- Camera: External USB webcam

---

## .gitignore

Make sure your `.gitignore` includes:

```
# Secrets
backend/.env
backend/credentials.json
backend/token.json

# Vision captures
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

# Databases & vector store
*.db
backend/chroma_db/

# OS
.DS_Store
Thumbs.db
```

---

## Key Lessons Learned

- **Playwright on Windows:** Must run on a single dedicated thread created at startup with a `_task_queue` pattern — cannot be called from async FastAPI routes directly due to asyncio/uvicorn conflicts
- **Google OAuth PKCE:** `Flow` object must be stored between `/login` and `/callback` — creating a new one in the callback breaks the code verifier check
- **Ollama embeddings:** Endpoint changed from `/api/embeddings` → `/api/embed` in Ollama 0.2+; always try new first, fall back gracefully
- **Gemini function calling:** Can silently return no function call — always wrap with keyword fallback and never let the router crash the chat endpoint
- **LLM data routing:** Ollama models (llama3.2 especially) ignore structured data blocks — route data summarization tasks to gemma3:4b or Gemini

---