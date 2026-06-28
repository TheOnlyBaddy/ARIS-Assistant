# ARIS/control/pc/hardware/media.py
"""
Volume & Media Playback Control module for ARIS — Windows 11
"""

import pyautogui
from pycaw.pycaw import AudioUtilities

def _get_volume_interface():
    device = AudioUtilities.GetSpeakers()
    return device.EndpointVolume

def media_control(action: str, level: int = None) -> dict:
    """
    Control system volume and media playback.
    action: 'play' | 'pause' | 'next' | 'prev' | 'mute' | 'vol_up' | 'vol_down' | 'set_volume'
    """
    act = action.lower().strip()

    # Playback controls still use pyautogui as WASAPI doesn't control player apps directly
    if act in ("play", "pause"):
        pyautogui.press("playpause")
        return {"action": "media_control", "sub_action": "playpause", "status": "ok"}
    elif act == "next":
        pyautogui.press("nexttrack")
        return {"action": "media_control", "sub_action": "nexttrack", "status": "ok"}
    elif act == "prev":
        pyautogui.press("prevtrack")
        return {"action": "media_control", "sub_action": "prevtrack", "status": "ok"}

    # Volume controls use pycaw for silent, instant, absolute precision
    try:
        volume = _get_volume_interface()
        
        if act == "mute":
            volume.SetMute(True, None)
            return {"action": "media_control", "sub_action": "mute", "status": "ok"}
            
        elif act == "unmute":
            volume.SetMute(False, None)
            return {"action": "media_control", "sub_action": "unmute", "status": "ok"}

        elif act == "toggle_mute":
            current_mute = volume.GetMute()
            volume.SetMute(1 - current_mute, None)
            return {"action": "media_control", "sub_action": "toggle_mute", "status": "ok"}
            
        elif act == "vol_up":
            current_val = volume.GetMasterVolumeLevelScalar()
            # Raise volume by 10% (0.1)
            new_val = min(current_val + 0.1, 1.0)
            volume.SetMasterVolumeLevelScalar(new_val, None)
            return {"action": "media_control", "sub_action": "vol_up", "status": "ok"}
            
        elif act == "vol_down":
            current_val = volume.GetMasterVolumeLevelScalar()
            # Lower volume by 10% (0.1)
            new_val = max(current_val - 0.1, 0.0)
            volume.SetMasterVolumeLevelScalar(new_val, None)
            return {"action": "media_control", "sub_action": "vol_down", "status": "ok"}
            
        elif act == "set_volume":
            if level is None:
                return {"action": "media_control", "status": "error", "error": "Level must be provided for set_volume."}
            try:
                level_val = int(level)
            except (ValueError, TypeError):
                return {"action": "media_control", "status": "error", "error": "Volume level must be an integer."}
            
            if level_val < 0 or level_val > 100:
                return {"action": "media_control", "status": "error", "error": "Volume level must be between 0 and 100."}
            
            # Set absolute volume level (0.0 to 1.0)
            volume.SetMasterVolumeLevelScalar(level_val / 100.0, None)
            return {"action": "media_control", "sub_action": "set_volume", "level": level_val, "status": "ok"}
            
        else:
            return {"action": "media_control", "status": "error", "error": f"Unknown action '{action}'."}
            
    except Exception as e:
        return {"action": "media_control", "status": "error", "error": f"Failed to access system audio interface: {e}"}
