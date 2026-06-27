"""
ARIS - Autonomous Reasoning & Intelligence System
Backend Main Entry Point
Phase 4 - Device & Computer Control
"""

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Any, Optional
import uvicorn
import os
import sys
import httpx
import threading
import json
from google import genai
from google.genai import types
import asyncio
import whisper as _whisper
import tempfile
import shutil

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    check_control_action,
    log_control_action,
    get_audit_log,
    get_safety_config,
    TrustLevel,
    TRUST_LEVEL
)
from auth.google_auth import (
    is_authenticated,
    auth_router
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
from voice.pipeline import start_pipeline, stop_pipeline, get_pipeline_status
from voice.tts import speak_async, get_tts_status
from vision.ocr import ocr_screen, ocr_camera, ocr_file
from vision.screen import analyze_screen, describe_screen

# ── Phase 4: PC Control ───────────────────────────────────────────────────────
from control.pc import (
    move_mouse, click, double_click, right_click, scroll,
    type_text, press_key, hotkey, open_app, close_window,
    minimize_window, maximize_window, focus_window,
    list_open_windows, take_screenshot, clipboard_read, clipboard_write
)
from control.files import (
    list_directory, create_file, create_folder,
    read_file, write_file, rename, move, copy,
    delete, search_files, open_file, open_in_explorer, get_file_info
)
from control.system import (
    get_stats, get_cpu, get_ram, get_disk,
    get_battery, list_processes, kill_process, get_network
)
from fastapi.responses import RedirectResponse, StreamingResponse
from control.browser import (
    open_url, search_google, click_element,
    fill_field, get_page_text, browser_screenshot,
    get_page_info, close_browser
)
from control.notify import send_notification, get_notification_history, clear_notification_history

load_dotenv()

# ─── CONFIG ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
PRIMARY_MODEL   = os.getenv("PRIMARY_MODEL", "gemini-2.5-flash")
FALLBACK_MODEL  = os.getenv("FALLBACK_MODEL", "llama3.2")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

OLLAMA_CHAT_MODEL   = os.getenv("OLLAMA_CHAT_MODEL",   "llama3.2")
OLLAMA_WRITE_MODEL  = os.getenv("OLLAMA_WRITE_MODEL",  "mistral")
OLLAMA_REASON_MODEL = os.getenv("OLLAMA_REASON_MODEL", "gemma3:4b")

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

# ─── FASTAPI APP ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="ARIS - Autonomous Reasoning & Intelligence System",
    description="Your personal AI assistant backend",
    version="4.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

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

# ─── PC CONTROL REQUEST MODELS ─────────────────────────────────────────────────

class MouseMoveRequest(BaseModel):
    x: int
    y: int
    duration: float = 0.3

class ClickRequest(BaseModel):
    x: Optional[int] = None
    y: Optional[int] = None
    button: str = "left"
    clicks: int = 1

class ScrollRequest(BaseModel):
    direction: str = "down"
    amount: int = 3

class TypeRequest(BaseModel):
    text: str
    interval: float = 0.05

class KeyRequest(BaseModel):
    key: str

class HotkeyRequest(BaseModel):
    keys: list[str]  # e.g. ["ctrl", "c"]

class AppRequest(BaseModel):
    app: str

class WindowRequest(BaseModel):
    title: str

class ClipboardWriteRequest(BaseModel):
    text: str

class ScreenshotRequest(BaseModel):
    filename: Optional[str] = None

# ─── REQUEST MODELS (same as before) ─────────────────────────────────────────
 
class OpenUrlRequest(BaseModel):
    url: str
    wait_for: str = "load"
 
class SearchRequest(BaseModel):
    query: str
    max_results: int = 5
 
class ClickElementRequest(BaseModel):
    selector: Optional[str] = None
    text: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
 
class FillFieldRequest(BaseModel):
    selector: str
    value: str
    press_enter: bool = False
 
class PageTextRequest(BaseModel):
    max_chars: int = 3000

class NotifyRequest(BaseModel):
    title: str
    message: str
    timeout: int = 5
    app_name: str = "ARIS"

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
            "pc_action"          : f"PC control action result:\n{data_str}\nConfirm to the user what was done in a friendly way.",
            "system_stats"       : f"System health data:\n{data_str}\nPresent the key stats clearly — CPU %, RAM %, battery, disk. Flag anything high.",
            "files"              : f"File operation result:\n{data_str}\nConfirm what was done or list the files clearly.",
            "browser"            : f"Browser action result:\n{data_str}\nSummarize what was found or confirm the action.",
            "needs_confirmation" : f"This action needs user confirmation:\n{data_str}\nAsk the user to confirm before proceeding.",
        }
        context   = context_prompts.get(data_type, f"Integration data:\n{data_str}")
        augmented = f"{message}\n\n[INTEGRATION RESULT — use this to answer]\n{context}"
    else:
        augmented = message

    contents = build_gemini_contents(history[:-1])
    contents.append(types.Content(role="user", parts=[types.Part(text=augmented)]))
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
            "pc_action"          : f"PC control action result:\n{data_str}\nConfirm to the user what was done in a friendly way.",
            "system_stats"       : f"System health data:\n{data_str}\nPresent the key stats clearly — CPU %, RAM %, battery, disk. Flag anything high.",
            "files"              : f"File operation result:\n{data_str}\nConfirm what was done or list the files clearly.",
            "browser"            : f"Browser action result:\n{data_str}\nSummarize what was found or confirm the action.",
            "needs_confirmation" : f"This action needs user confirmation:\n{data_str}\nAsk the user to confirm before proceeding.",
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
    # For data intents — force Ollama to use the provided data
    if integration_data and integration_data.get("type") not in ("general_chat", "none", None):
        data_instruction = (
            "CRITICAL INSTRUCTION: Real live data has been fetched and provided to you "
            "in the [DATA TO USE IN YOUR RESPONSE] block below. "
            "You MUST read and use ONLY this data to answer. "
            "NEVER say you don't have access to emails, calendar, tasks, files or system info — "
            "the actual data is in the prompt. Present it clearly and helpfully.\n\n"
        )
        augmented_system = data_instruction + system_prompt + anti_hallucination
    else:
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

    relevant_memories = await search_memories(request.message, n_results=3)
    system_prompt     = build_full_system_prompt(relevant_memories)

    add_to_memory(session_id, "user", request.message)
    history = get_history(session_id)

    intent_result    = await route_message(request.message)
    intent           = intent_result["intent"]
    params           = intent_result["params"]
    print(f"[ARIS Router] Intent: '{intent}' | Params: {params}")

    integration_data = None
    if intent != "general_chat":
        integration_data = await execute_intent(intent, params)
        print(f"[ARIS Router] Executed: {intent} → {integration_data['type']}")

    # ── MODEL SELECTION ───────────────────────────────────────────────────────────

    WRITE_INTENTS  = {"send_email", "search_emails"}
    REASON_INTENTS = {"create_event", "create_task", "complete_task"}
    DATA_INTENTS   = {
        "read_inbox", "get_today_events", "get_week_events",
        "get_tasks", "get_system_stats", "list_processes",
        "list_files", "read_file", "search_files",
        "browser_search", "get_person", "get_neglected_contacts",
        "get_upcoming_birthdays", "clipboard_read",
        "open_application", "take_screenshot", "pc_action",
    }

    # Complex tasks that need Gemini's reasoning power
    # Detected by checking if message looks like a knowledge/writing request
    def _needs_gemini(message: str, intent: str) -> bool:
        if intent != "general_chat":
            return False  # Integration intents handled locally
        msg = message.lower()
        triggers = [
            "what is", "what are", "explain", "how does", "how do",
            "write a", "write an", "generate", "create a story",
            "passage", "essay", "paragraph", "summarize", "summary",
            "difference between", "compare", "analyze", "analyse",
            "why is", "why does", "tell me about", "describe",
            "help me understand", "can you explain", "elaborate",
            "pros and cons", "advantages", "disadvantages",
            "definition of", "define", "meaning of",
        ]
        return any(t in msg for t in triggers)

    if intent in WRITE_INTENTS:
        ollama_model = OLLAMA_WRITE_MODEL    # mistral
    elif intent in REASON_INTENTS:
        ollama_model = OLLAMA_REASON_MODEL   # gemma3:4b
    elif intent in DATA_INTENTS:
        ollama_model = OLLAMA_REASON_MODEL   # gemma3:4b — reads data well
    else:
        ollama_model = OLLAMA_CHAT_MODEL     # llama3.2 — fast for simple chat

    # ── MODEL CALL ────────────────────────────────────────────────────────────────

    use_gemini = _needs_gemini(request.message, intent)

    try:
        if use_gemini:
            # Complex knowledge/writing tasks → Gemini
            try:
                reply      = await ask_gemini_with_context(
                    message=request.message,
                    history=history,
                    system_prompt=system_prompt,
                    integration_data=integration_data
                )
                model_used = PRIMARY_MODEL
                print(f"[ARIS] Gemini (complex) | Session: '{session_id}' | Intent: {intent}")

            except Exception as gemini_error:
                print(f"[ARIS] Gemini failed: {gemini_error}. Falling back to Ollama...")
                reply      = await ask_ollama_with_context(
                    message=request.message,
                    history=history,
                    system_prompt=system_prompt,
                    integration_data=integration_data,
                    model=ollama_model
                )
                model_used = f"ollama/{ollama_model}"

        else:
            # Everything else → Ollama (local, free, private)
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
        return {"status": "needs_confirmation", "message": "Add ?confirmed=true to permanently clear this session."}
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

