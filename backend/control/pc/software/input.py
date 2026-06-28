# ARIS/control/pc/software/input.py
"""
Mouse & Keyboard Emulation module for ARIS — Windows 11
"""

import pyautogui

# ── Safety config ─────────────────────────────────────────────────────────────
pyautogui.PAUSE = 0.1
pyautogui.FAILSAFE = True

# ── Exception Wrapper Decorator ───────────────────────────────────────────────

def wrap_failsafe(func):
    """Decorator to catch PyAutoGUI FailSafeException and generic errors safely."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except pyautogui.FailSafeException:
            return {
                "action": func.__name__,
                "status": "error",
                "error": "PyAutoGUI FailSafe triggered. Cursor was moved to screen corner to abort command."
            }
        except Exception as e:
            return {
                "action": func.__name__,
                "status": "error",
                "error": str(e)
            }
    return wrapper

# ── Mouse control ─────────────────────────────────────────────────────────────

@wrap_failsafe
def move_mouse(x: int, y: int, duration: float = 0.3) -> dict:
    """Move mouse to absolute screen coordinates."""
    pyautogui.moveTo(x, y, duration=duration)
    return {"action": "move_mouse", "x": x, "y": y, "status": "ok"}


@wrap_failsafe
def click(x: int = None, y: int = None, button: str = "left", clicks: int = 1) -> dict:
    """Click at position (or current position if x/y not given)."""
    if x is not None and y is not None:
        pyautogui.click(x, y, button=button, clicks=clicks, interval=0.1)
    else:
        pyautogui.click(button=button, clicks=clicks, interval=0.1)
    return {"action": "click", "x": x, "y": y, "button": button, "clicks": clicks, "status": "ok"}


@wrap_failsafe
def double_click(x: int, y: int) -> dict:
    """Double-click at position."""
    pyautogui.doubleClick(x, y)
    return {"action": "double_click", "x": x, "y": y, "status": "ok"}


@wrap_failsafe
def right_click(x: int, y: int) -> dict:
    """Right-click at position."""
    pyautogui.rightClick(x, y)
    return {"action": "right_click", "x": x, "y": y, "status": "ok"}


@wrap_failsafe
def scroll(direction: str = "down", amount: int = 3) -> dict:
    """Scroll up or down."""
    clicks = -amount if direction == "down" else amount
    pyautogui.scroll(clicks)
    return {"action": "scroll", "direction": direction, "amount": amount, "status": "ok"}

# ── Keyboard control ──────────────────────────────────────────────────────────

@wrap_failsafe
def type_text(text: str, interval: float = 0.05) -> dict:
    """Type text at current cursor position."""
    pyautogui.typewrite(text, interval=interval)
    return {"action": "type_text", "text": text, "status": "ok"}


@wrap_failsafe
def press_key(key: str) -> dict:
    """Press a single key (e.g. 'enter', 'escape', 'f5')."""
    pyautogui.press(key)
    return {"action": "press_key", "key": key, "status": "ok"}


@wrap_failsafe
def hotkey(*keys: str) -> dict:
    """
    Press a key combination.
    Examples: hotkey('ctrl','c') | hotkey('alt','tab')
    """
    pyautogui.hotkey(*keys)
    return {"action": "hotkey", "keys": list(keys), "status": "ok"}
