# ARIS/control/pc/software/app.py
"""
App Launching module for ARIS — Windows 11
"""

import os
import subprocess
import time
import winreg
import shutil

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


def resolve_app_path(executable: str) -> str:
    """Look up the absolute path of an executable in the Windows Registry App Paths."""
    if not executable.endswith(".exe") and not executable.startswith("ms-"):
        executable += ".exe"

    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            key_path = f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{executable}"
            with winreg.OpenKey(root, key_path) as key:
                path, _ = winreg.QueryValueEx(key, "")
                if path:
                    path = path.strip('"')
                    if os.path.exists(path):
                        return path
        except FileNotFoundError:
            continue
        except Exception:
            continue
    return None


def open_app(app_name: str) -> dict:
    """
    Open an application by name.
    Looks up APP_MAP first, resolves absolute path via registry or PATH, then launches it.
    """
    name_lower = app_name.lower().strip()
    executable = APP_MAP.get(name_lower, app_name)

    try:
        # ms-settings: and similar URI schemes need ShellExecute
        if executable.startswith("ms-") or (":" in executable and not os.path.exists(executable)):
            os.startfile(executable)
            resolved_path = executable
        else:
            # Check if path exists directly (absolute or relative)
            if os.path.exists(executable):
                resolved_path = os.path.abspath(executable)
            else:
                resolved_path = resolve_app_path(executable)

            # Check shutil.which as fallback
            if not resolved_path:
                resolved_path = shutil.which(executable)
            if not resolved_path and not executable.endswith(".exe"):
                resolved_path = shutil.which(executable + ".exe")

            if resolved_path:
                cmd = f'"{resolved_path}"' if " " in resolved_path and not resolved_path.startswith('"') else resolved_path
                subprocess.Popen(cmd, shell=True)
            else:
                return {
                    "action": "open_app",
                    "app": app_name,
                    "status": "error",
                    "error": f"Application '{app_name}' not found on this system."
                }

        time.sleep(1)  # Give app time to open
        return {"action": "open_app", "app": app_name, "executable": resolved_path, "status": "ok"}

    except Exception as e:
        return {"action": "open_app", "app": app_name, "status": "error", "error": str(e)}
