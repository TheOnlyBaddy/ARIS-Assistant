"""
ARIS Self-Learning from User Feedback
Logs user corrections to SQLite and analyzes patterns using LLM to generate
and apply system prompt instructions on the fly.
"""

import os
import sqlite3
import httpx
from datetime import datetime, timezone
from google import genai
from google.genai import types

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(os.path.dirname(BASE_DIR), "aris.db")
RULES_PATH = os.path.join(BASE_DIR, "learned_rules.txt")

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("PRIMARY_MODEL", "gemini-2.5-flash")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_feedback_tables():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_feedback (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id       TEXT    NOT NULL,
            user_correction  TEXT    NOT NULL,
            model_response   TEXT    NOT NULL,
            timestamp        TEXT    NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_feedback_tables()


# ─── CORRECTION DETECTION & LOGGING ──────────────────────────────────────────

CORRECTION_KEYWORDS = [
    "that's wrong", "not what i meant", "wrong response", "incorrect",
    "that is wrong", "no, i meant", "you got that wrong", "that's incorrect"
]

def detect_correction_heuristics(message: str) -> bool:
    """Check if message matches correction indicators."""
    msg_lower = message.lower()
    for kw in CORRECTION_KEYWORDS:
        if kw in msg_lower:
            return True
    return False


def log_user_correction(session_id: str, correction: str, last_response: str) -> bool:
    """Log a user correction entry to SQLite."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn = _get_conn()
        conn.execute(
            "INSERT INTO user_feedback (session_id, user_correction, model_response, timestamp) VALUES (?, ?, ?, ?)",
            (session_id, correction, last_response, now)
        )
        conn.commit()
        conn.close()
        print(f"[ARIS Learning] Logged correction: '{correction}'")
        return True
    except Exception as e:
        print(f"[ARIS Learning] Logging feedback failed: {e}")
        return False


# ─── FEEDBACK ANALYZER CORE ───────────────────────────────────────────────────

async def analyze_feedback_and_update_prompt() -> dict:
    """Fetch all corrections, analyze using LLM, and update learned_rules.txt."""
    conn = _get_conn()
    rows = conn.execute("SELECT user_correction, model_response FROM user_feedback").fetchall()
    conn.close()

    if len(rows) == 0:
        return {"status": "success", "message": "No corrections logged yet. Rules unchanged.", "rules": ""}

    # Format correction list
    correction_logs = ""
    for idx, r in enumerate(rows, 1):
        correction_logs += f"Correction {idx}:\n  Model said: '{r['model_response']}'\n  User corrected: '{r['user_correction']}'\n\n"

    prompt = (
        "You are the self-learning core of ARIS. Analyze the following list of user corrections to identify patterns. "
        "Formulate a concise, bulleted list of specific instructions/preferences that ARIS must follow in the future.\n\n"
        "User Correction History:\n"
        f"{correction_logs}\n"
        "Generate a clear, instruction-based summary of guidelines (e.g. '1. Always do X when asked Y'). "
        "Keep it concise (maximum 10 rules). Output ONLY the final bulleted list, no explanation or introductory text."
    )

    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
        )
        rules_text = response.text.strip()
    except Exception as e:
        print(f"[ARIS Learning] Gemini analysis failed: {e}. Trying Ollama fallback...")
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2")
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                r = await client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": ollama_model,
                        "prompt": prompt,
                        "stream": False,
                    }
                )
                r.raise_for_status()
                rules_text = r.json().get("response", "").strip()
        except Exception as ollama_err:
            return {"status": "error", "message": f"LLM analysis failed on both Gemini ({e}) and Ollama ({ollama_err})"}

    # Save to learned_rules.txt
    try:
        with open(RULES_PATH, "w", encoding="utf-8") as f:
            f.write(rules_text)
        return {
            "status": "success",
            "message": "Learned instructions updated successfully.",
            "rules": rules_text
        }
    except Exception as io_err:
        return {"status": "error", "message": f"Failed to save learned rules: {str(io_err)}"}


def get_learning_summary() -> dict:
    """Retrieve current corrections list and active rules."""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM user_feedback ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()

    active_rules = ""
    if os.path.exists(RULES_PATH):
        try:
            with open(RULES_PATH, "r", encoding="utf-8") as f:
                active_rules = f.read().strip()
        except Exception:
            pass

    return {
        "corrections": [dict(r) for r in rows],
        "active_rules": active_rules
    }