# ─── AUTH STATUS (legacy) ──────────────────────────────────────────────────────

@app.get("/auth/status")
async def auth_status():
    authenticated = is_authenticated()
    return {
        "google_connected": authenticated,
        "message": "Google account connected ✓" if authenticated else "Not connected — click Connect Google in the UI"
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
        return send_email(request.to, request.subject, request.body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/integrations/gmail/draft")
async def gmail_draft(request: SendEmailRequest):
    try:
        return create_draft(request.to, request.subject, request.body)
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
        return create_event(
            title=request.title,
            start_time=request.start_time,
            end_time=request.end_time,
            description=request.description,
            location=request.location,
            attendees=request.attendees,
            add_meet=request.add_meet
        )
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
        return create_task(
            content=request.content,
            description=request.description,
            due_string=request.due_string,
            priority=request.priority,
            labels=request.labels,
            project_id=request.project_id
        )
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
        return update_task(
            task_id=task_id,
            content=request.content,
            description=request.description,
            due_string=request.due_string,
            priority=request.priority
        )
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

# ─── RELATIONSHIP ROUTES ───────────────────────────────────────────────────────

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
        return save_person(
            name=request.name,
            relationship=request.relationship,
            birthday=request.birthday,
            notes=request.notes,
            preferences=request.preferences,
            last_contact=request.last_contact,
            contact_info=request.contact_info
        )
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
        return update_last_contact(name=name, notes=notes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/relationships/{name}")
async def relationships_delete(name: str):
    try:
        return delete_person(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── DAILY BRIEFING ────────────────────────────────────────────────────────────

@app.get("/briefing")
async def daily_briefing():
    try:
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

        calendar_events = fetch_calendar()
        emails          = fetch_emails()
        task_summary    = fetch_tasks()
        neglected       = fetch_neglected()
        birthdays       = fetch_birthdays()

        now      = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        hour     = now.hour
        greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
        profile  = load_profile()
        name     = profile.get("preferred_name", profile.get("name", "Shubh"))

        briefing_data = {
            "date":            date_str,
            "calendar_events": calendar_events,
            "emails":          emails,
            "tasks_today":     task_summary.get("today_tasks", []),
            "tasks_overdue":   task_summary.get("overdue_tasks", []),
            "neglected":       neglected,
            "birthdays":       birthdays,
        }

        briefing_json  = json.dumps(briefing_data, indent=2, default=str)
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
            contents=[types.Content(role="user", parts=[types.Part(text=summary_prompt)])],
            config=types.GenerateContentConfig(temperature=0.8, max_output_tokens=512)
        )
        summary = summary_response.text

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

# ─── VOICE ROUTES ──────────────────────────────────────────────────────────────

_whisper_model = _whisper.load_model("base")
print("✅ Whisper STT model loaded")


@app.post("/voice/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    suffix = os.path.splitext(audio.filename)[-1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(audio.file, tmp)
        tmp_path = tmp.name
    try:
        result = _whisper_model.transcribe(tmp_path, language="en", fp16=False, verbose=False)
        return {"text": result["text"].strip(), "language": result.get("language", "en")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    finally:
        os.unlink(tmp_path)


@app.post("/voice/speak")
async def voice_speak(request: Request):
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")
    speak_async(text)
    return {"status": "speaking", "text": text, "length": len(text)}


@app.get("/voice/tts-status")
async def tts_status():
    return get_tts_status()


@app.post("/voice/start")
async def voice_start():
    return start_pipeline()


@app.post("/voice/stop")
async def voice_stop():
    return stop_pipeline()


@app.get("/voice/status")
async def voice_status():
    return get_pipeline_status()

# ─── VISION ROUTES ─────────────────────────────────────────────────────────────

@app.get("/vision/screen")
async def vision_screen(prompt: str = None, monitor: int = 1):
    try:
        return analyze_screen(prompt=prompt, monitor_index=monitor)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/vision/camera")
async def vision_camera(prompt: str = None, camera: int = 0):
    try:
        from vision.camera import analyze_camera
        return analyze_camera(prompt=prompt, camera_index=camera)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/vision/ocr")
async def vision_ocr(source: str = "screen", mode: str = "extract", question: str = ""):
    try:
        if source == "camera":
            return ocr_camera(mode=mode, question=question)
        return ocr_screen(mode=mode, question=question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── PC CONTROL ROUTES ─────────────────────────────────────────────────────────

@app.post("/control/pc/mouse/move")
async def pc_mouse_move(req: MouseMoveRequest):
    try:
        return move_mouse(req.x, req.y, req.duration)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/mouse/click")
async def pc_click(req: ClickRequest):
    try:
        return click(req.x, req.y, req.button, req.clicks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/mouse/double-click")
async def pc_double_click(req: ClickRequest):
    try:
        return double_click(req.x, req.y)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/mouse/right-click")
async def pc_right_click(req: ClickRequest):
    try:
        return right_click(req.x, req.y)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/mouse/scroll")
async def pc_scroll(req: ScrollRequest):
    try:
        return scroll(req.direction, req.amount)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/keyboard/type")
async def pc_type(req: TypeRequest):
    try:
        return type_text(req.text, req.interval)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/keyboard/key")
async def pc_key(req: KeyRequest):
    try:
        return press_key(req.key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/keyboard/hotkey")
async def pc_hotkey(req: HotkeyRequest):
    try:
        return hotkey(*req.keys)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/app/open")
async def pc_open_app(req: AppRequest):
    try:
        return open_app(req.app)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/window/close")
async def pc_close_window(req: WindowRequest):
    try:
        return close_window(req.title)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/window/minimize")
async def pc_minimize(req: WindowRequest):
    try:
        return minimize_window(req.title)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/window/maximize")
async def pc_maximize(req: WindowRequest):
    try:
        return maximize_window(req.title)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/window/focus")
async def pc_focus(req: WindowRequest):
    try:
        return focus_window(req.title)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/control/pc/window/list")
async def pc_list_windows():
    try:
        return list_open_windows()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/screenshot")
async def pc_screenshot(req: ScreenshotRequest):
    try:
        return take_screenshot(req.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/control/pc/clipboard")
async def pc_clipboard_read():
    try:
        return clipboard_read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/clipboard")
async def pc_clipboard_write(req: ClipboardWriteRequest):
    try:
        return clipboard_write(req.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── ADD REQUEST MODELS (after PC control models) ─────────────────────────────

class ListDirRequest(BaseModel):
    path: str = "~"
    show_hidden: bool = False

class CreateFileRequest(BaseModel):
    path: str
    content: str = ""

class CreateFolderRequest(BaseModel):
    path: str

class ReadFileRequest(BaseModel):
    path: str
    max_chars: int = 5000

class WriteFileRequest(BaseModel):
    path: str
    content: str
    append: bool = False

class RenameRequest(BaseModel):
    path: str
    new_name: str

class MoveRequest(BaseModel):
    src: str
    dst: str

class CopyRequest(BaseModel):
    src: str
    dst: str

class DeleteRequest(BaseModel):
    path: str
    confirmed: bool = False

class SearchFilesRequest(BaseModel):
    query: str
    search_path: str = "~"
    extension: Optional[str] = None
    max_results: int = 50

class OpenFileRequest(BaseModel):
    path: str

class FileInfoRequest(BaseModel):
    path: str

# ─── ADD ROUTES (after PC control routes, before health check) ─────────────────

# ─── FILE & FOLDER MANAGEMENT ROUTES ──────────────────────────────────────────

@app.post("/control/files/list")
async def files_list(req: ListDirRequest):
    try:
        return list_directory(req.path, req.show_hidden)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/files/create")
async def files_create(req: CreateFileRequest):
    try:
        return create_file(req.path, req.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/files/folder")
async def files_create_folder(req: CreateFolderRequest):
    try:
        return create_folder(req.path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/files/read")
async def files_read(req: ReadFileRequest):
    try:
        return read_file(req.path, req.max_chars)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/files/write")
async def files_write(req: WriteFileRequest):
    try:
        return write_file(req.path, req.content, req.append)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/files/rename")
async def files_rename(req: RenameRequest):
    try:
        return rename(req.path, req.new_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/files/move")
async def files_move(req: MoveRequest):
    try:
        return move(req.src, req.dst)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/files/copy")
async def files_copy(req: CopyRequest):
    try:
        return copy(req.src, req.dst)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/files/delete")
async def files_delete(req: DeleteRequest):
    """Delete requires safety check + confirmation."""
    try:
        # Safety check first
        safety = check_control_action(
            action    = "delete_file",
            params    = {"path": req.path},
            confirmed = req.confirmed
        )
        if safety.requires_confirmation:
            return {
                "status" : "needs_confirmation",
                "message": safety.reason,
                "path"   : req.path
            }
        # Log and execute
        result = delete(req.path, confirmed=req.confirmed)
        log_control_action("delete_file", req.path, str(result), confirmed=True)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/files/search")
async def files_search(req: SearchFilesRequest):
    try:
        return search_files(req.query, req.search_path, req.extension, req.max_results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/files/open")
async def files_open(req: OpenFileRequest):
    try:
        return open_file(req.path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/files/explorer")
async def files_explorer(req: OpenFileRequest):
    try:
        return open_in_explorer(req.path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/files/info")
async def files_info(req: FileInfoRequest):
    try:
        return get_file_info(req.path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ─── ADD REQUEST MODELS ───────────────────────────────────────────────────────
 
class ProcessListRequest(BaseModel):
    sort_by: str = "cpu"
    limit: int = 20
 
class KillProcessRequest(BaseModel):
    name: Optional[str] = None
    pid: Optional[int] = None
    confirmed: bool = False
 
# ─── ADD ROUTES (after file routes, before health check) ──────────────────────
 
# ─── SYSTEM MONITORING ROUTES ─────────────────────────────────────────────────
 
@app.get("/control/system")
async def system_stats():
    """Full system snapshot — CPU, RAM, disk, battery, network."""
    try:
        return get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.get("/control/system/cpu")
async def system_cpu():
    try:
        return get_cpu()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.get("/control/system/ram")
async def system_ram():
    try:
        return get_ram()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.get("/control/system/disk")
async def system_disk():
    try:
        return get_disk()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.get("/control/system/battery")
async def system_battery():
    try:
        return get_battery()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.get("/control/system/network")
async def system_network():
    try:
        return get_network()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.post("/control/system/processes")
async def system_processes(req: ProcessListRequest):
    try:
        return list_processes(req.sort_by, req.limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.post("/control/system/kill")
async def system_kill(req: KillProcessRequest):
    """Kill process requires safety check + confirmation."""
    try:
        safety = check_control_action(
            action    = "kill_process",
            params    = {"name": req.name, "pid": req.pid},
            confirmed = req.confirmed
        )
        if safety.requires_confirmation:
            return {
                "status" : "needs_confirmation",
                "message": safety.reason,
                "target" : req.name or req.pid
            }
        result = kill_process(req.name, req.pid, confirmed=req.confirmed)
        log_control_action("kill_process", str(req.name or req.pid), str(result), confirmed=True)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
# ─── BROWSER AUTOMATION ROUTES ────────────────────────────────────────────────
 
@app.post("/control/browser/open")
async def browser_open(req: OpenUrlRequest):
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: open_url(req.url, req.wait_for))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.post("/control/browser/search")
async def browser_search(req: SearchRequest):
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: search_google(req.query, req.max_results))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.post("/control/browser/click")
async def browser_click(req: ClickElementRequest):
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: click_element(req.selector, req.text, req.x, req.y))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.post("/control/browser/fill")
async def browser_fill(req: FillFieldRequest):
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fill_field(req.selector, req.value, req.press_enter))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.post("/control/browser/text")
async def browser_text(req: PageTextRequest):
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: get_page_text(req.max_chars))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.post("/control/browser/screenshot")
async def browser_screenshot_route():
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, browser_screenshot)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.get("/control/browser/info")
async def browser_info():
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, get_page_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.post("/control/browser/close")
async def browser_close():
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, close_browser)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
  
# ─── NOTIFICATION ROUTES ──────────────────────────────────────────────────────
 
@app.post("/control/notify")
async def notify(req: NotifyRequest):
    try:
        return send_notification(req.title, req.message, req.timeout, req.app_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.get("/control/notify/history")
async def notify_history():
    try:
        return get_notification_history()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.delete("/control/notify/history")
async def notify_clear():
    try:
        return clear_notification_history()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
# ─── SSE LIVE SYSTEM STREAM ───────────────────────────────────────────────────
# Streams system stats every 2 seconds — frontend polls this for live gauges
 
@app.get("/control/system/stream")
async def system_stream():
    """
    Server-Sent Events stream of live system stats.
    Frontend connects once and receives updates every 2 seconds.
    Usage: const es = new EventSource('http://localhost:8000/control/system/stream')
    """
    async def event_generator():
        while True:
            try:
                stats = get_stats()
                import json
                data  = json.dumps(stats)
                yield f"data: {data}\n\n"
                await asyncio.sleep(2)
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                await asyncio.sleep(2)
 
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control"              : "no-cache",
            "X-Accel-Buffering"          : "no",
            "Access-Control-Allow-Origin": "*",
        }
    )
# ─── AUDIT LOG ROUTES ─────────────────────────────────────────────────────────

@app.get("/control/audit")
async def audit_log(limit: int = 50):
    """Return recent control action audit log."""
    try:
        return {
            "status" : "ok",
            "count"  : limit,
            "entries": get_audit_log(limit)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ARIS Backend", "phase": "4"}

@app.get("/control/system/ollama")
async def ollama_status():
    """Check Ollama + return active Gemini model info."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            ollama_connected = True
    except Exception:
        models = []
        ollama_connected = False

    return {
        "ollama": {
            "connected": ollama_connected,
            "models"   : models,
            "count"    : len(models)
        },
        "gemini": {
            "connected": True,  # if backend started, Gemini key is loaded
            "model"    : PRIMARY_MODEL,
            "chat_model"  : OLLAMA_CHAT_MODEL,
            "write_model" : OLLAMA_WRITE_MODEL,
            "reason_model": OLLAMA_REASON_MODEL,
        }
    }

# ─── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)