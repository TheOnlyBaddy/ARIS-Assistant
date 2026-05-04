"""
ARIS - Autonomous Reasoning & Intelligence System
Backend Main Entry Point
Phase 1, Step 7 - Safety Guardrails
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Any, Optional
import uvicorn
import os
import httpx
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

load_dotenv()

# ─── CONFIG ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
PRIMARY_MODEL   = os.getenv("PRIMARY_MODEL", "gemini-2.5-flash")
FALLBACK_MODEL  = os.getenv("FALLBACK_MODEL", "llama3.2")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

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
    version="1.0.0"
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
    print(f"[ARIS] Ready for {profile.get('name', 'User')} | "
          f"Sessions: {len(conversation_store)} | "
          f"Memories: {stats['total_memories']} | "
          f"Trust level: {safety['trust_level']}")

# ─── REQUEST / RESPONSE MODELS ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    confirmed: bool = False     # User sets this True to confirm a destructive action

class ChatResponse(BaseModel):
    response: str
    model_used: str
    session_id: str
    turn_count: int
    memories_used: int
    safety_status: str          # "ok", "blocked", "needs_confirmation"

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


async def ask_ollama(history: list[dict], system_prompt: str) -> str:
    prompt = build_ollama_prompt(history, system_prompt)
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": FALLBACK_MODEL, "prompt": prompt, "stream": False}
        )
        r.raise_for_status()
        return r.json()["response"]

# ─── ROUTES ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    profile = load_profile()
    return {
        "system": "ARIS",
        "version": "1.0.0",
        "status": "online",
        "user": profile.get("preferred_name", "User"),
        "message": f"ARIS is ready. Welcome back, {profile.get('preferred_name', 'User')}."
    }


@app.get("/health")
async def health_check():
    stats  = get_memory_stats()
    safety = get_safety_config()
    return {
        "status": "ok",
        "service": "ARIS Backend",
        "phase": "1 - Core Brain",
        "active_sessions": len(conversation_store),
        "semantic_memories": stats["total_memories"],
        "trust_level": safety["trust_level"]
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    session_id = request.session_id

    # ── SAFETY CHECK ──────────────────────────────────────────────────────────
    safety_result = check_message_safety(request.message)

    # Hard block — refuse completely
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

    # Needs confirmation — pause and ask user
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

    # Normal flow — retrieve memories, build prompt, get response
    relevant_memories = await search_memories(request.message, n_results=3)
    system_prompt     = build_full_system_prompt(relevant_memories)

    add_to_memory(session_id, "user", request.message)
    history = get_history(session_id)

    try:
        reply      = await ask_gemini(history, system_prompt)
        model_used = PRIMARY_MODEL
        print(f"[ARIS] Gemini | Session: '{session_id}' | "
              f"Turn: {len(history)} | Memories: {len(relevant_memories)}")

    except Exception as gemini_error:
        print(f"[ARIS] Gemini failed: {gemini_error}. Switching to Ollama...")
        try:
            reply      = await ask_ollama(history, system_prompt)
            model_used = f"ollama/{FALLBACK_MODEL}"
        except Exception as ollama_error:
            conversation_store[session_id].pop()
            raise HTTPException(status_code=503,
                detail=f"Both models failed. Gemini: {gemini_error}. Ollama: {ollama_error}")

    add_to_memory(session_id, "model", reply, model_used)
    await extract_and_store_facts(request.message, reply, session_id)

    return ChatResponse(
        response=reply,
        model_used=model_used,
        session_id=session_id,
        turn_count=len(conversation_store[session_id]) // 2,
        memories_used=len(relevant_memories),
        safety_status="ok"
    )


# ─── MEMORY ROUTES ─────────────────────────────────────────────────────────────

@app.get("/memory/{session_id}")
async def get_memory(session_id: str):
    history = get_history(session_id)
    return {"session_id": session_id, "turn_count": len(history) // 2, "history": history}


@app.delete("/memory/{session_id}")
async def clear_memory(session_id: str, confirmed: bool = False):
    """
    Clear a session's memory. Requires confirmed=true as a query param.
    Example: DELETE /memory/my-session?confirmed=true
    """
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
async def safety_status():
    """View current safety configuration."""
    return get_safety_config()


# ─── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)