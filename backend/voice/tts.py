# voice/tts.py
# ARIS Text-to-Speech Engine
# Primary : Kokoro (local, high quality, unlimited, free)
# Fallback : pyttsx3 (Windows built-in, always works)

import threading
import numpy as np
import sounddevice as sd
import pyttsx3

# ── Config ─────────────────────────────────────────────────
KOKORO_VOICE     = 'af_heart'  # Female American — natural and clear
KOKORO_SPEED     = 1.0         # 1.0 = normal, 1.2 = slightly faster
LOCAL_VOICE_IDX  = 1           # Windows Zira fallback
LOCAL_VOICE_RATE = 175
# ───────────────────────────────────────────────────────────

# ── Auto-detect output device (survives Windows device reshuffles) ──────────
def _get_output_device():
    """
    Finds best output device by matching system default first,
    then falling back to keyword search.
    """
    devices = sd.query_devices()

    # Strategy 1: Match the system default output by name
    # This is the most reliable — Windows knows which device is active
    try:
        default = sd.query_devices(kind='output')
        default_name = default['name'].lower()
        for i, d in enumerate(devices):
            if (d['max_output_channels'] > 0 and
                d['name'].lower() == default['name'].lower()):
                print(f"✅ Audio output auto-selected: [{i}] {d['name']}")
                return i
    except Exception:
        pass

    # Strategy 2: Keyword priority search (skip known bad devices)
    skip_keywords = ['2nd', 'nahimic', 'osmo', 'pc speaker', 'hdmi', 'surround']
    priority_keywords = [
        ('nirvana',),               # Nirvana Ion ANC (your current headphones)
        ('kreo',),                  # Kreo Sonik headset
        ('realtek', 'headphone'),
        ('headphone',),
        ('speaker',),
    ]
    for keywords in priority_keywords:
        for i, d in enumerate(devices):
            if d['max_output_channels'] > 0:
                name_lower = d['name'].lower()
                if any(skip in name_lower for skip in skip_keywords):
                    continue
                if all(kw in name_lower for kw in keywords):
                    print(f"✅ Audio output auto-selected: [{i}] {d['name']}")
                    return i

    print("✅ Audio output: system default")
    return None

OUTPUT_DEVICE = _get_output_device()

# ── TTS state — readable by voice pipeline & FastAPI ───────
tts_state = {"engine": "none", "speaking": False}

# ── pyttsx3 local engine (init once at startup) ─────────────
_local_engine = pyttsx3.init()
_voices = _local_engine.getProperty('voices')
if len(_voices) > LOCAL_VOICE_IDX:
    _local_engine.setProperty('voice', _voices[LOCAL_VOICE_IDX].id)
    print(f"✅ Local TTS (pyttsx3) ready: {_voices[LOCAL_VOICE_IDX].name}")
else:
    print("✅ Local TTS (pyttsx3) ready: default voice")
_local_engine.setProperty('rate', LOCAL_VOICE_RATE)
_local_engine.setProperty('volume', 1.0)

# ── Kokoro engine (lazy load — only loads when first used) ──
_kokoro_pipeline = None

def _get_kokoro():
    """Load Kokoro pipeline once, reuse forever"""
    global _kokoro_pipeline
    if _kokoro_pipeline is None:
        try:
            from kokoro import KPipeline
            print("⏳ Loading Kokoro TTS model...")
            _kokoro_pipeline = KPipeline(lang_code='a')
            print("✅ Kokoro TTS ready")
        except Exception as e:
            print(f"⚠️  Kokoro load failed: {e}")
            return None
    return _kokoro_pipeline

# ── Kokoro speak ────────────────────────────────────────────
def _speak_kokoro(text: str) -> bool:
    """
    Speak via Kokoro local TTS.
    Returns True if successful, False if any error (triggers fallback).
    """
    pipeline = _get_kokoro()
    if not pipeline:
        return False

    try:
        generator = pipeline(text, voice=KOKORO_VOICE, speed=KOKORO_SPEED)

        audio_chunks = []
        for _, _, audio in generator:
            audio_chunks.append(audio)

        if not audio_chunks:
            print("⚠️  Kokoro returned empty audio")
            return False

        audio_data = np.concatenate(audio_chunks)
        tts_state["speaking"] = True
        tts_state["engine"]   = "kokoro"

        sd.play(audio_data, samplerate=24000, device=OUTPUT_DEVICE)
        sd.wait()
        return True

    except Exception as e:
        print(f"⚠️  Kokoro error: {e} — falling back to pyttsx3")
        return False

# ── pyttsx3 fallback ────────────────────────────────────────
def _speak_local(text: str):
    """Always-available Windows TTS — no limits, no dependencies"""
    tts_state["speaking"] = True
    tts_state["engine"]   = "local"
    _local_engine.say(text)
    _local_engine.runAndWait()

# ── Public API — all ARIS modules use these ─────────────────
def speak(text: str, force_local: bool = False):
    """
    Main speak function for all of ARIS.
    Tries Kokoro first (high quality), falls back to pyttsx3 automatically.

    Args:
        text:        What ARIS should say
        force_local: Skip Kokoro and go straight to pyttsx3
    """
    if not text or not text.strip():
        return

    tts_state["speaking"] = False
    print(f'\n🔊 ARIS: "{text[:80]}{"..." if len(text) > 80 else ""}"')

    if not force_local:
        success = _speak_kokoro(text)
        if success:
            tts_state["speaking"] = False
            return

    # Kokoro failed or force_local=True — use pyttsx3
    _speak_local(text)
    tts_state["speaking"] = False

def speak_async(text: str, force_local: bool = False):
    """
    Non-blocking speak — runs in a background thread.
    Use this in the voice pipeline so FastAPI stays responsive.

    Returns the thread object (you can call .join() if you need to wait).
    """
    t = threading.Thread(target=speak, args=(text, force_local), daemon=True)
    t.start()
    return t

def get_tts_status() -> dict:
    """Returns current TTS engine and speaking state — used by /voice/status"""
    return {
        "speaking": tts_state["speaking"],
        "engine":   tts_state["engine"],
        "output_device": OUTPUT_DEVICE
    }