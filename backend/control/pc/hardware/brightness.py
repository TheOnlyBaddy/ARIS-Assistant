# ARIS/control/pc/hardware/brightness.py
"""
Screen Brightness Control module for ARIS — Windows 11
"""

import subprocess

def set_brightness(level: int) -> dict:
    """
    Set screen brightness to a level from 0 to 100 using Windows PowerShell WMI.
    """
    try:
        level_val = int(level)
    except (ValueError, TypeError):
        return {"action": "set_brightness", "status": "error", "error": "Brightness level must be an integer."}

    if level_val < 0 or level_val > 100:
        return {"action": "set_brightness", "status": "error", "error": "Brightness level must be between 0 and 100."}

    try:
        # Run PowerShell command in the background
        cmd = f"powershell -Command \"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {level_val})\""
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"action": "set_brightness", "level": level_val, "status": "ok"}
    except Exception as e:
        return {"action": "set_brightness", "status": "error", "error": str(e)}
