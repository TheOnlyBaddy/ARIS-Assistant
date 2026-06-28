"""
ARIS Safety Guardrails — Phase 4
Protects against harmful requests, enforces confirmation before
destructive control actions, and logs all control actions to SQLite.
"""

import os
import re
import sqlite3
from datetime import datetime
from enum import Enum
from pathlib import Path

# ─── TRUST LEVELS ──────────────────────────────────────────────────────────────

class TrustLevel(str, Enum):
    AUTO = "auto"   # ARIS acts immediately
    ASK  = "ask"    # ARIS asks before destructive actions

TRUST_LEVEL = TrustLevel(os.getenv("ARIS_TRUST_LEVEL", "ask"))

# ─── AUDIT LOG SETUP ───────────────────────────────────────────────────────────

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
AUDIT_DB  = os.path.join(BASE_DIR, "audit_log.db")

def _init_audit_db():
    conn = None
    try:
        conn = sqlite3.connect(AUDIT_DB)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS control_audit (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                action      TEXT    NOT NULL,
                params      TEXT,
                result      TEXT,
                confirmed   INTEGER DEFAULT 0,
                blocked     INTEGER DEFAULT 0
            )
        """)
        conn.commit()
    finally:
        if conn:
            conn.close()

_init_audit_db()


def log_control_action(action: str, params: str = "", result: str = "",
                        confirmed: bool = False, blocked: bool = False):
    """Write every control action to the audit log."""
    conn = None
    try:
        conn = sqlite3.connect(AUDIT_DB)
        conn.execute("""
            INSERT INTO control_audit (timestamp, action, params, result, confirmed, blocked)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            action,
            str(params)[:500],
            str(result)[:500],
            int(confirmed),
            int(blocked)
        ))
        conn.commit()
    except Exception as e:
        print(f"[Audit] Log failed: {e}")
    finally:
        if conn:
            conn.close()


