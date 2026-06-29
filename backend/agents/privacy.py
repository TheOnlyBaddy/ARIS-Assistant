"""
ARIS Full Offline & Privacy Module
- Manages encryption/decryption of database columns using Fernet
- Implements data retention policy (pruning old database entries)
- Manages configuration of PRIVACY_MODE in the .env file
"""

import os
import sqlite3
import dotenv
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(BASE_DIR)
ROOT_DIR = os.path.dirname(BACKEND_DIR)
ENV_PATH = os.path.join(ROOT_DIR, ".env")
if not os.path.exists(ENV_PATH):
    ENV_PATH = os.path.join(BACKEND_DIR, ".env")
DB_PATH  = os.path.join(BACKEND_DIR, "aris.db")

# ─── ENCRYPTION CORE ──────────────────────────────────────────────────────────

def get_or_create_key() -> str:
    """Load or generate a Fernet encryption key, persisting it to .env."""
    dotenv.load_dotenv(ENV_PATH)
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        key = Fernet.generate_key().decode()
        # Save key to .env
        set_env_variable("ENCRYPTION_KEY", key)
    return key


def set_env_variable(key: str, value: str):
    """Write or update a configuration variable in the .env file."""
    lines = []
    found = False
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    for idx, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[idx] = f"{key}={value}\n"
            found = True
            break

    if not found:
        lines.append(f"{key}={value}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # Force reload os.environ
    os.environ[key] = value
    dotenv.load_dotenv(ENV_PATH)


# Initialize key
ENCRYPTION_KEY = get_or_create_key()
fernet = Fernet(ENCRYPTION_KEY.encode())


def encrypt_text(text: str) -> str:
    """Encrypt plain text. Returns encrypted text with 'ENC:' prefix."""
    if not text:
        return text
    try:
        encrypted = fernet.encrypt(text.encode()).decode()
        return f"ENC:{encrypted}"
    except Exception:
        return text


def decrypt_text(text: str) -> str:
    """Decrypt text if it has the 'ENC:' prefix, otherwise return unchanged."""
    if not text or not text.startswith("ENC:"):
        return text
    try:
        encrypted_part = text[4:]
        decrypted = fernet.decrypt(encrypted_part.encode()).decode()
        return decrypted
    except Exception as e:
        print(f"[ARIS Privacy] Decryption failed: {e}")
        return "[Decryption Failed]"


# ─── DATA RETENTION POLICY ────────────────────────────────────────────────────

def enforce_data_retention() -> int:
    """Prune conversation messages older than N days from the database."""
    dotenv.load_dotenv(ENV_PATH)
    retention_days_str = os.getenv("DATA_RETENTION_DAYS", "30")
    try:
        days = int(retention_days_str)
    except ValueError:
        days = 30

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = cutoff.isoformat()

    conn = sqlite3.connect(DB_PATH)
    try:
        # SQLite store handles dates as text (ISO format)
        cur = conn.execute(
            "DELETE FROM conversation_messages WHERE timestamp < ?",
            (cutoff_str,)
        )
        deleted_count = cur.rowcount
        conn.commit()
        if deleted_count > 0:
            print(f"[ARIS Privacy] Data retention policy deleted {deleted_count} messages older than {days} days.")
        return deleted_count
    except Exception as e:
        print(f"[ARIS Privacy] Data retention pruning failed: {e}")
        return 0
    finally:
        conn.close()


def update_privacy_settings(privacy_mode: bool, retention_days: int) -> dict:
    """Update settings in .env and run data retention pruning."""
    set_env_variable("PRIVACY_MODE", "true" if privacy_mode else "false")
    set_env_variable("DATA_RETENTION_DAYS", str(retention_days))
    
    # Prune database
    pruned = enforce_data_retention()

    return {
        "status": "success",
        "privacy_mode": privacy_mode,
        "retention_days": retention_days,
        "messages_pruned": pruned
    }


def get_privacy_settings() -> dict:
    """Retrieve current privacy configuration."""
    dotenv.load_dotenv(ENV_PATH)
    is_private = os.getenv("PRIVACY_MODE", "false").lower() == "true"
    retention_days = int(os.getenv("DATA_RETENTION_DAYS", "30"))
    return {
        "privacy_mode": is_private,
        "retention_days": retention_days
    }
