# ARIS/control/pc/software/clipboard.py
"""
Clipboard management module for ARIS — Windows 11
"""

import pyperclip

def clipboard_read() -> dict:
    """Read current clipboard content."""
    try:
        content = pyperclip.paste()
        return {"action": "clipboard_read", "content": content, "status": "ok"}
    except Exception as e:
        return {"action": "clipboard_read", "status": "error", "error": str(e)}


def clipboard_write(text: str) -> dict:
    """Write text to clipboard."""
    try:
        pyperclip.copy(text)
        return {"action": "clipboard_write", "text": text, "status": "ok"}
    except Exception as e:
        return {"action": "clipboard_write", "status": "error", "error": str(e)}
