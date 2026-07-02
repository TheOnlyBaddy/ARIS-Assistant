"""
ARIS - Autonomous Reasoning & Intelligence System
Backend Main Entry Point
Phase 4 - Device & Computer Control
"""

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import os
# Robustly find .env from either backend or root
_base_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_base_dir, ".env")
if not os.path.exists(_env_path):
    _env_path = os.path.join(os.path.dirname(_base_dir), ".env")
load_dotenv(_env_path)

from typing import Any, Optional
import uvicorn
import time
import sys
import subprocess
import httpx
import threading
import json
from google import genai
from google.genai import types
import asyncio
from contextlib import asynccontextmanager
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
from control.pc.software import (
    move_mouse, click, double_click, right_click, scroll,
    type_text, press_key, hotkey, open_app, close_window,
    minimize_window, maximize_window, focus_window,
    list_open_windows, take_screenshot, clipboard_read, clipboard_write,
    list_directory, create_file, create_folder,
    read_file, write_file, rename, move, copy,
    delete, search_files, open_file, open_in_explorer, get_file_info,
    open_url, search_google, click_element,
    fill_field, get_page_text, browser_screenshot,
    get_page_info, close_browser,
    send_notification, get_notification_history, clear_notification_history
)
from control.pc.hardware import (
    get_stats, get_cpu, get_ram, get_disk,
    get_battery, list_processes, kill_process, get_network,
    media_control, set_brightness, lock_pc, sleep_pc,
    shutdown_pc, restart_pc, cancel_shutdown, get_network_diagnostics
)

# ─── CONFIG ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
PRIMARY_MODEL   = os.getenv("PRIMARY_MODEL", "gemini-2.5-flash")
FALLBACK_MODEL  = os.getenv("FALLBACK_MODEL", "llama3.2")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

OLLAMA_CHAT_MODEL   = os.getenv("OLLAMA_CHAT_MODEL",   "llama3.2")
OLLAMA_WRITE_MODEL  = os.getenv("OLLAMA_WRITE_MODEL",  "mistral")
OLLAMA_REASON_MODEL = os.getenv("OLLAMA_REASON_MODEL", "gemma3:4b")

async def get_best_ollama_model(target_model: str) -> str:
    """
    Checks if a fine-tuned version of the model exists in Ollama.
    If yes, returns the fine-tuned version. If not, falls back to the base model.
    """
    mapping = {
        OLLAMA_CHAT_MODEL: "aris-llama",
        OLLAMA_WRITE_MODEL: "aris-mistral",
        OLLAMA_REASON_MODEL: "aris-gemma"
    }
    
    fine_tuned = mapping.get(target_model)
    if not fine_tuned:
        return target_model
        
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if r.status_code == 200:
                # Extract simple names like "aris-llama" and full names like "aris-llama:latest"
                available_simple = [m["name"].split(":")[0] for m in r.json().get("models", [])]
                available_full = [m["name"] for m in r.json().get("models", [])]
                if fine_tuned in available_simple or f"{fine_tuned}:latest" in available_full:
                    return fine_tuned
    except Exception as e:
        print(f"[ARIS Routing] Ollama tag check failed: {e}. Defaulting to base model.")
        
    return target_model

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

ARIS_BASE_PROMPT = (
    "You are ARIS (Autonomous Reasoning & Intelligence System), "
    "a highly capable, friendly, and thoughtful personal AI assistant. "
    "You are helpful, concise, and always honest. "
    "Refer to yourself as ARIS, never as Gemini or any other AI. "
    "You have short-term conversation memory, long-term database memory, "
    "and semantic memory of important facts. "
    "Always adapt your tone and style to match the user profile below. "
    "CRITICAL RULE: Never address the user by their actual name (such as Shubh, User, etc.). "
    "Instead, always address them as 'boss' or 'sir'."
)

# ─── IN-MEMORY STORE ───────────────────────────────────────────────────────────

conversation_store: dict[str, list[dict]] = {}
gemini_cooldown_until: float = 0.0

# ─── STARTUP ───────────────────────────────────────────────────────────────────

def ensure_ollama_running():
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        # Ping Ollama base URL
        r = httpx.get(ollama_url, timeout=1.0)
        if r.status_code == 200:
            print("[ARIS Startup] Ollama is running.")
            return
    except Exception:
        pass

    # Ollama is not responding. Let's try to start it.
    print("[ARIS Startup] Ollama is not running. Checking if 'ollama' is installed...")
    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        # Check standard Windows installation directory as fallback
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            win_path = os.path.join(local_appdata, "Programs", "Ollama", "ollama.exe")
            if os.path.exists(win_path):
                ollama_bin = win_path

    if ollama_bin:
        print(f"[ARIS Startup] Found Ollama binary. Auto-launching 'ollama serve' in background...")
        try:
            subprocess.Popen(
                "ollama serve",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print("[ARIS Startup] Ollama process spawned successfully.")
        except Exception as e:
            print(f"[ARIS Startup] Failed to auto-launch Ollama: {e}")
    else:
        print("[ARIS Startup] WARNING: 'ollama' command not found in system PATH. Please launch Ollama manually.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[ARIS] Starting up...")
    ensure_ollama_running()
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
    
    # Start background scheduler
    from agents.scheduler import start_scheduler, stop_scheduler
    start_scheduler()

    try:
        yield
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        print("[ARIS] Shutting down...")
        try:
            stop_scheduler()
        except Exception:
            pass

# ─── FASTAPI APP ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="ARIS - Autonomous Reasoning & Intelligence System",
    description="Your personal AI assistant backend",
    version="4.0.0",
    lifespan=lifespan
)

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from fastapi import Security, Depends
from fastapi.security.api_key import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    expected_key = os.getenv("API_KEY", "your_secure_token")
    if not api_key or api_key != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid X-API-Key")



