"""
ARIS Monitoring & Observability Module
- Implements structured JSON logging to stdout and file
- Captures system resource utilization and database metrics
- Serves administrative usage statistics
"""

import os
import time
import json
import psutil
import sqlite3
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(BASE_DIR)
DB_PATH = os.path.join(BACKEND_DIR, "aris.db")
LOG_PATH = os.path.join(BACKEND_DIR, "aris_structured.log")
TOOLS_REGISTRY_PATH = os.path.join(BASE_DIR, "generated_tools", "tools_registry.json")


def log_structured(level: str, message: str, session_id: str = "system", execution_time_ms: float = 0.0, error: str = None):
    """Log formatted JSON message to console and persistent log file."""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        "session_id": session_id,
        "execution_time_ms": round(execution_time_ms, 2)
    }
    if error:
        log_entry["error"] = error
        
    # Print to console (Docker catches this)
    print(json.dumps(log_entry))
    
    # Save to file
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"[ARIS Logger Error] Failed to write log: {e}")


def get_db_size_kb() -> float:
    """Return size of SQLite database in KB."""
    if os.path.exists(DB_PATH):
        return round(os.path.getsize(DB_PATH) / 1024.0, 2)
    return 0.0


def get_active_session_count() -> int:
    """Count number of active conversation sessions in SQLite."""
    if not os.path.exists(DB_PATH):
        return 0
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT COUNT(DISTINCT session_id) FROM conversation_messages").fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


def get_registered_tool_count() -> int:
    """Count self-created tools registered in JSON catalog."""
    if os.path.exists(TOOLS_REGISTRY_PATH):
        try:
            with open(TOOLS_REGISTRY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return len(data)
        except Exception:
            pass
    return 0


def get_error_count() -> int:
    """Count total error entries recorded in our structured log file."""
    if not os.path.exists(LOG_PATH):
        return 0
    errors = 0
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if '"level": "ERROR"' in line:
                    errors += 1
    except Exception:
        pass
    return errors


def get_admin_stats() -> dict:
    """Consolidate resource metrics, DB size, and log data."""
    # Force single-shot CPU percentage query
    cpu_usage = psutil.cpu_percent(interval=None)
    mem_usage = psutil.virtual_memory().percent

    return {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": {
            "cpu_load_percent": cpu_usage,
            "memory_utilization_percent": mem_usage
        },
        "database": {
            "db_size_kb": get_db_size_kb(),
            "total_active_sessions": get_active_session_count()
        },
        "agents": {
            "registered_tools_count": get_registered_tool_count()
        },
        "observability": {
            "logged_errors_count": get_error_count(),
            "log_file_size_kb": round(os.path.getsize(LOG_PATH) / 1024.0, 2) if os.path.exists(LOG_PATH) else 0.0
        }
    }