def get_audit_log(limit: int = 50) -> list[dict]:
    """Return recent audit log entries, newest first."""
    conn = None
    try:
        conn = sqlite3.connect(AUDIT_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM control_audit
            ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[Audit] Read failed: {e}")
        return []
    finally:
        if conn:
            conn.close()

# ─── BLOCKED CONTENT PATTERNS ──────────────────────────────────────────────────

BLOCKED_PATTERNS = [
    r"\b(how to (make|build|create) a (bomb|weapon|explosive))\b",
    r"\b(instructions for (killing|harming|hurting) (someone|people|a person))\b",
    r"\b(how to (kill|hurt) (myself|yourself))\b",
    r"\b(suicide (method|instructions|how to))\b",
    r"\b(how to (hack|crack|break into) (a system|an account|a network))\b",
    r"\b(make (drugs|meth|cocaine|heroin))\b",
    r"\b(ignore (all )?(previous |prior )?(instructions|prompts))\b",
    r"\b(jailbreak|dan mode|developer mode|ignore your (training|rules))\b",
    r"\b(reveal your (system prompt|instructions|prompt))\b",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]

# ─── DESTRUCTIVE KEYWORDS (chat messages) ─────────────────────────────────────

DESTRUCTIVE_KEYWORDS = [
    "delete", "clear", "remove", "reset", "erase",
    "wipe", "destroy", "purge", "drop", "overwrite"
]

# ─── CONTROL ACTION SAFETY ─────────────────────────────────────────────────────
# These control actions require explicit confirmation before executing.
# Maps action name → human-readable warning message.

DANGEROUS_CONTROL_ACTIONS = {
    "delete_file"    : "delete a file permanently",
    "delete_folder"  : "delete an entire folder and all its contents",
    "kill_process"   : "force-kill a running process",
    "close_window"   : "close an application window",
    "format_drive"   : "format a drive",
    "write_file"     : "overwrite file contents",
    "run_command"    : "execute a system command",
}

# These actions are always logged but never need confirmation
LOGGED_CONTROL_ACTIONS = {
    "open_app", "take_screenshot", "clipboard_write",
    "move_mouse", "click", "type_text", "hotkey",
    "open_url", "search_google", "send_notification",
    "create_file", "create_folder", "rename", "move", "copy",
    "list_directory", "read_file", "list_processes",
    "get_stats", "get_cpu", "get_ram", "get_disk",
}

# ─── SAFETY RESULT ─────────────────────────────────────────────────────────────

class SafetyResult:
    def __init__(self, is_safe: bool, reason: str = "", requires_confirmation: bool = False):
        self.is_safe               = is_safe
        self.reason                = reason
        self.requires_confirmation = requires_confirmation

    def __repr__(self):
        return f"<SafetyResult safe={self.is_safe} confirm={self.requires_confirmation}>"

# ─── MAIN SAFETY CHECK (chat messages) ────────────────────────────────────────

def check_message_safety(message: str) -> SafetyResult:
    """Run safety checks on an incoming user message."""
    message_lower = message.lower().strip()

    # Hard blocks
    for pattern in COMPILED_PATTERNS:
        if pattern.search(message_lower):
            log_control_action("blocked_message", message[:200], "hard_block", blocked=True)
            return SafetyResult(
                is_safe=False,
                reason=(
                    "I'm not able to help with that request. "
                    "It falls outside the boundaries of what ARIS is designed to assist with. "
                    "If you need help with something else, I'm here."
                )
            )

    # Destructive keywords in ASK mode
    if TRUST_LEVEL == TrustLevel.ASK:
        for keyword in DESTRUCTIVE_KEYWORDS:
            if keyword in message_lower:
                return SafetyResult(
                    is_safe=True,
                    requires_confirmation=True,
                    reason=(
                        f"This action contains '{keyword}' which could modify or remove data. "
                        f"Please confirm you want to proceed."
                    )
                )

    return SafetyResult(is_safe=True)


# ─── CONTROL ACTION SAFETY CHECK ──────────────────────────────────────────────

def check_control_action(action: str, params: dict = None,
                          confirmed: bool = False) -> SafetyResult:
    """
    Check if a control action is safe to execute.
    Dangerous actions require confirmed=True.
    All actions are logged to the audit DB.
    """
    params = params or {}

    # Always log the attempt
    log_control_action(
        action    = action,
        params    = str(params),
        result    = "pending",
        confirmed = confirmed,
        blocked   = False
    )

    # Dangerous actions need confirmation
    if action in DANGEROUS_CONTROL_ACTIONS and TRUST_LEVEL == TrustLevel.ASK:
        if not confirmed:
            description = DANGEROUS_CONTROL_ACTIONS[action]
            return SafetyResult(
                is_safe=True,
                requires_confirmation=True,
                reason=(
                    f"⚠️ ARIS wants to **{description}**.\n\n"
                    f"Parameters: `{params}`\n\n"
                    f"Reply **'yes, confirmed'** to proceed or **'cancel'** to abort."
                )
            )

    # Log as confirmed/executed
    log_control_action(
        action    = action,
        params    = str(params),
        result    = "executed",
        confirmed = confirmed or action not in DANGEROUS_CONTROL_ACTIONS,
        blocked   = False
    )

    return SafetyResult(is_safe=True)


def get_safety_config() -> dict:
    """Return current safety configuration."""
    return {
        "trust_level"                          : TRUST_LEVEL.value,
        "blocked_pattern_count"                : len(BLOCKED_PATTERNS),
        "destructive_keywords"                 : DESTRUCTIVE_KEYWORDS,
        "dangerous_control_actions"            : list(DANGEROUS_CONTROL_ACTIONS.keys()),
        "confirmation_required_for_destructive": TRUST_LEVEL == TrustLevel.ASK,
        "audit_log_path"                       : AUDIT_DB,
    }