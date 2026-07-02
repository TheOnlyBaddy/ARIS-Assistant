# vision/screen.py
# ARIS Screen Vision
# Captures screenshot → sends to Gemini Vision → returns description
# Optimized: thinking_budget=0 reduces response time from ~40s to ~3-5s

import mss
import os
import time
from PIL import Image
import io
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# ── Setup Gemini Vision ───────────────────────────────────────
_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "gemini-3.5-flash")

VISION_MODELS = [
    PRIMARY_MODEL,
    "gemini-2.5-flash",       # Fallback
    "gemini-2.0-flash",       # Fallback
    "gemini-2.0-flash-lite",  # Cheapest fallback
]

# ── Config ────────────────────────────────────────────────────
SCREENSHOT_DIR = "vision/screenshots"
MAX_WIDTH      = 1280
JPEG_QUALITY   = 85
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

print(f"Gemini Vision ready ({PRIMARY_MODEL}, fast mode)")

# ── Capture screenshot ────────────────────────────────────────
def capture_screen(monitor_index: int = 1) -> tuple[Image.Image, str]:
    """
    Captures the full screen and saves as JPEG.
    monitor_index: 1 = primary, 2 = secondary monitor
    Returns (PIL Image, saved file path)
    """
    with mss.mss() as sct:
        monitors = sct.monitors
        if monitor_index >= len(monitors):
            monitor_index = 1
        monitor = monitors[monitor_index]
        raw     = sct.grab(monitor)
        img     = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    # Resize to MAX_WIDTH — saves tokens and speeds up API call
    if img.width > MAX_WIDTH:
        ratio  = MAX_WIDTH / img.width
        height = int(img.height * ratio)
        img    = img.resize((MAX_WIDTH, height), Image.LANCZOS)

    timestamp = int(time.time())
    path      = f"{SCREENSHOT_DIR}/screen_{timestamp}.jpg"
    img.save(path, "JPEG", quality=JPEG_QUALITY)
    return img, path

# ── Convert PIL image to bytes ────────────────────────────────
def _image_to_bytes(img: Image.Image) -> bytes:
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()

# ── Analyze screen with Gemini Vision ────────────────────────
def analyze_screen(prompt: str = None, monitor_index: int = 1) -> dict:
    """
    Captures screen and asks Gemini Vision to describe it.

    Args:
        prompt       : Custom question about the screen (optional)
        monitor_index: Which monitor to capture (default: primary)

    Returns dict with description, screenshot path, model used, timing.
    """
    print("Capturing screen...")
    img, path = capture_screen(monitor_index)
    print(f"   Screenshot: {img.width}x{img.height}px -> {path}")

    # Build prompt
    if not prompt:
        vision_prompt = (
            "You are ARIS, a personal AI assistant analyzing the user's screen. "
            "Describe what you see concisely and helpfully in 2-3 sentences. "
            "Focus on: what application is open, what content is visible, "
            "and anything that might help the user. "
            "Never address the user by name; always use 'boss' or 'sir'."
        )
    else:
        vision_prompt = (
            f"You are ARIS, a personal AI assistant analyzing the user's screen. "
            f"The user asks: '{prompt}'. "
            f"Answer based only on what you can see on the screen. "
            f"Be concise and direct. "
            f"Never address the user by name; always use 'boss' or 'sir'."
        )

    img_bytes = _image_to_bytes(img)

    # Try each model until one succeeds
    last_error = None
    for model_name in VISION_MODELS:
        try:
            print(f"Sending to {model_name}...")
            start = time.time()

            response = _client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    vision_prompt
                ],
                # thinking_budget=0 disables slow extended thinking mode
                # Reduces response time from ~40s to ~3-5s with same accuracy
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=0)
                )
            )

            elapsed     = time.time() - start
            description = response.text.strip()
            print(f"Vision response in {elapsed:.1f}s")

            return {
                "description" : description,
                "screenshot"  : path,
                "resolution"  : f"{img.width}x{img.height}",
                "elapsed_secs": round(elapsed, 2),
                "model_used"  : model_name,
            }

        except Exception as e:
            err_short = str(e)[:100]
            print(f"   {model_name} failed: {err_short}")
            last_error = e
            continue

    raise RuntimeError(f"All vision models failed. Last error: {last_error}")

# ── Quick one-liner for voice pipeline ───────────────────────
def describe_screen() -> str:
    """Returns just the text description — used by voice pipeline"""
    result = analyze_screen()
    return result["description"]