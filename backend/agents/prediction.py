"""
ARIS Predictive Assistance Core
- Analyzes interaction history (conversation_messages) to learn user query patterns
- Inspects upcoming calendar events for the next 2 hours
- Uses LLM to proactively suggest next actions and prepare briefs
"""

import os
import sqlite3
import json
import httpx
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types
from integrations.router import execute_intent

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(os.path.dirname(BASE_DIR), "aris.db")

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("PRIMARY_MODEL", "gemini-2.5-flash")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def analyze_user_patterns() -> dict:
    """Analyze conversation history to find hourly pattern frequencies of intents/keywords."""
    conn = _get_conn()
    try:
        # Fetch all user messages with timestamps
        rows = conn.execute(
            "SELECT text, timestamp FROM conversation_messages WHERE role = 'user'"
        ).fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()

    patterns = {}
    if not rows:
        return patterns

    for r in rows:
        text = r["text"].lower()
        ts_str = r["timestamp"]
        try:
            # Parse timestamp and extract hour
            # SQLite datetime strings look like '2026-06-29T10:50:26'
            if "T" in ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            else:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
            
            # Convert to local hour (approximate)
            hour = ts.hour
            
            # Simple keyword classification
            category = "general"
            if any(k in text for k in ["email", "inbox", "gmail", "mail"]):
                category = "emails"
            elif any(k in text for k in ["calendar", "schedule", "event", "meeting"]):
                category = "calendar"
            elif any(k in text for k in ["task", "todo", "todoist"]):
                category = "tasks"
            elif any(k in text for k in ["stat", "cpu", "health", "system"]):
                category = "system"
            elif any(k in text for k in ["spend", "expense", "budget", "finance"]):
                category = "finance"

            if category != "general":
                key = f"{hour:02d}:00"
                if key not in patterns:
                    patterns[key] = {}
                patterns[key][category] = patterns[key].get(category, 0) + 1
        except Exception:
            continue

    return patterns


async def get_upcoming_events() -> list:
    """Retrieve calendar events starting in the next 2 hours."""
    try:
        res = await execute_intent("get_today_events", {})
        if res and res.get("type") == "events":
            events = res.get("data", [])
            now = datetime.now(timezone.utc)
            two_hours_later = now + timedelta(hours=2)

            upcoming = []
            for e in events:
                start_str = e.get("start")
                if start_str:
                    try:
                        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                        if now <= start_dt <= two_hours_later:
                            # Calculate minutes until start
                            mins_until = int((start_dt - now).total_seconds() / 60)
                            e["mins_until"] = mins_until
                            upcoming.append(e)
                    except Exception:
                        continue
            return upcoming
    except Exception:
        pass
    return []


async def predict_next_actions() -> dict:
    """Analyze current time, patterns, and calendar to output proactive suggestions."""
    # 1. Get current time context
    now_local = datetime.now()
    current_hour = now_local.hour
    time_str = now_local.strftime("%I:%M %p")

    # 2. Get pattern history
    patterns = analyze_user_patterns()
    hour_key = f"{current_hour:02d}:00"
    current_hour_patterns = patterns.get(hour_key, {})

    # 3. Get calendar context
    upcoming_meetings = await get_upcoming_events()

    # Formulate analysis prompt
    prompt = (
        "You are the predictive assistance core of ARIS. Based on the user's current context, predict what they might need and suggest proactive actions.\n\n"
        f"Current Local Time: {time_str} (Hour {current_hour:02d})\n"
        f"User History Patterns for this hour: {json.dumps(current_hour_patterns)}\n"
        f"Upcoming Calendar Events (next 2 hours): {json.dumps(upcoming_meetings)}\n\n"
        "Generate 1-3 highly context-aware, proactive suggestions. Examples:\n"
        "- If a meeting is starting in 30 mins: Suggest preparing a brief or joining link.\n"
        "- If the user usually checks emails at this hour: Suggest summarizes their unread mail.\n"
        "- If no major event or pattern matches: Suggest a general productive nudge based on typical office hours (e.g. review tasks, health check).\n\n"
        "Output your suggestions as a valid JSON object with a single key 'suggestions' containing a list of strings. Do not include markdown fences."
    )

    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
        )
        raw_text = response.text.strip()
    except Exception as e:
        print(f"[ARIS Predict] Gemini failed: {e}. Trying Ollama fallback...")
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
                raw_text = r.json().get("response", "").strip()
        except Exception as ollama_err:
            return {"status": "error", "message": f"Prediction failed on both Gemini ({e}) and Ollama ({ollama_err})"}

    # Clean markdown fences
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        raw_text = "\n".join(lines).strip()
        if raw_text.startswith("json"):
            raw_text = raw_text[4:].strip()

    try:
        data = json.loads(raw_text)
        return {
            "status": "success",
            "time": time_str,
            "patterns_detected": current_hour_patterns,
            "upcoming_events_found": len(upcoming_meetings),
            "suggestions": data.get("suggestions", [])
        }
    except Exception as parse_err:
        return {
            "status": "success",
            "time": time_str,
            "patterns_detected": current_hour_patterns,
            "upcoming_events_found": len(upcoming_meetings),
            "suggestions": [raw_text]
        }
