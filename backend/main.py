"""
ARIS - Autonomous Reasoning & Intelligence System
Backend Main Entry Point
Phase 2 - Communication Layer
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Any, Optional
import uvicorn
import os
import httpx
import threading
import json
from google import genai
from google.genai import types
from database import (
    init_db,
    save_message,
    load_all_sessions_from_db,
    get_all_sessions
)
from semantic_memory import (
    search_memories,
    extract_and_store_facts,
    get_memory_stats
)
from user_profile import (
    load_profile,
    save_profile,
    build_profile_prompt,
    update_profile_field,
    DEFAULT_PROFILE
)
from safety import (
    check_message_safety,
    get_safety_config,
    TrustLevel,
    TRUST_LEVEL
)
from auth.google_auth import (
    is_authenticated,
    run_auth_flow
)
from integrations.gmail import (
    read_inbox,
    search_emails,
    get_email,
    send_email,
    create_draft,
    get_inbox_summary
)
from integrations.calendar import (
    get_today_events,
    get_week_events,
    get_events,
    create_event,
    delete_event,
    check_conflicts,
    get_agenda_summary
)
from integrations.tasks import (
    get_all_tasks,
    get_today_tasks,
    get_overdue_tasks,
    create_task,
    update_task,
    complete_task,
    delete_task,
    get_projects,
    get_task_summary
)
from integrations.relationships import (
    save_person,
    get_person,
    get_all_people,
    search_people,
    delete_person,
    update_last_contact,
    get_neglected_contacts,
    get_upcoming_birthdays
)
from integrations.router import route_message, execute_intent
from integrations.tasks import get_task_summary
from integrations.calendar import get_agenda_summary
from integrations.gmail import get_inbox_summary

load_dotenv()

# ─── CONFIG ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
PRIMARY_MODEL   = os.getenv("PRIMARY_MODEL", "gemini-2.5-flash")
FALLBACK_MODEL  = os.getenv("FALLBACK_MODEL", "llama3.2")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Ollama model routing — right model for the right job
OLLAMA_CHAT_MODEL   = os.getenv("OLLAMA_CHAT_MODEL",   "llama3.2")   # General chat + simple reads
OLLAMA_WRITE_MODEL  = os.getenv("OLLAMA_WRITE_MODEL",  "mistral")     # Writing emails, summaries
OLLAMA_REASON_MODEL = os.getenv("OLLAMA_REASON_MODEL", "gemma3:4b")   # Complex reasoning, scheduling

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

ARIS_BASE_PROMPT = (
    "You are ARIS (Autonomous Reasoning & Intelligence System), "
    "a highly capable, friendly, and thoughtful personal AI assistant. "
    "You are helpful, concise, and always honest. "
    "Refer to yourself as ARIS, never as Gemini or any other AI. "
    "You have short-term conversation memory, long-term database memory, "
    "and semantic memory of important facts. "
    "Always adapt your tone and style to match the user profile below."
)

# ─── IN-MEMORY STORE ───────────────────────────────────────────────────────────

conversation_store: dict[str, list[dict]] = {}

# ─── FASTAPI SETUP ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="ARIS - Autonomous Reasoning & Intelligence System",
    description="Your personal AI assistant backend",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── STARTUP ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    print("[ARIS] Starting up...")
    init_db()
    global conversation_store
    conversation_store = load_all_sessions_from_db()
    profile = load_profile()
    stats   = get_memory_stats()
    safety  = get_safety_config()
    google  = "✓ connected" if is_authenticated() else "✗ not connected"
    print(f"[ARIS] Ready for {profile.get('name', 'User')} | "
          f"Sessions: {len(conversation_store)} | "
          f"Memories: {stats['total_memories']} | "
          f"Trust level: {safety['trust_level']} | "
          f"Google: {google}")

# ─── REQUEST / RESPONSE MODELS ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    confirmed: bool = False

class ChatResponse(BaseModel):
    response: str
    model_used: str
    session_id: str
    turn_count: int
    memories_used: int
    safety_status: str
    intent: str = "general_chat"
    integration_type: str = "none"

class ProfileUpdateRequest(BaseModel):
    field: str
    value: Any

# ─── PROMPT BUILDER ────────────────────────────────────────────────────────────

def build_full_system_prompt(memories: list[str]) -> str:
    profile       = load_profile()
    profile_block = build_profile_prompt(profile)
    prompt        = f"{ARIS_BASE_PROMPT}\n\n{profile_block}"

    if memories:
        memory_block = "\n\nLONG-TERM MEMORY (facts you know about this user):\n"
        for i, mem in enumerate(memories, 1):
            memory_block += f"  {i}. {mem}\n"
        memory_block += "\nUse these facts naturally when relevant."
        prompt += memory_block

    return prompt

# ─── HELPERS ───────────────────────────────────────────────────────────────────

def get_history(session_id: str) -> list[dict]:
    return conversation_store.get(session_id, [])


def add_to_memory(session_id: str, role: str, text: str, model_used: str = None):
    if session_id not in conversation_store:
        conversation_store[session_id] = []
    conversation_store[session_id].append({"role": role, "text": text})
    save_message(session_id, role, text, model_used)


def build_gemini_contents(history: list[dict]) -> list:
    return [
        types.Content(role=t["role"], parts=[types.Part(text=t["text"])])
        for t in history
    ]


def build_ollama_prompt(history: list[dict], system_prompt: str) -> str:
    prompt = f"{system_prompt}\n\n"
    for turn in history:
        label = "User" if turn["role"] == "user" else "ARIS"
        prompt += f"{label}: {turn['text']}\n"
    prompt += "ARIS:"
    return prompt

# ─── AI BRAIN ──────────────────────────────────────────────────────────────────

async def ask_gemini(history: list[dict], system_prompt: str) -> str:
    contents = build_gemini_contents(history)
    response = gemini_client.models.generate_content(
        model=PRIMARY_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7,
            max_output_tokens=1024,
        )
    )
    return response.text


async def ask_ollama(history: list[dict], system_prompt: str, model: str = None) -> str:
    model  = model or FALLBACK_MODEL
    prompt = build_ollama_prompt(history, system_prompt)
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False}
        )
        r.raise_for_status()
        return r.json()["response"]


async def ask_gemini_with_context(
    message: str,
    history: list[dict],
    system_prompt: str,
    integration_data: dict = None
) -> str:
    """Ask Gemini with integration data injected as context."""
    if integration_data and integration_data.get("type") not in ("general_chat", "none", None):
        data_str  = json.dumps(integration_data["data"], indent=2, default=str)
        data_type = integration_data["type"]

        context_prompts = {
            "emails":         f"Here are the emails retrieved:\n{data_str}\nSummarize them clearly and concisely for the user.",
            "events":         f"Here are the calendar events retrieved from Google Calendar:\n{data_str}\nPresent them clearly. IMPORTANT: If the list is empty [], tell the user their calendar is clear — do NOT invent or hallucinate any events.",
            "event_created":  f"Event created successfully:\n{data_str}\nConfirm this to the user in a friendly way.",
            "tasks":          f"Here are the tasks:\n{data_str}\nPresent them clearly. If empty [], say there are no tasks.",
            "task_created":   f"Task created successfully:\n{data_str}\nConfirm this to the user in a friendly way.",
            "task_completed": f"Task marked complete:\n{data_str}\nConfirm this to the user.",
            "email_sent":     f"Email sent successfully:\n{data_str}\nConfirm this to the user.",
            "person":         f"Here is the person's info from relationship memory:\n{data_str}\nPresent it naturally and helpfully.",
            "people":         f"Here are contacts who haven't been reached recently:\n{data_str}\nPresent them with a friendly nudge.",
            "birthdays":      f"Here are upcoming birthdays:\n{data_str}\nPresent them warmly.",
            "error":          f"An error occurred: {integration_data['data']}\nTell the user something went wrong and suggest they try again.",
        }

        context   = context_prompts.get(data_type, f"Integration data:\n{data_str}")
        augmented = f"{message}\n\n[INTEGRATION RESULT — use this to answer]\n{context}"
    else:
        augmented = message

    contents = build_gemini_contents(history[:-1])
    contents.append(types.Content(
        role="user",
        parts=[types.Part(text=augmented)]
    ))

    response = gemini_client.models.generate_content(
        model=PRIMARY_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7,
            max_output_tokens=1024,
        )
    )
    return response.text


async def ask_ollama_with_context(
    message: str,
    history: list[dict],
    system_prompt: str,
    integration_data: dict = None,
    model: str = None
) -> str:
    """Ask Ollama with integration data injected as context."""
    model = model or FALLBACK_MODEL

    if integration_data and integration_data.get("type") not in ("general_chat", "none", None):
        data_str  = json.dumps(integration_data["data"], indent=2, default=str)
        data_type = integration_data["type"]

        context_prompts = {
            "emails":         f"Here are the emails retrieved:\n{data_str}\nSummarize them clearly and concisely.",
            "events":         f"Here are the calendar events:\n{data_str}\nPresent them clearly. If empty [], say the calendar is clear — do NOT invent events.",
            "event_created":  f"Event created successfully:\n{data_str}\nConfirm to the user.",
            "tasks":          f"Here are the tasks:\n{data_str}\nPresent them clearly. If empty [], say there are no tasks.",
            "task_created":   f"Task created successfully:\n{data_str}\nConfirm to the user.",
            "task_completed": f"Task completed:\n{data_str}\nConfirm to the user.",
            "email_sent":     f"Email sent:\n{data_str}\nConfirm to the user.",
            "person":         f"Here is the person info:\n{data_str}\nPresent it naturally.",
            "people":         f"Here are neglected contacts:\n{data_str}\nPresent with a friendly nudge.",
            "birthdays":      f"Here are upcoming birthdays:\n{data_str}\nPresent warmly.",
            "error":          f"Error: {integration_data['data']}\nTell the user something went wrong.",
        }

        context   = context_prompts.get(data_type, f"Data:\n{data_str}")
        augmented = f"{message}\n\n[DATA TO USE IN YOUR RESPONSE]\n{context}"
    else:
        augmented = message

    anti_hallucination = (
        "\n\nCRITICAL RULE: You ONLY have access to data explicitly provided in [DATA TO USE IN YOUR RESPONSE] blocks. "
        "NEVER invent, estimate, or fabricate emails, events, tasks, counts, or names. "
        "If no data block is provided, do not pretend to have retrieved anything. "
        "If data is empty, say so honestly."
    )
    augmented_system = system_prompt + anti_hallucination
    full_prompt = build_ollama_prompt(history[:-1], augmented_system)
    full_prompt += f"User: {augmented}\nARIS:"

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": model, "prompt": full_prompt, "stream": False}
        )
        r.raise_for_status()
        return r.json()["response"]

# ─── CHAT ROUTE ────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    session_id = request.session_id

    # ── SAFETY CHECK ──────────────────────────────────────────────────────────
    safety_result = check_message_safety(request.message)

    if not safety_result.is_safe:
        print(f"[ARIS Safety] BLOCKED message in session '{session_id}'")
        return ChatResponse(
            response=safety_result.reason,
            model_used="safety-filter",
            session_id=session_id,
            turn_count=len(get_history(session_id)) // 2,
            memories_used=0,
            safety_status="blocked"
        )

    if safety_result.requires_confirmation and not request.confirmed:
        print(f"[ARIS Safety] Confirmation required in session '{session_id}'")
        return ChatResponse(
            response=(
                f"⚠️ This action requires confirmation.\n\n"
                f"{safety_result.reason}\n\n"
                f"To proceed, resend your message with `\"confirmed\": true`."
            ),
            model_used="safety-filter",
            session_id=session_id,
            turn_count=len(get_history(session_id)) // 2,
            memories_used=0,
            safety_status="needs_confirmation"
        )
    # ── END SAFETY CHECK ──────────────────────────────────────────────────────

    relevant_memories = await search_memories(request.message, n_results=3)
    system_prompt     = build_full_system_prompt(relevant_memories)

    add_to_memory(session_id, "user", request.message)
    history = get_history(session_id)

    # ── INTENT ROUTING ────────────────────────────────────────────────────────
    intent_result    = await route_message(request.message)
    intent           = intent_result["intent"]
    params           = intent_result["params"]
    print(f"[ARIS Router] Intent: '{intent}' | Params: {params}")

    integration_data = None
    if intent != "general_chat":
        integration_data = await execute_intent(intent, params)
        print(f"[ARIS Router] Executed: {intent} → {integration_data['type']}")
    # ── END INTENT ROUTING ───────────────────────────────────────────────────

    # ── MODEL SELECTION ───────────────────────────────────────────────────────
    # Route to the best local Ollama model based on intent
    # Gemini is emergency fallback only if all Ollama models fail

    WRITE_INTENTS = {
        "send_email",      # Needs good writing quality
        "search_emails",   # Needs summarization ability
    }

    REASON_INTENTS = {
        "create_event",    # Needs date/time parsing and reasoning
        "create_task",     # Needs parameter extraction
        "complete_task",   # Needs precision
    }

    if intent in WRITE_INTENTS:
        ollama_model = OLLAMA_WRITE_MODEL    # mistral
    elif intent in REASON_INTENTS:
        ollama_model = OLLAMA_REASON_MODEL   # gemma3:4b
    else:
        ollama_model = OLLAMA_CHAT_MODEL     # llama3.2 for chat + simple reads
    # ── END MODEL SELECTION ──────────────────────────────────────────────────

    try:
        try:
            reply      = await ask_ollama_with_context(
                message=request.message,
                history=history,
                system_prompt=system_prompt,
                integration_data=integration_data,
                model=ollama_model
            )
            model_used = f"ollama/{ollama_model}"
            print(f"[ARIS] Ollama({ollama_model}) | Session: '{session_id}' | Intent: {intent}")

        except Exception as ollama_error:
            print(f"[ARIS] Ollama failed: {ollama_error}. Falling back to Gemini...")
            reply      = await ask_gemini_with_context(
                message=request.message,
                history=history,
                system_prompt=system_prompt,
                integration_data=integration_data
            )
            model_used = PRIMARY_MODEL
            print(f"[ARIS] Gemini fallback | Session: '{session_id}' | Intent: {intent}")

    except Exception as gemini_error:
        conversation_store[session_id].pop()
        raise HTTPException(status_code=503,
            detail=f"All models failed. Error: {gemini_error}")

    add_to_memory(session_id, "model", reply, model_used)
    await extract_and_store_facts(request.message, reply, session_id)

    return ChatResponse(
        response=reply,
        model_used=model_used,
        session_id=session_id,
        turn_count=len(conversation_store[session_id]) // 2,
        memories_used=len(relevant_memories),
        safety_status="ok",
        intent=intent,
        integration_type=integration_data["type"] if integration_data else "none"
    )

# ─── MEMORY ROUTES ─────────────────────────────────────────────────────────────

@app.get("/memory/{session_id}")
async def get_memory(session_id: str):
    history = get_history(session_id)
    return {"session_id": session_id, "turn_count": len(history) // 2, "history": history}


@app.delete("/memory/{session_id}")
async def clear_memory(session_id: str, confirmed: bool = False):
    if not confirmed:
        return {
            "status": "needs_confirmation",
            "message": "Add ?confirmed=true to permanently clear this session."
        }
    if session_id in conversation_store:
        del conversation_store[session_id]
        return {"status": "cleared", "session_id": session_id}
    return {"status": "not_found", "session_id": session_id}


@app.get("/sessions")
async def list_sessions():
    return {"sessions": get_all_sessions()}


@app.get("/semantic-memory")
async def semantic_memory_stats():
    return get_memory_stats()

# ─── PROFILE ROUTES ────────────────────────────────────────────────────────────

@app.get("/profile")
async def get_profile():
    return load_profile()


@app.put("/profile")
async def update_profile(update: ProfileUpdateRequest):
    try:
        updated = update_profile_field(update.field, update.value)
        return {"status": "updated", "field": update.field, "profile": updated}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/profile/reset")
async def reset_profile():
    save_profile(DEFAULT_PROFILE)
    return {"status": "reset", "profile": DEFAULT_PROFILE}

# ─── SAFETY ROUTES ─────────────────────────────────────────────────────────────

@app.get("/safety")
async def safety_status_route():
    return get_safety_config()

# ─── GOOGLE AUTH ROUTES ────────────────────────────────────────────────────────

@app.get("/auth/google/login")
async def google_login():
    def do_auth():
        try:
            run_auth_flow()
            print("[Auth] ✓ Google account connected successfully!")
        except Exception as e:
            print(f"[Auth] ✗ Auth failed: {e}")

    thread = threading.Thread(target=do_auth, daemon=True)
    thread.start()
    return {
        "status": "started",
        "message": "A browser window should open. Complete login there, then check /auth/status"
    }


@app.get("/auth/status")
async def auth_status():
    authenticated = is_authenticated()
    return {
        "google_connected": authenticated,
        "message": "Google account connected ✓" if authenticated else "Not connected — visit /auth/google/login"
    }

# ─── GMAIL ROUTES ──────────────────────────────────────────────────────────────

@app.get("/integrations/gmail/inbox")
async def gmail_inbox(max_results: int = 10, unread_only: bool = False, category: str = "primary"):
    try:
        emails = read_inbox(max_results=max_results, unread_only=unread_only, category=category)
        return {"status": "ok", "category": category, "count": len(emails), "emails": emails}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/integrations/gmail/search")
async def gmail_search(q: str, max_results: int = 5):
    try:
        emails = search_emails(query=q, max_results=max_results)
        return {"status": "ok", "query": q, "count": len(emails), "emails": emails}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/integrations/gmail/message/{message_id}")
async def gmail_get_message(message_id: str):
    try:
        email = get_email(message_id)
        return {"status": "ok", "email": email}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str


@app.post("/integrations/gmail/send")
async def gmail_send(request: SendEmailRequest):
    try:
        result = send_email(request.to, request.subject, request.body)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/integrations/gmail/draft")
async def gmail_draft(request: SendEmailRequest):
    try:
        result = create_draft(request.to, request.subject, request.body)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── CALENDAR ROUTES ───────────────────────────────────────────────────────────

@app.get("/integrations/calendar/today")
async def calendar_today():
    try:
        events = get_today_events()
        return {"status": "ok", "count": len(events), "events": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/integrations/calendar/week")
async def calendar_week():
    try:
        events = get_week_events()
        return {"status": "ok", "count": len(events), "events": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CreateEventRequest(BaseModel):
    title: str
    start_time: str
    end_time: str
    description: str = ""
    location: str = ""
    attendees: list[str] = []
    add_meet: bool = False


@app.post("/integrations/calendar/create")
async def calendar_create(request: CreateEventRequest):
    try:
        result = create_event(
            title=request.title,
            start_time=request.start_time,
            end_time=request.end_time,
            description=request.description,
            location=request.location,
            attendees=request.attendees,
            add_meet=request.add_meet
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/integrations/calendar/{event_id}")
async def calendar_delete(event_id: str):
    try:
        return delete_event(event_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/integrations/calendar/conflicts")
async def calendar_conflicts(start_time: str, end_time: str):
    try:
        return check_conflicts(start_time, end_time)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── TODOIST ROUTES ────────────────────────────────────────────────────────────

@app.get("/integrations/tasks")
async def tasks_get_all(filter: str = None):
    try:
        tasks = get_all_tasks(filter_str=filter)
        return {"status": "ok", "count": len(tasks), "tasks": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/integrations/tasks/today")
async def tasks_today():
    try:
        tasks = get_today_tasks()
        return {"status": "ok", "count": len(tasks), "tasks": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/integrations/tasks/overdue")
async def tasks_overdue():
    try:
        tasks = get_overdue_tasks()
        return {"status": "ok", "count": len(tasks), "tasks": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/integrations/tasks/projects")
async def tasks_projects():
    try:
        projects = get_projects()
        return {"status": "ok", "projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CreateTaskRequest(BaseModel):
    content: str
    description: str = ""
    due_string: str = None
    priority: int = 1
    labels: list[str] = []
    project_id: str = None


@app.post("/integrations/tasks")
async def tasks_create(request: CreateTaskRequest):
    try:
        result = create_task(
            content=request.content,
            description=request.description,
            due_string=request.due_string,
            priority=request.priority,
            labels=request.labels,
            project_id=request.project_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdateTaskRequest(BaseModel):
    content: str = None
    description: str = None
    due_string: str = None
    priority: int = None


@app.put("/integrations/tasks/{task_id}")
async def tasks_update(task_id: str, request: UpdateTaskRequest):
    try:
        result = update_task(
            task_id=task_id,
            content=request.content,
            description=request.description,
            due_string=request.due_string,
            priority=request.priority
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/integrations/tasks/{task_id}/complete")
async def tasks_complete(task_id: str):
    try:
        return complete_task(task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/integrations/tasks/{task_id}")
async def tasks_delete(task_id: str):
    try:
        return delete_task(task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── RELATIONSHIP MEMORY ROUTES ────────────────────────────────────────────────

class SavePersonRequest(BaseModel):
    name: str
    relationship: str
    birthday: str = None
    notes: str = ""
    preferences: str = ""
    last_contact: str = None
    contact_info: str = ""


@app.post("/relationships")
async def relationships_save(request: SavePersonRequest):
    try:
        result = save_person(
            name=request.name,
            relationship=request.relationship,
            birthday=request.birthday,
            notes=request.notes,
            preferences=request.preferences,
            last_contact=request.last_contact,
            contact_info=request.contact_info
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/relationships")
async def relationships_get_all():
    try:
        people = get_all_people()
        return {"status": "ok", "count": len(people), "people": people}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/relationships/search")
async def relationships_search(q: str):
    try:
        results = search_people(query=q)
        return {"status": "ok", "query": q, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/relationships/neglected")
async def relationships_neglected(days: int = 14):
    try:
        people = get_neglected_contacts(days_threshold=days)
        return {"status": "ok", "threshold_days": days, "count": len(people), "people": people}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/relationships/birthdays")
async def relationships_birthdays(days_ahead: int = 30):
    try:
        birthdays = get_upcoming_birthdays(days_ahead=days_ahead)
        return {"status": "ok", "days_ahead": days_ahead, "count": len(birthdays), "birthdays": birthdays}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/relationships/{name}")
async def relationships_get_one(name: str):
    try:
        person = get_person(name)
        if not person:
            raise HTTPException(status_code=404, detail=f"Person '{name}' not found")
        return {"status": "ok", "person": person}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/relationships/{name}/contact")
async def relationships_update_contact(name: str, notes: str = ""):
    try:
        result = update_last_contact(name=name, notes=notes)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/relationships/{name}")
async def relationships_delete(name: str):
    try:
        return delete_person(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── DAILY BRIEFING ROUTE ──────────────────────────────────────────────────────

@app.get("/briefing")
async def daily_briefing():
    """
    Compile a full morning briefing for Shubh:
    - Today's calendar events
    - Unread primary emails
    - Tasks due today + overdue
    - Neglected contacts
    - Upcoming birthdays
    - Gemini-generated summary paragraph
    """
    try:
        # ── Gather all data in parallel ───────────────────────────────────────
        import asyncio
        from datetime import datetime

        def fetch_calendar():
            try:
                return get_today_events()
            except Exception as e:
                print(f"[Briefing] Calendar error: {e}")
                return []

        def fetch_emails():
            try:
                return read_inbox(max_results=5, unread_only=False, category="primary")
            except Exception as e:
                print(f"[Briefing] Gmail error: {e}")
                return []

        def fetch_tasks():
            try:
                return get_task_summary()
            except Exception as e:
                print(f"[Briefing] Tasks error: {e}")
                return {"today_tasks": [], "overdue_tasks": [], "due_today": 0, "overdue": 0}

        def fetch_neglected():
            try:
                return get_neglected_contacts(days_threshold=14)
            except Exception as e:
                print(f"[Briefing] Relationships error: {e}")
                return []

        def fetch_birthdays():
            try:
                return get_upcoming_birthdays(days_ahead=7)
            except Exception as e:
                print(f"[Briefing] Birthdays error: {e}")
                return []

        # Run all fetches
        calendar_events = fetch_calendar()
        emails          = fetch_emails()
        task_summary    = fetch_tasks()
        neglected       = fetch_neglected()
        birthdays       = fetch_birthdays()

        # ── Build briefing data ───────────────────────────────────────────────
        now         = datetime.now()
        date_str    = now.strftime("%A, %B %d, %Y")
        hour        = now.hour
        greeting    = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
        profile     = load_profile()
        name        = profile.get("preferred_name", profile.get("name", "Shubh"))

        briefing_data = {
            "date":             date_str,
            "calendar_events":  calendar_events,
            "emails":           emails,
            "tasks_today":      task_summary.get("today_tasks", []),
            "tasks_overdue":    task_summary.get("overdue_tasks", []),
            "neglected":        neglected,
            "birthdays":        birthdays,
        }

        # ── Ask Gemini to write the summary paragraph ─────────────────────────
        briefing_json = json.dumps(briefing_data, indent=2, default=str)

        summary_prompt = f"""