app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_request_latency(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000.0
        session_id = request.headers.get("X-Session-ID", "system")
        
        # Avoid cluttering logs with continuous polling requests
        if request.url.path not in ("/finetune/status", "/control/system/ollama", "/admin/stats"):
            from agents.monitoring import log_structured
            log_structured(
                level="INFO",
                message=f"HTTP {request.method} {request.url.path} -> {response.status_code}",
                session_id=session_id,
                execution_time_ms=duration_ms
            )
        return response
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000.0
        if request.url.path not in ("/finetune/status", "/control/system/ollama", "/admin/stats"):
            from agents.monitoring import log_structured
            log_structured(
                level="ERROR",
                message=f"HTTP {request.method} {request.url.path} failed",
                session_id=request.headers.get("X-Session-ID", "system"),
                execution_time_ms=duration_ms,
                error=str(e)
            )
        raise e

@app.middleware("http")
async def verify_admin_api_key(request: Request, call_next):
    path = request.url.path
    if any(path.startswith(prefix) for prefix in ["/agents", "/settings", "/admin", "/control"]):
        if request.method == "OPTIONS":
            return await call_next(request)

        # Exempt read-only status-check endpoints the frontend polls
        exempt_paths = ["/control/system/ollama"]
        if path in exempt_paths and request.method == "GET":
            return await call_next(request)
            
        api_key = request.headers.get("X-API-Key")
        expected_key = os.getenv("API_KEY", "your_secure_token")
        if not api_key or api_key != expected_key:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: Invalid or missing X-API-Key"}
            )
    return await call_next(request)

app.include_router(auth_router)

from fastapi.staticfiles import StaticFiles
# Create output directory if not exists
output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
os.makedirs(os.path.join(output_dir, "images"), exist_ok=True)
app.mount("/output", StaticFiles(directory=output_dir), name="output")

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

class MediaRequest(BaseModel):
    action: str
    level: Optional[int] = None

class BrightnessRequest(BaseModel):
    level: int

class PowerRequest(BaseModel):
    action: str
    confirmed: Optional[bool] = False

