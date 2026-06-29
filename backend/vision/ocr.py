# vision/ocr.py
# ARIS OCR — reads text from screen or camera using Gemini Vision
# No Tesseract needed — Gemini handles text extraction accurately
# Works with: printed text, handwriting, code, receipts, documents

import os
import time
from PIL import Image
import io
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "gemini-3.5-flash")

VISION_MODELS = [
    PRIMARY_MODEL,
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]

JPEG_QUALITY = 95   # High quality for OCR — text clarity matters
OCR_DIR      = "vision/ocr_shots"
os.makedirs(OCR_DIR, exist_ok=True)

print("OCR module ready (Gemini Vision)")

# ── Convert PIL image to bytes ────────────────────────────────
def _image_to_bytes(img: Image.Image) -> bytes:
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()

# ── Core OCR function ─────────────────────────────────────────
def _run_ocr(img: Image.Image, mode: str = "extract", context: str = "") -> dict:
    """
    Internal OCR runner.
    mode: "extract" | "summarize" | "translate" | "answer"
    """
    # Save image
    timestamp = int(time.time())
    path      = f"{OCR_DIR}/ocr_{timestamp}.jpg"
    img.save(path, "JPEG", quality=JPEG_QUALITY)

    # Build prompt based on mode
    prompts = {
        "extract": (
            "Extract ALL text visible in this image exactly as written. "
            "Preserve formatting where possible. "
            "If no text is visible, say 'No text found'."
        ),
        "summarize": (
            "Extract the text from this image and provide a concise summary "
            "of what it says. Focus on the key information."
        ),
        "translate": (
            f"Extract the text from this image and translate it to English. "
            f"Show both original and translation."
        ),
        "answer": (
            f"Look at the text in this image and answer this question: {context}. "
            f"Base your answer only on what you can read in the image."
        ),
    }

    ocr_prompt = prompts.get(mode, prompts["extract"])
    img_bytes  = _image_to_bytes(img)

    last_error = None
    for model_name in VISION_MODELS:
        try:
            start = time.time()
            response = _client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    ocr_prompt
                ],
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=0)
                )
            )
            elapsed = time.time() - start
            text    = response.text.strip()

            return {
                "text"        : text,
                "mode"        : mode,
                "image_path"  : path,
                "resolution"  : f"{img.width}x{img.height}",
                "elapsed_secs": round(elapsed, 2),
                "model_used"  : model_name,
            }

        except Exception as e:
            print(f"   {model_name} failed: {str(e)[:80]}")
            last_error = e
            continue

    raise RuntimeError(f"OCR failed. Last error: {last_error}")

# ── OCR from screen ───────────────────────────────────────────
def ocr_screen(mode: str = "extract", question: str = "") -> dict:
    """
    Captures screen and extracts text.
    mode: "extract" | "summarize" | "answer"
    question: used when mode="answer"
    """
    from vision.screen import capture_screen
    print("Capturing screen for OCR...")
    img, _ = capture_screen()
    print(f"   Image: {img.width}x{img.height}px")
    print(f"   Mode : {mode}")
    return _run_ocr(img, mode=mode, context=question)

# ── OCR from camera ───────────────────────────────────────────
def ocr_camera(mode: str = "extract", question: str = "") -> dict:
    """
    Captures webcam frame and extracts text.
    Point camera at document, book, whiteboard, receipt etc.
    mode: "extract" | "summarize" | "translate" | "answer"
    question: used when mode="answer"
    """
    from vision.camera import capture_frame
    print("Capturing camera frame for OCR...")
    img, _ = capture_frame()
    print(f"   Image: {img.width}x{img.height}px")
    print(f"   Mode : {mode}")
    return _run_ocr(img, mode=mode, context=question)

# ── OCR from file ─────────────────────────────────────────────
def ocr_file(image_path: str, mode: str = "extract", question: str = "") -> dict:
    """OCR from an existing image file"""
    img = Image.open(image_path).convert("RGB")
    return _run_ocr(img, mode=mode, context=question)

# ── Quick one-liners for voice pipeline ──────────────────────
def read_screen() -> str:
    """Reads text from screen — used by voice pipeline"""
    result = ocr_screen(mode="summarize")
    return result["text"]

def read_camera() -> str:
    """Reads text from camera — used by voice pipeline"""
    result = ocr_camera(mode="summarize")
    return result["text"]