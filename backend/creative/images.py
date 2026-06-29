"""
ARIS Image Generation
- Generates images from text descriptions
- Tries DALL-E (OpenAI) first, falls back to Gemini Imagen 3
- Saves images to ARIS/output/images/
"""

import os
import time
import base64
from pathlib import Path
from google import genai
from google.genai import types

# Setup output directory in the root of the project
# This assumes creative/ is under backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
OUTPUT_DIR = ROOT_DIR / "output" / "images"

# Ensure output directory exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def generate_image(prompt: str) -> dict:
    """Generate an image using Gemini Imagen 4."""
    gemini_key = os.getenv("GEMINI_API_KEY")

    filename = f"gen_{int(time.time())}.jpg"
    filepath = OUTPUT_DIR / filename
    local_url = f"/output/images/{filename}"

    if not gemini_key:
        return {
            "status": "error",
            "message": "GEMINI_API_KEY is not configured in the environment."
        }

    try:
        gemini_client = genai.Client(api_key=gemini_key)
        result = gemini_client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                output_mime_type="image/jpeg",
                aspect_ratio="1:1",
                person_generation="allow_adult"
            )
        )
        generated_image = result.generated_images[0]
        image_bytes = base64.b64decode(generated_image.image.image_bytes)
        with open(filepath, "wb") as f:
            f.write(image_bytes)

        return {
            "status": "success",
            "provider": "google/imagen-4",
            "prompt": prompt,
            "url": local_url
        }
    except Exception as e:
        error_msg = str(e)
        if "paid plans" in error_msg or "400" in error_msg:
            return {
                "status": "error",
                "message": "Gemini Imagen is only available on paid tier plans. Please upgrade your Google AI Studio account billing to use image generation."
            }
        return {"status": "error", "message": f"Gemini Imagen failed: {error_msg}"}