class WindowSnapRequest(BaseModel):
    direction: str

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

    # Inject learned rules from feedback
    rules_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents", "learned_rules.txt")
    if os.path.exists(rules_path):
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                rules = f.read().strip()
                if rules:
                    prompt += f"\n\nLEARNED USER PREFERENCES & RULES:\n{rules}"
        except Exception:
            pass

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
        profile = load_profile()
        user_name = profile.get("preferred_name", profile.get("name", "User"))
        app_name = ""
        if isinstance(integration_data.get("data"), dict):
            app_name = integration_data["data"].get("app", "")

        context_prompts = {
            "emails":         f"Here are the emails retrieved:\n{data_str}\nPresent the emails as a clean, structured bulleted list. Do NOT mix details of different emails. Format each email exactly as:\n* **[Sender]** — *[Subject]*: [One-sentence concise summary of the content].",
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
            "pc_action"          : f"PC control action result:\n{data_str}\nKeep your response extremely short and simple. Say only something like 'done boss', 'ok boss', or 'alright boss'. Do NOT describe details, paths, or executables.",
            "system_stats"       : f"System health data:\n{data_str}\nPresent the key stats clearly — CPU %, RAM %, battery, disk. Flag anything high.",
            "files"              : f"File operation result:\n{data_str}\nConfirm what was done or list the files clearly.",
            "browser"            : f"Browser action result:\n{data_str}\nSummarize what was found or confirm the action.",
            "needs_confirmation" : f"This action needs user confirmation:\n{data_str}\nAsk the user to confirm before proceeding.",
            "app_not_found"      : f"Say exactly: 'Boss, I didnt find any application or app name {app_name} mind you say it again'",
            "knowledge"          : f"Knowledge base results:\n{data_str}\nProvide a friendly response using this information.",
            "code"               : f"Code tool result:\n{data_str}\nShow the code or execution output clearly.",
            "habits"             : f"Habit tracker result:\n{data_str}\nSummarize completion status or streaks warmly.",
            "health"             : f"Health log/trends result:\n{data_str}\nPresent stats or trends summary clearly.",
            "finance"            : f"Finance log/budgets result:\n{data_str}\nPresent transaction confirmation or budget details clearly.",
            "meals"              : f"Meal planning result:\n{data_str}\nPresent suggestions or meal plan clearly.",
            "tutor"              : f"Personal tutor lesson/quiz result:\n{data_str}\nHelp the student with this lesson or quiz content.",
            "writing"            : f"Creative writing output:\n{data_str}\nShow the generated content clearly.",
            "image"              : f"Image generator output:\n{data_str}\nShow the status and download path of the generated image.",
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
        profile = load_profile()
        user_name = profile.get("preferred_name", profile.get("name", "User"))
        app_name = ""
        if isinstance(integration_data.get("data"), dict):
            app_name = integration_data["data"].get("app", "")

        context_prompts = {
            "emails":         f"Here are the emails retrieved:\n{data_str}\nPresent the emails as a clean, structured bulleted list. Do NOT mix details of different emails. Format each email exactly as:\n* **[Sender]** — *[Subject]*: [One-sentence concise summary of the content].",
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
            "pc_action"          : f"PC control action result:\n{data_str}\nKeep your response extremely short and simple. Say only something like 'done boss', 'ok boss', or 'alright boss'. Do NOT describe details, paths, or executables.",
            "system_stats"       : f"System health data:\n{data_str}\nPresent the key stats clearly — CPU %, RAM %, battery, disk. Flag anything high.",
            "files"              : f"File operation result:\n{data_str}\nConfirm what was done or list the files clearly.",
            "browser"            : f"Browser action result:\n{data_str}\nSummarize what was found or confirm the action.",
            "needs_confirmation" : f"This action needs user confirmation:\n{data_str}\nAsk the user to confirm before proceeding.",
            "app_not_found"      : f"Say exactly: 'Boss, I didnt find any application or app name {app_name} mind you say it again'",
            "knowledge"          : f"Knowledge base results:\n{data_str}\nProvide a friendly response using this information.",
            "code"               : f"Code tool result:\n{data_str}\nShow the code or execution output clearly.",
            "habits"             : f"Habit tracker result:\n{data_str}\nSummarize completion status or streaks warmly.",
            "health"             : f"Health log/trends result:\n{data_str}\nPresent stats or trends summary clearly.",
            "finance"            : f"Finance log/budgets result:\n{data_str}\nPresent transaction confirmation or budget details clearly.",
            "meals"              : f"Meal planning result:\n{data_str}\nPresent suggestions or meal plan clearly.",
            "tutor"              : f"Personal tutor lesson/quiz result:\n{data_str}\nHelp the student with this lesson or quiz content.",
            "writing"            : f"Creative writing output:\n{data_str}\nShow the generated content clearly.",
            "image"              : f"Image generator output:\n{data_str}\nShow the status and download path of the generated image.",
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

# ─── ACTION DETAIL BUILDER ─────────────────────────────────────────────────────

def _build_action_detail(data: dict, intent: str, params: dict) -> str:
    """Build a short human-readable summary of the PC action that was performed."""
    sub = data.get("sub_action", "")
    action = data.get("action", intent)

    # Volume / Media
    if intent == "media_control":
        if sub == "set_volume":
            return f"volume set to {data.get('level', params.get('level', '?'))}"
        if sub == "vol_up":
            return "volume increased"
        if sub == "vol_down":
            return "volume decreased"
        if sub == "mute":
            return "volume muted"
        if sub == "unmute":
            return "volume unmuted"
        if sub == "toggle_mute":
            return "volume mute toggled"
        if sub == "volumemute":
            return "volume toggled mute"
        if sub == "playpause":
            return "playback toggled"
        if sub == "nexttrack":
            return "skipped to next track"
        if sub == "prevtrack":
            return "went to previous track"

    # Brightness
    if intent == "brightness_control":
        level = data.get("level", params.get("level", "?"))
        return f"brightness set to {level}"

    # Power
    if intent == "power_control":
        pwr = params.get("action", "")
        labels = {"lock": "PC locked", "sleep": "PC going to sleep", "shutdown": "shutting down",
                  "restart": "restarting", "cancel": "shutdown cancelled"}
        return labels.get(pwr, f"{pwr} done")

    # Open / Close / Kill
    if intent == "open_application":
        act_type = data.get("action", "open_app")
        name = data.get("name", params.get("app", "it"))
        if act_type == "open_folder":
            return f"{name} folder opened"
        elif act_type == "open_file":
            return f"{name} opened"
        elif act_type == "open_url":
            return f"{data.get('url', name)} opened in browser"
        return f"{name} opened"
    if intent == "close_application":
        return f"{params.get('title', 'application')} closed"
    if intent == "kill_process":
        return f"{params.get('name', 'process')} killed"

    # Screenshot
    if intent == "take_screenshot":
        return "screenshot captured"

    # Window snap
    if intent == "window_snap":
        return f"window snapped {params.get('direction', '')}"

    # Clipboard
    if intent == "clipboard_write":
        return "text copied to clipboard"
    if intent == "clipboard_read":
        return "clipboard read"

    # Typing / Hotkey
    if intent == "type_text":
        return "text typed"
    if intent == "press_hotkey":
        return f"pressed {params.get('keys', 'hotkey')}"

    # Notification
    if intent == "send_notification":
        return "notification sent"

    # Network
    if intent == "network_diagnostics":
        return "network diagnostics retrieved"

    # System stats / Processes
    if intent == "get_system_stats":
        return "system stats retrieved"
    if intent == "list_processes":
        return "processes listed"

    return ""

# ─── CHAT ROUTE ────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
@limiter.limit("5/minute")
async def chat(request: Request, chat_payload: ChatRequest):
    # Remap request to payload to preserve downstream compatibility
    global gemini_cooldown_until
    request_obj = request
    request = chat_payload
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

    # Auto-detect user corrections of previous model response
    from agents.learning import detect_correction_heuristics, log_user_correction
    if detect_correction_heuristics(request.message):
        history = get_history(session_id)
        last_model_msg = ""
        for turn in reversed(history):
            if turn.get("role") == "model":
                last_model_msg = turn.get("text", "")
                break
        if last_model_msg:
            log_user_correction(session_id, request.message, last_model_msg)

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
        "media_control", "brightness_control", "power_control",
        "window_snap", "network_diagnostics", "send_notification",
        "clipboard_write", "kill_process", "type_text", "press_hotkey",
    }

    # Complex tasks that need Gemini's reasoning power
    # Detected by checking if message looks like a knowledge/writing request
    def _needs_gemini(message: str, intent: str) -> bool:
        if intent not in ["general_chat", "knowledge_search", "browser_search"]:
            return False  # System action and control integration intents handled locally
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
            "joke", "jokes", "story", "stories", "poem", "poems",
            "draft", "write a passage", "tell a joke", "creative"
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

    # ── SHORT CONFIRMATION FOR SUCCESSFUL PC ACTIONS ──────────────────────────────
    if integration_data and integration_data.get("type") == "pc_action":
        data = integration_data.get("data", {})
        if isinstance(data, dict) and data.get("status") == "ok":
            import random
            prefix = random.choice(["Ok boss", "Alright boss", "Done boss", "Done, sir", "Alright, boss"])
            detail = _build_action_detail(data, intent, params)
            reply = f"{prefix}, {detail}." if detail else f"{prefix}."
            model_used = "system/direct_reply"
            print(f"[ARIS] Direct PC action confirmation: {reply}")

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

    # ── MODEL CALL ────────────────────────────────────────────────────────────────

    is_gemini_cooldown = time.time() < gemini_cooldown_until
    if is_gemini_cooldown:
        print("[ARIS] Gemini is in cooldown. Bypassing cloud call and routing to Ollama.")

    # Intercept use_gemini for Offline/Privacy Mode
    is_privacy_mode = os.getenv("PRIVACY_MODE", "false").lower() == "true"
    if is_privacy_mode:
        print("[ARIS Privacy] Privacy Mode enabled. Forcing local Ollama execution.")
        use_gemini = False
    else:
        use_gemini = _needs_gemini(request.message, intent) and not is_gemini_cooldown

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
                err_str = str(gemini_error).upper()
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "QUOTA" in err_str:
                    print("[ARIS] Gemini rate limit reached! Activating 5-minute local fallback cooldown...")
                    gemini_cooldown_until = time.time() + 300.0

                print(f"[ARIS] Gemini failed: {gemini_error}. Falling back to Ollama...")
                active_model = await get_best_ollama_model(ollama_model)
                reply      = await ask_ollama_with_context(
                    message=request.message,
                    history=history,
                    system_prompt=system_prompt,
                    integration_data=integration_data,
                    model=active_model
                )
                model_used = f"ollama/{active_model}"

        else:
            # Everything else → Ollama (local, free, private)
            try:
                active_model = await get_best_ollama_model(ollama_model)
                reply      = await ask_ollama_with_context(
                    message=request.message,
                    history=history,
                    system_prompt=system_prompt,
                    integration_data=integration_data,
                    model=active_model
                )
                model_used = f"ollama/{active_model}"
                print(f"[ARIS] Ollama({active_model}) | Session: '{session_id}' | Intent: {intent}")

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
You are ARIS, a personal AI assistant. Generate a warm, concise morning briefing for the user.
CRITICAL: Never address the user by their actual name ({name}). Instead, always address them as 'boss' or 'sir'.

Today is {date_str}. Here is all the data:

{briefing_json}

Write a friendly {greeting} message that:
1. Greets the user warmly as 'boss' or 'sir' (do NOT use their actual name)
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


@app.post("/control/pc/media")
async def pc_media(req: MediaRequest):
    try:
        return media_control(req.action, req.level)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/brightness")
async def pc_brightness(req: BrightnessRequest):
    try:
        return set_brightness(req.level)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/power")
async def pc_power(req: PowerRequest):
    try:
        act = req.action.lower().strip()
        if act == "lock":
            return lock_pc()
        elif act == "sleep":
            return sleep_pc()
        elif act == "shutdown":
            return shutdown_pc(req.confirmed)
        elif act == "restart":
            return restart_pc(req.confirmed)
        elif act in ("cancel", "abort"):
            return cancel_shutdown()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown power action '{req.action}'")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/control/pc/window/snap")