You are ARIS, a personal AI assistant. Generate a warm, concise morning briefing for {name}.

Today is {date_str}. Here is all the data:

{briefing_json}

Write a friendly {greeting} message that:
1. Greets {name} warmly
2. Summarizes today's calendar (or says it's clear)
3. Highlights important emails if any
4. Mentions tasks due today and any overdue ones
5. Gently nudges about neglected contacts if any
6. Mentions upcoming birthdays in the next 7 days if any
7. Ends with a motivating one-liner

Keep it conversational, warm, and under 200 words. Do not use bullet points — write it as natural flowing paragraphs.
"""

        summary_response = gemini_client.models.generate_content(
            model=PRIMARY_MODEL,
            contents=[types.Content(
                role="user",
                parts=[types.Part(text=summary_prompt)]
            )],
            config=types.GenerateContentConfig(
                temperature=0.8,
                max_output_tokens=512,
            )
        )
        summary = summary_response.text

        # ── Return full briefing ──────────────────────────────────────────────
        return {
            "status":          "ok",
            "date":            date_str,
            "greeting":        greeting,
            "summary":         summary,
            "calendar_count":  len(calendar_events),
            "calendar_events": calendar_events,
            "email_count":     len(emails),
            "emails":          emails,
            "tasks_today":     task_summary.get("today_tasks", []),
            "tasks_overdue":   task_summary.get("overdue_tasks", []),
            "due_today_count": task_summary.get("due_today", 0),
            "overdue_count":   task_summary.get("overdue", 0),
            "neglected":       neglected,
            "birthdays":       birthdays,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Briefing failed: {str(e)}")

# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ARIS Backend"}

# ─── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)