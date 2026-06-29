"""
ARIS Agentic Task Loop
- Think -> Plan -> Act -> Observe -> Retry loop
- Decomposes complex goals into ordered subtasks using Gemini
- Executes subtasks via intent executor
- Stores task/subtask states in SQLite (backend/aris.db)
"""

import os
import sqlite3
import json
import asyncio
import httpx
from datetime import datetime, timezone
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
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_tables():
    """Create agent task tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agent_tasks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            goal         TEXT    NOT NULL,
            status       TEXT    NOT NULL DEFAULT 'pending', -- pending, running, done, failed
            created_at   TEXT    NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_subtasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id     INTEGER NOT NULL,
            step_number INTEGER NOT NULL,
            description TEXT    NOT NULL,
            intent      TEXT    NOT NULL,
            params      TEXT    NOT NULL DEFAULT '{}', -- JSON string of intent params
            status      TEXT    NOT NULL DEFAULT 'pending', -- pending, running, done, failed, retrying
            result      TEXT, -- JSON string or text output
            retries     INTEGER DEFAULT 0,
            FOREIGN KEY(task_id) REFERENCES agent_tasks(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()


init_tables()


# ─── AGENT TASK LOOP IMPLEMENTATION ───────────────────────────────────────────

async def plan_task(goal: str) -> dict:
    """Analyze the goal and decompose it into ordered subtasks using Gemini."""
    prompt = (
        f"You are the autonomous planning core of ARIS. Break down the user's high-level goal into an ordered sequence of concrete subtasks.\n"
        f"Goal: '{goal}'\n\n"
        "Each subtask must map to one of our supported system intents. Available intents include:\n"
        "- `browser_search` (params: query)\n"
        "- `browser_open` (params: url)\n"
        "- `list_files` (params: path)\n"
        "- `read_file` (params: path)\n"
        "- `create_file` (params: path, content)\n"
        "- `code_generate` (params: description, language)\n"
        "- `code_execute` (params: code)\n"
        "- `send_notification` (params: message)\n"
        "- `knowledge_store` (params: content, title)\n"
        "- `knowledge_search` (params: query)\n\n"
        "Format your output as a valid JSON array of objects. Do not include markdown wraps or fences. "
        "Each object MUST have exactly these keys:\n"
        "- 'step_number': Integer index starting from 1\n"
        "- 'description': Short summary of this step\n"
        "- 'intent': The matching intent name string\n"
        "- 'params': Object containing parameters for the intent\n\n"
        "Example output structure:\n"
        '[\n  {"step_number": 1, "description": "Search for X", "intent": "browser_search", "params": {"query": "X"}}\n]'
    )

    raw_text = None
    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=1024)
            )
        )
        raw_text = response.text.strip()
    except Exception as gemini_err:
        print(f"[ARIS Task Loop] Gemini planning failed: {gemini_err}. Trying Ollama fallback...")
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_REASON_MODEL", "gemma3:4b")
        try:
            with httpx.Client(timeout=45.0) as client:
                r = client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {
                            "temperature": 0.0
                        }
                    }
                )
                r.raise_for_status()
                raw_text = r.json().get("response", "").strip()
        except Exception as ollama_err:
            return {"status": "error", "message": f"Planning failed on both Gemini ({gemini_err}) and Ollama ({ollama_err})"}

    try:
        # Clean markdown formatting if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            raw_text = "\n".join(lines).strip()
            if raw_text.startswith("json"):
                raw_text = raw_text[4:].strip()

        steps = json.loads(raw_text)
        if isinstance(steps, dict):
            for k in ["steps", "plan", "subtasks", "tasks"]:
                if k in steps and isinstance(steps[k], list):
                    steps = steps[k]
                    break
            if isinstance(steps, dict):
                steps = [steps]

        now = datetime.now(timezone.utc).isoformat()

        # Create main task
        conn = _get_conn()
        cur = conn.execute(
            "INSERT INTO agent_tasks (goal, status, created_at) VALUES (?, 'pending', ?)",
            (goal, now)
        )
        task_id = cur.lastrowid

        # Insert subtasks
        for step in steps:
            step_num = int(step.get("step_number", 1))
            desc = step.get("description", "").strip()
            intent = step.get("intent", "general_chat").strip()
            params = json.dumps(step.get("params", {}))

            conn.execute(
                """INSERT INTO agent_subtasks (task_id, step_number, description, intent, params, status)
                   VALUES (?, ?, ?, ?, ?, 'pending')""",
                (task_id, step_num, desc, intent, params)
            )
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "task_id": task_id,
            "goal": goal,
            "steps": steps
        }
    except Exception as e:
        return {"status": "error", "message": f"Planning failed: {str(e)}"}


async def execute_task_loop(task_id: int):
    """Background loop that processes subtasks sequentially with error recovery/retries."""
    conn = _get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return

    # Update state to running
    conn.execute("UPDATE agent_tasks SET status = 'running' WHERE id = ?", (task_id,))
    conn.commit()

    subtasks = conn.execute(
        "SELECT * FROM agent_subtasks WHERE task_id = ? ORDER BY step_number ASC",
        (task_id,)
    ).fetchall()
    conn.close()

    max_retries = 2

    for row in subtasks:
        subtask_id = row["id"]
        intent = row["intent"]
        params = json.loads(row["params"])
        step_number = row["step_number"]

        print(f"[ARIS Task Loop] Executing Task {task_id} | Step {step_number}: {row['description']}")

        # Update subtask state to running
        conn = _get_conn()
        conn.execute("UPDATE agent_subtasks SET status = 'running' WHERE id = ?", (subtask_id,))
        conn.commit()
        conn.close()

        success = False
        result_data = None
        attempt = 0

        while attempt <= max_retries and not success:
            if attempt > 0:
                print(f"[ARIS Task Loop] Retrying subtask {subtask_id} (Attempt {attempt}/{max_retries})...")
                conn = _get_conn()
                conn.execute(
                    "UPDATE agent_subtasks SET status = 'retrying', retries = ? WHERE id = ?",
                    (attempt, subtask_id)
                )
                conn.commit()
                conn.close()

            try:
                # Act: Execute intent
                res = await execute_intent(intent, params)
                
                # Observe: Parse result
                is_err = False
                if res:
                    if res.get("type") == "error":
                        is_err = True
                    elif isinstance(res.get("data"), dict) and res["data"].get("status") == "error":
                        is_err = True
                
                if is_err:
                    result_data = res.get("data") if res else "Unknown error"
                    attempt += 1
                else:
                    success = True
                    result_data = res
            except Exception as e:
                result_data = f"Exception: {str(e)}"
                attempt += 1

        # Save result and final subtask status
        conn = _get_conn()
        final_status = "done" if success else "failed"
        conn.execute(
            "UPDATE agent_subtasks SET status = ?, result = ? WHERE id = ?",
            (final_status, json.dumps(result_data, default=str), subtask_id)
        )
        conn.commit()
        conn.close()

        # If a critical step failed, we abort the entire task loop
        if not success:
            print(f"[ARIS Task Loop] Task {task_id} failed at Step {step_number}. Aborting loop.")
            conn = _get_conn()
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE agent_tasks SET status = 'failed', completed_at = ? WHERE id = ?",
                (now, task_id)
            )
            conn.commit()
            conn.close()
            return

    # All steps completed successfully
    print(f"[ARIS Task Loop] Task {task_id} completed successfully.")
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE agent_tasks SET status = 'done', completed_at = ? WHERE id = ?",
        (now, task_id)
    )
    conn.commit()
    conn.close()


def get_task_status(task_id: int) -> dict:
    """Retrieve full execution status of a task and its subtasks."""
    conn = _get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return {"status": "error", "message": "Task not found"}

    subtasks = conn.execute(
        "SELECT * FROM agent_subtasks WHERE task_id = ? ORDER BY step_number ASC",
        (task_id,)
    ).fetchall()
    conn.close()

    return {
        "task": dict(task),
        "subtasks": [dict(s) for s in subtasks]
    }


def list_tasks(limit: int = 20) -> list:
    """List all recent goals and tasks."""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM agent_tasks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