async def pc_window_snap(req: WindowSnapRequest):
    try:
        return snap_window(req.direction)
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


@app.get("/control/system/network/diagnostics")
async def system_network_diagnostics():
    try:
        return get_network_diagnostics()
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


# ── Intelligence: Search ────────────────────────────────────────────────────
from intelligence.search import web_search, deep_research, fact_check
from intelligence.knowledge import add_document, search_knowledge, list_documents, delete_document

@app.post("/intelligence/search")
async def route_web_search(request: Request):
    body = await request.json()
    query = body.get("query", "").strip()
    mode = body.get("mode", "quick")  # "quick" | "deep" | "factcheck"
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    if mode == "deep":
        result = await deep_research(query)
    elif mode == "factcheck":
        result = await fact_check(query)
    else:
        result = await web_search(query)
    return result

# ── Intelligence: Knowledge Base ─────────────────────────────────────────────

@app.post("/intelligence/knowledge/add")
async def route_knowledge_add(request: Request):
    body = await request.json()
    source_type = body.get("type", "").strip()
    content = body.get("content", "").strip()
    title = body.get("title", "").strip()
    if not source_type or not content:
        raise HTTPException(status_code=400, detail="type and content are required")
    return await add_document(source_type, content, title)

@app.post("/intelligence/knowledge/search")
async def route_knowledge_search(request: Request):
    body = await request.json()
    query = body.get("query", "").strip()
    limit = body.get("limit", 4)
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    results = await search_knowledge(query, limit)
    return {"results": results}

