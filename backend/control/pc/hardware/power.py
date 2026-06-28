# ARIS/control/pc/hardware/power.py
"""
Power Management Control module for ARIS — Windows 11
"""

import subprocess

def lock_pc() -> dict:
    """Lock the Windows workstation."""
    try:
        subprocess.Popen("rundll32.exe user32.dll,LockWorkStation", shell=True)
        return {"action": "power_control", "sub_action": "lock", "status": "ok"}
    except Exception as e:
        return {"action": "power_control", "status": "error", "error": str(e)}


def sleep_pc() -> dict:
    """Put the PC to sleep."""
    try:
        subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
        return {"action": "power_control", "sub_action": "sleep", "status": "ok"}
    except Exception as e:
        return {"action": "power_control", "status": "error", "error": str(e)}


def shutdown_pc(confirmed: bool = False) -> dict:
    """
    Shut down the PC in 60 seconds.
    Guarded by confirmation.
    """
    if not confirmed:
        return {
            "status"    : "needs_confirmation",
            "message"   : "Are you sure you want to shut down your PC? Pass confirmed=true to proceed.",
            "sub_action": "shutdown"
        }

    try:
        subprocess.Popen("shutdown /s /t 60 /c \"ARIS triggered shutdown\"", shell=True)
        return {
            "action"    : "power_control",
            "sub_action": "shutdown",
            "status"    : "ok",
            "message"   : "PC shutting down in 60 seconds. Use 'cancel' or 'abort' to stop."
        }
    except Exception as e:
        return {"action": "power_control", "status": "error", "error": str(e)}


def restart_pc(confirmed: bool = False) -> dict:
    """
    Restart the PC in 60 seconds.
    Guarded by confirmation.
    """
    if not confirmed:
        return {
            "status"    : "needs_confirmation",
            "message"   : "Are you sure you want to restart your PC? Pass confirmed=true to proceed.",
            "sub_action": "restart"
        }

    try:
        subprocess.Popen("shutdown /r /t 60 /c \"ARIS triggered restart\"", shell=True)
        return {
            "action"    : "power_control",
            "sub_action": "restart",
            "status"    : "ok",
            "message"   : "PC restarting in 60 seconds. Use 'cancel' or 'abort' to stop."
        }
    except Exception as e:
        return {"action": "power_control", "status": "error", "error": str(e)}


def cancel_shutdown() -> dict:
    """Cancel a pending shutdown or restart command."""
    try:
        subprocess.Popen("shutdown /a", shell=True)
        return {
            "action"    : "power_control",
            "sub_action": "cancel",
            "status"    : "ok",
            "message"   : "Pending shutdown or restart has been cancelled."
        }
    except Exception as e:
        return {"action": "power_control", "status": "error", "error": str(e)}
