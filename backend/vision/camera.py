# vision/camera.py
# ARIS Camera Vision
# Captures webcam frame → sends to Gemini Vision → returns description
# Triggered by voice: "ARIS what do you see?" or /vision/camera endpoint

import os
import time
from PIL import Image
import io
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

_cv2 = None


def _get_cv2():
    """Lazy-load OpenCV to avoid DLL conflicts with audio libs at import time."""
    global _cv2
    if _cv2 is None:
        try:
            import cv2
            _cv2 = cv2
        except ImportError as e:
            raise RuntimeError(
                "OpenCV (cv2) failed to load. Camera features are unavailable. "
                "Try: pip uninstall opencv-python -y && pip install opencv-python"
            ) from e
    return _cv2

# ── Setup Gemini Vision ───────────────────────────────────────
_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

VISION_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]

# ── Config ────────────────────────────────────────────────────
CAMERA_DIR   = "vision/camera_shots"
JPEG_QUALITY = 90       # Higher quality for camera — details matter
CAMERA_INDEX = 0        # 0 = first camera, 1 = second camera
WARMUP_FRAMES = 5       # Discard first N frames — camera needs to adjust exposure
os.makedirs(CAMERA_DIR, exist_ok=True)

print("✅ Camera Vision module ready")

# ── Find available cameras ────────────────────────────────────
def list_cameras() -> list[int]:
    """Returns list of available camera indices"""
    cv2 = _get_cv2()
    available = []
    for i in range(5):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)  # CAP_DSHOW = Windows DirectShow
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                available.append(i)
            cap.release()
    return available

# ── Capture camera frame ──────────────────────────────────────
def capture_frame(camera_index: int = None) -> tuple[Image.Image, str]:
    """
    Captures a single frame from the webcam.
    Auto-detects camera if index not specified.
    Returns (PIL Image, saved file path)
    """
    if camera_index is None:
        camera_index = CAMERA_INDEX

    cv2 = _get_cv2()
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)

    if not cap.isOpened():
        # Try next camera index
        cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
        if not cap.isOpened():
            raise RuntimeError(
                f"Could not open camera {camera_index}. "
                "Check USB webcam is connected and not used by another app."
            )

    # Set resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # Warmup — discard first N frames so exposure adjusts
    print(f"   📷 Camera warming up ({WARMUP_FRAMES} frames)...")
    for _ in range(WARMUP_FRAMES):
        cap.read()

    # Capture the actual frame
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError("Camera capture failed — got empty frame")

    # Convert BGR (OpenCV) → RGB (PIL)
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img       = Image.fromarray(frame_rgb)

    # Save to disk
    timestamp = int(time.time())
    path      = f"{CAMERA_DIR}/camera_{timestamp}.jpg"
    img.save(path, "JPEG", quality=JPEG_QUALITY)

    return img, path

# ── Convert PIL image to bytes ────────────────────────────────
def _image_to_bytes(img: Image.Image) -> bytes:
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()

# ── Analyze camera frame with Gemini Vision ───────────────────
def analyze_camera(prompt: str = None, camera_index: int = None) -> dict:
    """
    Captures webcam frame and asks Gemini Vision to describe the scene.

    Args:
        prompt      : Custom question about what the camera sees
        camera_index: Which camera to use (default: auto-detect)

    Returns dict with description, image path, model used, timing.
    """
    print("📷 Capturing from webcam...")
    img, path = capture_frame(camera_index)
    print(f"   Frame: {img.width}x{img.height}px → {path}")

    # Build prompt
    if not prompt:
        vision_prompt = (
            "You are ARIS, a personal AI assistant with camera vision. "
            "Describe what you see through the camera concisely in 2-3 sentences. "
            "Focus on: people present, objects, environment, and anything notable."
        )
    else:
        vision_prompt = (
            f"You are ARIS, a personal AI assistant with camera vision. "
            f"The user asks: '{prompt}'. "
            f"Answer based on what you can see through the camera."
        )

    img_bytes = _image_to_bytes(img)

    last_error = None
    for model_name in VISION_MODELS:
        try:
            print(f"🔍 Sending to {model_name}...")
            start = time.time()

            response = _client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    vision_prompt
                ],
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=0)
                )
            )

            elapsed     = time.time() - start
            description = response.text.strip()
            print(f"✅ Camera vision response in {elapsed:.1f}s")

            return {
                "description" : description,
                "image_path"  : path,
                "resolution"  : f"{img.width}x{img.height}",
                "elapsed_secs": round(elapsed, 2),
                "model_used"  : model_name,
                "camera_index": camera_index or CAMERA_INDEX,
            }

        except Exception as e:
            print(f"   ⚠️  {model_name} failed: {str(e)[:100]}")
            last_error = e
            continue

    raise RuntimeError(f"All vision models failed. Last error: {last_error}")

# ── Quick one-liner for voice pipeline ───────────────────────
def describe_camera() -> str:
    """Returns just the text description — used by voice pipeline"""
    result = analyze_camera()
    return result["description"]