@app.get("/intelligence/knowledge/list")
async def route_knowledge_list():
    return {"documents": list_documents()}

@app.delete("/intelligence/knowledge/delete")
async def route_knowledge_delete(request: Request):
    body = await request.json()
    source = body.get("source", "").strip()
    if not source:
        raise HTTPException(status_code=400, detail="source is required")
    return delete_document(source)

# ── Intelligence: Code Assistant & Sandbox ───────────────────────────────────
from intelligence.code import generate_code, debug_code, execute_python

@app.post("/intelligence/code/generate")
async def route_code_generate(request: Request):
    body = await request.json()
    description = body.get("description", "").strip()
    language = body.get("language", "python").strip()
    if not description:
        raise HTTPException(status_code=400, detail="description is required")
    return await generate_code(description, language)

@app.post("/intelligence/code/debug")
async def route_code_debug(request: Request):
    body = await request.json()
    code = body.get("code", "").strip()
    error = body.get("error", "").strip()
    language = body.get("language", "python").strip()
    if not code:
        raise HTTPException(status_code=400, detail="code is required")
    return await debug_code(code, error, language)

@app.post("/intelligence/code/execute")
async def route_code_execute(request: Request):
    body = await request.json()
    code = body.get("code", "").strip()
    timeout = body.get("timeout", 10)
    if not code:
        raise HTTPException(status_code=400, detail="code is required")
    return execute_python(code, timeout)

# ── Life: Goal & Habit Tracker ───────────────────────────────────────────────
from life.habits import (
    create_habit, list_habits, delete_habit,
    log_habit, get_habit_status, get_all_streaks,
    create_goal, list_goals, update_goal_progress, delete_goal
)

