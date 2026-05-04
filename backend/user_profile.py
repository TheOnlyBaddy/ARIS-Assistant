"""
ARIS User Profile Manager
Loads and manages the user profile that shapes ARIS's personality and responses.
"""

import json
import os
from datetime import datetime

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = os.path.join(BASE_DIR, "user_profile.json")

# Default profile used if no profile file exists yet
DEFAULT_PROFILE = {
    "name": "User",
    "preferred_name": "User",
    "location": "Unknown",
    "occupation": "Unknown",
    "interests": [],
    "communication_style": {
        "tone": "friendly",
        "verbosity": "concise",
        "use_emojis": False,
        "technical_level": "intermediate"
    },
    "aris_persona": {
        "personality": "professional yet warm",
        "response_style": "direct with clear explanations",
        "language": "English"
    },
    "reminders_enabled": True,
    "timezone": "UTC"
}


def load_profile() -> dict:
    """Load user profile from JSON file. Returns default if file doesn't exist."""
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            profile = json.load(f)
            print(f"[ARIS Profile] Loaded profile for: {profile.get('name', 'Unknown')}")
            return profile
    except FileNotFoundError:
        print("[ARIS Profile] No profile found, using defaults.")
        return DEFAULT_PROFILE
    except json.JSONDecodeError as e:
        print(f"[ARIS Profile] Profile file corrupted: {e}. Using defaults.")
        return DEFAULT_PROFILE


def save_profile(profile: dict) -> bool:
    """Save updated profile back to JSON file."""
    try:
        with open(PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
        print(f"[ARIS Profile] Profile saved for: {profile.get('name', 'Unknown')}")
        return True
    except Exception as e:
        print(f"[ARIS Profile] Failed to save profile: {e}")
        return False


def build_profile_prompt(profile: dict) -> str:
    """
    Convert the user profile into a natural language block
    that gets injected into ARIS's system prompt.
    ARIS reads this and adapts its behavior automatically.
    """
    style = profile.get("communication_style", {})
    persona = profile.get("aris_persona", {})
    interests = profile.get("interests", [])

    tone        = style.get("tone", "friendly")
    verbosity   = style.get("verbosity", "concise")
    tech_level  = style.get("technical_level", "intermediate")
    use_emojis  = style.get("use_emojis", False)
    personality = persona.get("personality", "professional yet warm")
    resp_style  = persona.get("response_style", "direct")

    interests_str = ", ".join(interests) if interests else "not specified"

    prompt = f"""
USER PROFILE (adapt your responses based on this):
- Name: {profile.get('preferred_name', profile.get('name', 'User'))}
- Occupation: {profile.get('occupation', 'Unknown')}
- Location: {profile.get('location', 'Unknown')}
- Interests: {interests_str}
- Timezone: {profile.get('timezone', 'UTC')}

COMMUNICATION PREFERENCES:
- Tone: {tone} — be {tone} in all responses
- Verbosity: {verbosity} — keep responses {verbosity} unless detail is requested
- Technical level: {tech_level} — assume {tech_level} knowledge, skip basics
- Emojis: {"use them occasionally" if use_emojis else "do not use emojis"}

YOUR PERSONA AS ARIS:
- Personality: {personality}
- Response style: {resp_style}
- Always address the user as {profile.get('preferred_name', 'User')}
""".strip()

    return prompt


def update_profile_field(field_path: str, value) -> dict:
    """
    Update a specific field in the profile using dot notation.
    Example: update_profile_field("communication_style.tone", "casual")
    """
    profile = load_profile()
    keys = field_path.split(".")

    # Navigate to the nested field
    target = profile
    for key in keys[:-1]:
        if key not in target:
            target[key] = {}
        target = target[key]

    target[keys[-1]] = value
    save_profile(profile)
    return profile