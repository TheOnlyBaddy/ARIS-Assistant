# ARIS/control/pc/software/window.py
"""
Window Management and Layout Snapping module for ARIS — Windows 11
"""

import os
from datetime import datetime
import win32gui
import win32con
import win32process
import psutil
import pyautogui

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
                try:
                    win32gui.SetForegroundWindow(hwnd)
                    found.append(title)
                except Exception:
                    # Occasional Win32 exceptions if thread doesn't own focus
                    pass

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


def snap_window(direction: str) -> dict:
    """
    Snap the current foreground window to the left or right half of the screen.
    direction: 'left' | 'right'
    """
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return {"action": "snap_window", "status": "error", "error": "No active window found."}

        width, height = pyautogui.size()
        half_width = width // 2

        # SW_SHOWNORMAL restores the window if minimized or maximized
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNORMAL)

        # MoveWindow(hwnd, x, y, width, height, repaint)
        # Note: height - 45 leaves space for standard Windows taskbar
        if direction.lower() == "left":
            win32gui.MoveWindow(hwnd, 0, 0, half_width, height - 45, True)
        elif direction.lower() == "right":
            win32gui.MoveWindow(hwnd, half_width, 0, half_width, height - 45, True)
        else:
            return {"action": "snap_window", "status": "error", "error": f"Invalid direction '{direction}'. Use 'left' or 'right'."}

        title = win32gui.GetWindowText(hwnd)
        return {"action": "snap_window", "window": title, "direction": direction, "status": "ok"}
    except Exception as e:
        return {"action": "snap_window", "status": "error", "error": str(e)}

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "vision", "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

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

