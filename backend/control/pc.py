# ARIS/control/pc.py
"""
PC Control module for ARIS — Windows 11
Handles: mouse, keyboard, app launch, window management, screenshots, clipboard
"""

import pyautogui
import subprocess
import os
import time
import win32gui
import win32con
import win32process
import psutil
import pyperclip
from datetime import datetime

# ── Safety config ─────────────────────────────────────────────────────────────
# Prevents mouse flying to corner and crashing — 0.1s pause between actions
pyautogui.PAUSE = 0.1
# Move to top-left corner to abort if something goes wrong
pyautogui.FAILSAFE = True

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "vision", "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# ── Common app name → executable mapping ──────────────────────────────────────
APP_MAP = {
    "notepad"       : "notepad.exe",
    "chrome"        : "chrome.exe",
    "google chrome" : "chrome.exe",
    "firefox"       : "firefox.exe",
    "edge"          : "msedge.exe",
    "microsoft edge": "msedge.exe",
    "explorer"      : "explorer.exe",
    "file explorer" : "explorer.exe",
    "calculator"    : "calc.exe",
    "paint"         : "mspaint.exe",
    "cmd"           : "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell"    : "powershell.exe",
    "spotify"       : "spotify.exe",
    "discord"       : "discord.exe",
    "vs code"       : "code.exe",
    "vscode"        : "code.exe",
    "visual studio code": "code.exe",
    "word"          : "winword.exe",
    "excel"         : "excel.exe",
    "task manager"  : "taskmgr.exe",
    "snipping tool" : "SnippingTool.exe",
    "settings"      : "ms-settings:",
    "control panel" : "control.exe",
}

# ── Mouse control ─────────────────────────────────────────────────────────────

def move_mouse(x: int, y: int, duration: float = 0.3) -> dict:
    """Move mouse to absolute screen coordinates."""
    pyautogui.moveTo(x, y, duration=duration)
    return {"action": "move_mouse", "x": x, "y": y, "status": "ok"}


def click(x: int = None, y: int = None, button: str = "left", clicks: int = 1) -> dict:
    """Click at position (or current position if x/y not given)."""
    if x is not None and y is not None:
        pyautogui.click(x, y, button=button, clicks=clicks, interval=0.1)
    else:
        pyautogui.click(button=button, clicks=clicks, interval=0.1)
    return {"action": "click", "x": x, "y": y, "button": button, "clicks": clicks, "status": "ok"}


def double_click(x: int, y: int) -> dict:
    """Double-click at position."""
    pyautogui.doubleClick(x, y)
    return {"action": "double_click", "x": x, "y": y, "status": "ok"}


def right_click(x: int, y: int) -> dict:
    """Right-click at position."""
    pyautogui.rightClick(x, y)
    return {"action": "right_click", "x": x, "y": y, "status": "ok"}


def scroll(direction: str = "down", amount: int = 3) -> dict:
    """Scroll up or down."""
    clicks = -amount if direction == "down" else amount
    pyautogui.scroll(clicks)
    return {"action": "scroll", "direction": direction, "amount": amount, "status": "ok"}

# ── Keyboard control ──────────────────────────────────────────────────────────

def type_text(text: str, interval: float = 0.05) -> dict:
    """Type text at current cursor position."""
    pyautogui.typewrite(text, interval=interval)
    return {"action": "type_text", "text": text, "status": "ok"}


def press_key(key: str) -> dict:
    """Press a single key (e.g. 'enter', 'escape', 'f5')."""
    pyautogui.press(key)
    return {"action": "press_key", "key": key, "status": "ok"}


def hotkey(*keys: str) -> dict:
    """
    Press a key combination.
    Examples: hotkey('ctrl','c') | hotkey('alt','tab') | hotkey('ctrl','shift','esc')
    """
    pyautogui.hotkey(*keys)
    return {"action": "hotkey", "keys": list(keys), "status": "ok"}

# ── App control ───────────────────────────────────────────────────────────────

def open_app(app_name: str) -> dict:
    """
    Open an application by name.
    Looks up APP_MAP first, then tries running the name directly.
    """
    name_lower = app_name.lower().strip()
    executable = APP_MAP.get(name_lower, app_name)

    try:
        # ms-settings: and similar URI schemes need ShellExecute
        if executable.startswith("ms-"):
            os.startfile(executable)
        else:
            subprocess.Popen(executable, shell=True)

        time.sleep(1)  # Give app time to open
        return {"action": "open_app", "app": app_name, "executable": executable, "status": "ok"}

    except Exception as e:
        return {"action": "open_app", "app": app_name, "status": "error", "error": str(e)}


def close_window(title_contains: str) -> dict:
    """Close a window whose title contains the given string."""
    closed = []

    def enum_handler(hwnd, ctx):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title_contains.lower() in title.lower():
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                closed.append(title)

    win32gui.EnumWindows(enum_handler, None)

    if closed:
        return {"action": "close_window", "closed": closed, "status": "ok"}
    return {"action": "close_window", "status": "not_found", "searched_for": title_contains}


def minimize_window(title_contains: str) -> dict:
    """Minimize a window whose title contains the given string."""
    found = []

    def enum_handler(hwnd, ctx):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title_contains.lower() in title.lower():
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                found.append(title)

    win32gui.EnumWindows(enum_handler, None)

    if found:
        return {"action": "minimize_window", "minimized": found, "status": "ok"}
    return {"action": "minimize_window", "status": "not_found", "searched_for": title_contains}


def maximize_window(title_contains: str) -> dict:
    """Maximize a window whose title contains the given string."""
    found = []

    def enum_handler(hwnd, ctx):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title_contains.lower() in title.lower():
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                found.append(title)

    win32gui.EnumWindows(enum_handler, None)

    if found:
        return {"action": "maximize_window", "maximized": found, "status": "ok"}
    return {"action": "maximize_window", "status": "not_found", "searched_for": title_contains}


def focus_window(title_contains: str) -> dict:
    """Bring a window to front by partial title match."""
    found = []

    def enum_handler(hwnd, ctx):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title_contains.lower() in title.lower():
                win32gui.SetForegroundWindow(hwnd)
                found.append(title)

    win32gui.EnumWindows(enum_handler, None)

    if found:
        return {"action": "focus_window", "focused": found, "status": "ok"}
    return {"action": "focus_window", "status": "not_found", "searched_for": title_contains}


def list_open_windows() -> dict:
    """List all visible open windows."""
    windows = []

    def enum_handler(hwnd, ctx):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                windows.append(title)

    win32gui.EnumWindows(enum_handler, None)
    return {"action": "list_windows", "windows": windows, "count": len(windows), "status": "ok"}

# ── Screenshot ────────────────────────────────────────────────────────────────

def take_screenshot(filename: str = None) -> dict:
    """Take a screenshot and save it. Returns the file path."""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"

    path = os.path.join(SCREENSHOT_DIR, filename)
    screenshot = pyautogui.screenshot()
    screenshot.save(path)

    return {
        "action"  : "screenshot",
        "filename": filename,
        "path"    : path,
        "url"     : f"/vision/image/{filename}",
        "status"  : "ok"
    }

# ── Clipboard ─────────────────────────────────────────────────────────────────

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