# ARIS/control/pc/software/notify.py
"""
Desktop Notification module for ARIS — Windows 11
Uses plyer for native Windows toast notifications.
"""

import os
from plyer import notification
from datetime import datetime

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