@app.post("/life/habits/create")
async def route_create_habit(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    return create_habit(
        name,
        body.get("description", ""),
        body.get("target", ""),
        body.get("frequency", "daily")
    )

@app.get("/life/habits/list")
async def route_list_habits():
    return {"habits": list_habits()}

@app.delete("/life/habits/delete")
async def route_delete_habit(request: Request):
    body = await request.json()
    habit_id = body.get("id")
    if not habit_id:
        raise HTTPException(status_code=400, detail="id is required")
    return delete_habit(habit_id)

@app.post("/life/habits/log")
async def route_log_habit(request: Request):
    body = await request.json()
    habit_id = body.get("habit_id")
    if not habit_id:
        raise HTTPException(status_code=400, detail="habit_id is required")
    return log_habit(habit_id, body.get("date", ""), body.get("notes", ""))

@app.get("/life/habits/status/{habit_id}")
async def route_habit_status(habit_id: int):
    return get_habit_status(habit_id)

@app.get("/life/habits/streaks")
async def route_all_streaks():
    return {"streaks": get_all_streaks()}

@app.post("/life/goals/create")
async def route_create_goal(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    return create_goal(
        name,
        body.get("description", ""),
        body.get("target_date", ""),
        body.get("metric", "")
    )

@app.get("/life/goals/list")
async def route_list_goals():
    return {"goals": list_goals()}

@app.post("/life/goals/progress")
async def route_update_goal_progress(request: Request):
    body = await request.json()
    goal_id = body.get("id")
    progress = body.get("progress")
    if goal_id is None or progress is None:
        raise HTTPException(status_code=400, detail="id and progress are required")
    return update_goal_progress(goal_id, float(progress))

@app.delete("/life/goals/delete")
async def route_delete_goal(request: Request):
    body = await request.json()
    goal_id = body.get("id")
    if not goal_id:
        raise HTTPException(status_code=400, detail="id is required")
    return delete_goal(goal_id)

# ── Life: Health & Wellbeing ─────────────────────────────────────────────────
from life.health import log_health, get_health_log, get_health_history, analyze_trends, get_health_summary

@app.post("/life/health/log")
async def route_log_health(request: Request):
    body = await request.json()
    return log_health(
        log_date=body.get("date", ""),
        sleep_hours=body.get("sleep_hours"),
        mood=body.get("mood"),
        energy=body.get("energy"),
        water_litres=body.get("water_litres"),
        exercise_mins=body.get("exercise_mins"),
        exercise_type=body.get("exercise_type", ""),
        notes=body.get("notes", "")
    )

@app.get("/life/health/today")
async def route_health_today():
    return get_health_log()

@app.get("/life/health/history")
async def route_health_history(days: int = 7):
    return {"history": get_health_history(days)}

@app.get("/life/health/summary")
async def route_health_summary():
    return await get_health_summary()

@app.get("/life/health/trends")
async def route_health_trends(days: int = 7):
    return await analyze_trends(days)

# ── Life: Finance Awareness ──────────────────────────────────────────────────
from life.finance import (
    log_transaction, get_transactions, delete_transaction,
    get_monthly_summary, set_budget, get_budgets,
    create_savings_goal, add_to_savings, list_savings_goals
)

@app.post("/life/finance/log")
async def route_log_transaction(request: Request):
    body = await request.json()
    amount = body.get("amount")
    if amount is None:
        raise HTTPException(status_code=400, detail="amount is required")
    return log_transaction(
        amount=float(amount),
        category=body.get("category", "other"),
        description=body.get("description", ""),
        txn_type=body.get("type", "expense"),
        txn_date=body.get("date", "")
    )

@app.get("/life/finance/transactions")
async def route_get_transactions(days: int = 30, category: str = ""):
    return {"transactions": get_transactions(days, category)}

@app.delete("/life/finance/delete")
async def route_delete_transaction(request: Request):
    body = await request.json()
    txn_id = body.get("id")
    if not txn_id:
        raise HTTPException(status_code=400, detail="id is required")
    return delete_transaction(txn_id)

@app.get("/life/finance/summary")
async def route_monthly_summary(year: int = 0, month: int = 0):
    return get_monthly_summary(year, month)

@app.post("/life/finance/budget")
async def route_set_budget(request: Request):
    body = await request.json()
    category = body.get("category", "").strip()
    limit = body.get("monthly_limit")
    if not category or limit is None:
        raise HTTPException(status_code=400, detail="category and monthly_limit are required")
    return set_budget(category, float(limit))

@app.get("/life/finance/budgets")
async def route_get_budgets():
    return {"budgets": get_budgets()}

@app.post("/life/finance/savings/create")
async def route_create_savings_goal(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    target = body.get("target_amount")
    if not name or target is None:
        raise HTTPException(status_code=400, detail="name and target_amount are required")
    return create_savings_goal(name, float(target), body.get("target_date", ""))

@app.post("/life/finance/savings/add")
async def route_add_to_savings(request: Request):
    body = await request.json()
    goal_id = body.get("id")
    amount = body.get("amount")
    if goal_id is None or amount is None:
        raise HTTPException(status_code=400, detail="id and amount are required")
    return add_to_savings(goal_id, float(amount))

@app.get("/life/finance/savings")
async def route_list_savings():
    return {"goals": list_savings_goals()}

# ── Life: Meal Planning ──────────────────────────────────────────────────────
from life.meals import (
    log_meal, get_meals_today, get_meal_history, delete_meal,
    set_preference, get_preferences, suggest_meals, plan_weekly_meals
)

@app.post("/life/meals/log")
async def route_log_meal(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    return log_meal(
        name=name,
        meal_type=body.get("type", "lunch"),
        calories=body.get("calories"),
        notes=body.get("notes", ""),
        meal_date=body.get("date", "")
    )

@app.get("/life/meals/today")
async def route_meals_today(date: str = ""):
    return get_meals_today(date)

@app.get("/life/meals/history")
async def route_meal_history(days: int = 7):
    return {"history": get_meal_history(days)}

@app.delete("/life/meals/delete")
async def route_delete_meal(request: Request):
    body = await request.json()
    meal_id = body.get("id")
    if not meal_id:
        raise HTTPException(status_code=400, detail="id is required")
    return delete_meal(meal_id)

@app.post("/life/meals/preferences")
async def route_set_preference(request: Request):
    body = await request.json()
    key = body.get("key", "").strip()
    value = body.get("value", "").strip()
    if not key or not value:
        raise HTTPException(status_code=400, detail="key and value are required")
    return set_preference(key, value)

@app.get("/life/meals/preferences")
async def route_get_preferences():
    return {"preferences": get_preferences()}

@app.post("/life/meals/suggest")
async def route_suggest_meals(request: Request):
    body = await request.json()
    return await suggest_meals(body.get("meal_type", ""), body.get("preferences", ""))

@app.post("/life/meals/plan")
async def route_plan_weekly():
    return await plan_weekly_meals()

    
# ─── AUDIT LOG ROUTES ─────────────────────────────────────────────────────────


# ── Intelligence: Personal Tutor ─────────────────────────────────────────────
from intelligence.tutor import (
    start_lesson, generate_flashcards, list_flashcards,
    generate_quiz, submit_quiz_answers, get_tutor_progress
)

@app.post("/intelligence/tutor/learn")
async def route_tutor_learn(request: Request):
    body = await request.json()
    topic = body.get("topic", "").strip()
    difficulty = body.get("difficulty", "beginner").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")
    return await start_lesson(topic, difficulty)

@app.post("/intelligence/tutor/flashcards")
async def route_tutor_flashcards(request: Request):
    body = await request.json()
    topic = body.get("topic", "").strip()
    count = body.get("count", 5)
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")
    return await generate_flashcards(topic, count)

@app.get("/intelligence/tutor/flashcards")
async def route_list_flashcards(topic: str = ""):
    return {"flashcards": list_flashcards(topic)}

@app.post("/intelligence/tutor/quiz")
async def route_tutor_quiz(request: Request):
    body = await request.json()
    topic = body.get("topic", "").strip()
    difficulty = body.get("difficulty", "medium").strip()
    count = body.get("count", 3)
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")
    return await generate_quiz(topic, difficulty, count)

@app.post("/intelligence/tutor/quiz/submit")
async def route_tutor_quiz_submit(request: Request):
    body = await request.json()
    quiz_id = body.get("quiz_id")
    answers = body.get("answers")
    if quiz_id is None or answers is None:
        raise HTTPException(status_code=400, detail="quiz_id and answers are required")
    return submit_quiz_answers(quiz_id, answers)

@app.get("/intelligence/tutor/progress")
async def route_tutor_progress():
    return {"progress": get_tutor_progress()}

# ── Creative: Image Generation ───────────────────────────────────────────────
from creative.images import generate_image

@app.post("/creative/images")
async def route_generate_image(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    return await generate_image(prompt)


# ── Creative: Content Writing ───────────────────────────────────────────────
from creative.writing import generate_content

@app.post("/creative/writing")
async def route_generate_writing(request: Request):
    body = await request.json()
    topic = body.get("topic", "").strip()
    format_type = body.get("format", "blog").strip()
    export_type = body.get("export_type", "md").strip()
    export_name = body.get("export_name", "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")
    return await generate_content(topic, format_type, export_type, export_name)


# ── Agents: Task Loop ─────────────────────────────────────────────────────────
from agents.task_loop import plan_task, execute_task_loop, get_task_status, list_tasks
from fastapi import BackgroundTasks

@app.post("/agents/task")
async def route_create_task(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    goal = body.get("goal", "").strip()
    if not goal:
        raise HTTPException(status_code=400, detail="goal is required")
    
    plan = await plan_task(goal)
    if plan.get("status") == "error":
        return plan
        
    task_id = plan["task_id"]
    background_tasks.add_task(execute_task_loop, task_id)
    return plan

@app.get("/agents/task/{task_id}")
async def route_get_task(task_id: int):
    return get_task_status(task_id)

@app.get("/agents/tasks")
async def route_list_tasks(limit: int = 20):
    return {"tasks": list_tasks(limit)}


# ── Agents: Multi-Agent Spawning ──────────────────────────────────────────────
from agents.multi_agent import run_multi_agent_workflow

@app.post("/agents/multi")
async def route_run_multi_agent(request: Request):
    body = await request.json()
    goal = body.get("goal", "").strip()
    if not goal:
        raise HTTPException(status_code=400, detail="goal is required")
    
    result = await run_multi_agent_workflow(goal)
    return result


# ── Agents: Self-Tool Creation ────────────────────────────────────────────────
from agents.tool_creator import create_self_tool, list_registered_tools

@app.post("/agents/create-tool")
async def route_create_self_tool(request: Request):
    body = await request.json()
    task_desc = body.get("task_description", "").strip()
    tool_name = body.get("tool_name", "").strip()
    test_params = body.get("test_params", {})
    
    if not task_desc or not tool_name:
        raise HTTPException(status_code=400, detail="task_description and tool_name are required")
        
    result = await create_self_tool(task_desc, tool_name, test_params)
    return result

@app.get("/agents/tools")
async def route_list_self_tools():
    return {"tools": list_registered_tools()}


# ── Agents: Self-Learning from Feedback ───────────────────────────────────────
from agents.learning import log_user_correction, analyze_feedback_and_update_prompt, get_learning_summary

@app.post("/agents/feedback")
async def route_log_feedback(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "").strip()
    correction = body.get("user_correction", "").strip()
    response = body.get("model_response", "").strip()
    
    if not session_id or not correction or not response:
        raise HTTPException(status_code=400, detail="session_id, user_correction, and model_response are required")
        
    success = log_user_correction(session_id, correction, response)
    return {"status": "success" if success else "error"}

@app.post("/agents/learning/trigger")
async def route_trigger_learning():
    return await analyze_feedback_and_update_prompt()

@app.get("/agents/learning/summary")
async def route_learning_summary():
    return get_learning_summary()


# ── Agents: 24/7 Scheduler & Automations ──────────────────────────────────────
from agents.scheduler import create_scheduled_job, list_scheduled_jobs, delete_scheduled_job, trigger_job_now

@app.post("/agents/schedule")
async def route_create_schedule(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    trigger_type = body.get("trigger_type", "").strip()
    expression = body.get("expression", "").strip()
    intent = body.get("intent", "").strip()
    params = body.get("params", {})
    
    if not name or not trigger_type or not expression or not intent:
        raise HTTPException(status_code=400, detail="name, trigger_type, expression, and intent are required")
        
    return create_scheduled_job(name, trigger_type, expression, intent, params)

@app.get("/agents/schedules")
async def route_list_schedules():
    return {"schedules": list_scheduled_jobs()}

@app.delete("/agents/schedule/{job_id}")
async def route_delete_schedule(job_id: str):
    return delete_scheduled_job(job_id)

@app.post("/agents/schedule/{job_id}/trigger")
async def route_trigger_schedule(job_id: str):
    return trigger_job_now(job_id)


# ── Agents: Predictive Assistance ─────────────────────────────────────────────
from agents.prediction import predict_next_actions

@app.get("/agents/predict")
async def route_predict_actions():
    return await predict_next_actions()


# ── Settings: Privacy & Offline Mode ──────────────────────────────────────────
from agents.privacy import update_privacy_settings, get_privacy_settings

@app.post("/settings/privacy")
async def route_save_privacy(request: Request):
    body = await request.json()
    privacy_mode = body.get("privacy_mode", False)
    retention_days = body.get("retention_days", 30)
    
    return update_privacy_settings(privacy_mode, retention_days)

@app.get("/settings/privacy")
async def route_get_privacy():
    return get_privacy_settings()


# ── Observability: Admin Statistics Panel ──────────────────────────────────────
from agents.monitoring import get_admin_stats

@app.get("/admin/stats")
async def route_admin_stats():
    return get_admin_stats()


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

# ─── FINE-TUNING ENDPOINTS ─────────────────────────────────────────────────────

@app.get("/finetune/status")
async def get_finetune_status():
    from finetune.retrain import load_metadata, get_new_examples_count
    meta = load_metadata()
    new_count = get_new_examples_count(meta["last_trained_timestamp"])
    return {
        "status": "ok",
        "last_trained": meta["last_trained_timestamp"],
        "examples_at_last_train": meta["examples_at_last_train"],
        "new_examples_collected": new_count,
        "model_versions": meta["model_versions"],
        "rollback_versions": meta["rollback_versions"]
    }

# Background worker for running training asynchronously so it doesn't block the HTTP call
def run_retrain_bg(force: bool, dry_run: bool):
    try:
        from finetune.retrain import run_retrain_pipeline
        run_retrain_pipeline(force=force, dry_run=dry_run)
    except Exception as e:
        print(f"[ARIS Finetune Worker] Asynchronous retraining failed: {e}")

@app.post("/finetune/retrain")
async def trigger_retrain(background_tasks: BackgroundTasks, force: bool = False, dry_run: bool = False):
    background_tasks.add_task(run_retrain_bg, force, dry_run)
    return {"status": "started", "message": "Retraining job queued in background."}

@app.post("/finetune/rollback")
async def rollback_model(model_type: str):
    # model_type: llama3.2, mistral, gemma3
    if model_type not in ["llama3.2", "mistral", "gemma3"]:
        raise HTTPException(status_code=400, detail="Invalid model type. Must be llama3.2, mistral, or gemma3.")
        
    from finetune.retrain import load_metadata, save_metadata
    meta = load_metadata()
    rollbacks = meta["rollback_versions"][model_type]
    if not rollbacks:
        raise HTTPException(status_code=400, detail=f"No rollback versions available for {model_type}.")
        
    # Revert to the last version in rollbacks
    previous_version = rollbacks.pop()
    current_version = meta["model_versions"][model_type]
    
    # Rollback Ollama tag copy
    ollama_base_tag = "aris-llama" if model_type == "llama3.2" else ("aris-mistral" if model_type == "mistral" else "aris-gemma")
    prev_tag = previous_version.replace("-v", ":")
    
    # Copy previous version tag back to main tag
    # e.g., ollama copy aris-llama:1 aris-llama
    cmd = ["ollama", "copy", prev_tag, ollama_base_tag]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Ollama rollback copy failed: {res.stderr}")
        
    # Put current version back to rollback list (swap them)
    rollbacks.insert(0, current_version)
    meta["rollback_versions"][model_type] = rollbacks
    meta["model_versions"][model_type] = previous_version
    save_metadata(meta)
    
    return {
        "status": "success",
        "message": f"Successfully rolled back {model_type} to {previous_version}.",
        "active_version": previous_version
    }

# ─── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)