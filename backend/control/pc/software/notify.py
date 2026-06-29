# ARIS/control/pc/software/notify.py
"""
Desktop Notification module for ARIS — Windows 11
Uses plyer for native Windows toast notifications.
"""

import os
import threading
from plyer import notification
from datetime import datetime


# ── Suppress plyer balloon_tip thread crashes ─────────────────────────────────
# plyer spawns a background thread (balloon_tip) for Windows toast notifications.
# On some systems, Shell_NotifyIconW fails and raises an unhandled exception in
# that thread, spamming stderr with full tracebacks. These are non-fatal — the
# notification dispatch already succeeded or gracefully failed — so we silence them.
_original_excepthook = threading.excepthook

def _suppress_plyer_thread_crash(args):
    """Silently ignore exceptions from plyer's balloon_tip threads."""
    if args.thread and args.thread.name and "balloon_tip" in args.thread.name:
        # Silently ignore — this is a known plyer issue on Windows
        return
    # For all other threads, use the default handler
    _original_excepthook(args)

threading.excepthook = _suppress_plyer_thread_crash

# ── Notification history (in-memory log) ──────────────────────────────────────
_history: list[dict] = []


def send_notification(
    title: str,
    message: str,
    timeout: int = 5,
    app_name: str = "ARIS"
) -> dict:
    """
    Send a Windows desktop toast notification.
    timeout: seconds before it auto-dismisses (default 5)
    """
    try:
        notification.notify(
            title       = title,
            message     = message,
            app_name    = app_name,
            timeout     = timeout,
        )

        entry = {
            "title"    : title,
            "message"  : message,
            "app_name" : app_name,
            "timeout"  : timeout,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        _history.append(entry)

        return {
            "action" : "send_notification",
            "title"  : title,
            "message": message,
            "status" : "ok"
        }

    except Exception as e:
        return {"action": "send_notification", "status": "error", "error": str(e)}


def get_notification_history() -> dict:
    """Return all notifications sent this session."""
    return {
        "action" : "notification_history",
        "count"  : len(_history),
        "history": list(reversed(_history)),  # newest first
        "status" : "ok"
    }


def clear_notification_history() -> dict:
    """Clear the in-memory notification log."""
    _history.clear()
    return {"action": "clear_history", "status": "ok"}
