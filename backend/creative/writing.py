"""
ARIS Long-Form Content Writing
- Write blog posts, essays, emails, reports, social posts in Shubh's voice/style
- Style learned from user_profile.json
- Export as .txt or .md file
"""

import os
import json
import time
from pathlib import Path
from google import genai
from google.genai import types

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
OUTPUT_DIR = ROOT_DIR / "output" / "writing"
PROFILE_PATH = BACKEND_DIR / "user_profile.json"

# Ensure output directory exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("PRIMARY_MODEL", "gemini-2.5-flash")


def _load_user_profile() -> dict:
    """Load user profile details to mimic style."""
    if PROFILE_PATH.exists():
        try:
            with open(PROFILE_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


async def generate_content(
    topic: str,
    format_type: str = "blog",
    export_type: str = "md",
    export_name: str = ""
) -> dict:
    """Generate long-form content mimicking Shubh's communication style and export it."""
    profile = _load_user_profile()

    name = profile.get("name", "Shubh")
    occupation = profile.get("occupation", "Software Developer")
    interests = ", ".join(profile.get("interests", ["AI", "Python", "technology"]))
    
    style = profile.get("communication_style", {})
    tone = style.get("tone", "friendly")
    verbosity = style.get("verbosity", "concise")
    use_emojis = style.get("use_emojis", False)
    tech_level = style.get("technical_level", "advanced")

    prompt = (
        f"You are writing a piece of content on behalf of {name}, who is a {occupation}.\n"
        f"Interests of {name}: {interests}.\n\n"
        f"Writing Style Rules:\n"
        f"- Tone: {tone}\n"
        f"- Verbosity: {verbosity}\n"
        f"- Use Emojis: {use_emojis} (Do NOT use emojis at all if False)\n"
        f"- Technical Level: {tech_level}\n\n"
        f"Format required: {format_type}\n"
        f"Topic to write about: {topic}\n\n"
        f"Please write the complete {format_type} content without any introductory meta-text or tags from the AI. "
        f"Write directly in {name}'s voice."
    )

    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=1024)
            )
        )
        content = response.text.strip()

        # Filename setup
        if not export_name:
            export_name = f"draft_{int(time.time())}"
        
        # Clean export name
        export_name = "".join(c for c in export_name if c.isalnum() or c in ("-", "_")).strip()
        filename = f"{export_name}.{export_type}"
        filepath = OUTPUT_DIR / filename
        local_url = f"/output/writing/{filename}"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "status": "success",
            "format": format_type,
            "topic": topic,
            "file_path": local_url,
            "content": content
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
