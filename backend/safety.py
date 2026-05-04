"""
ARIS Safety Guardrails
Protects against harmful requests and enforces confirmation
before destructive actions.
"""

import os
import re
from enum import Enum

# ─── TRUST LEVELS ──────────────────────────────────────────────────────────────

class TrustLevel(str, Enum):
    AUTO = "auto"   # ARIS acts immediately, no confirmation needed
    ASK  = "ask"    # ARIS asks for confirmation before anything destructive

# Load from env, default to "ask" (safer)
TRUST_LEVEL = TrustLevel(os.getenv("ARIS_TRUST_LEVEL", "ask"))

# ─── BLOCKED CONTENT PATTERNS ──────────────────────────────────────────────────
# These patterns catch clearly harmful requests.
# ARIS will refuse these regardless of trust level.

BLOCKED_PATTERNS = [
    # Violence
    r"\b(how to (make|build|create) a (bomb|weapon|explosive))\b",
    r"\b(instructions for (killing|harming|hurting) (someone|people|a person))\b",
    # Self-harm
    r"\b(how to (kill|hurt) (myself|yourself))\b",
    r"\b(suicide (method|instructions|how to))\b",
    # Illegal activity
    r"\b(how to (hack|crack|break into) (a system|an account|a network))\b",
    r"\b(make (drugs|meth|cocaine|heroin))\b",
    # Sensitive data extraction
    r"\b(ignore (all )?(previous |prior )?(instructions|prompts))\b",
    r"\b(jailbreak|dan mode|developer mode|ignore your (training|rules))\b",
    r"\b(reveal your (system prompt|instructions|prompt))\b",
]

# Compile patterns once for performance
COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]

# ─── DESTRUCTIVE ACTION KEYWORDS ───────────────────────────────────────────────
# These are actions that modify or delete data.
# In "ask" mode, ARIS will require confirmation before proceeding.

DESTRUCTIVE_KEYWORDS = [
    "delete", "clear", "remove", "reset", "erase",
    "wipe", "destroy", "purge", "drop", "overwrite"
]

# ─── SAFETY CHECK RESULTS ──────────────────────────────────────────────────────

class SafetyResult:
    def __init__(self, is_safe: bool, reason: str = "", requires_confirmation: bool = False):
        self.is_safe               = is_safe
        self.reason                = reason
        self.requires_confirmation = requires_confirmation

    def __repr__(self):
        return f"<SafetyResult safe={self.is_safe} confirm={self.requires_confirmation}>"


# ─── MAIN SAFETY CHECK ─────────────────────────────────────────────────────────

def check_message_safety(message: str) -> SafetyResult:
    """
    Run safety checks on an incoming user message.
    Returns a SafetyResult indicating:
      - is_safe: whether ARIS should respond at all
      - requires_confirmation: whether to ask user to confirm first
      - reason: explanation if blocked or needs confirmation
    """
    message_lower = message.lower().strip()

    # ── Check 1: Hard blocks (always refuse) ──
    for pattern in COMPILED_PATTERNS:
        if pattern.search(message_lower):
            return SafetyResult(
                is_safe=False,
                reason=(
                    "I'm not able to help with that request. "
                    "It falls outside the boundaries of what ARIS is designed to assist with. "
                    "If you need help with something else, I'm here."
                )
            )

    # ── Check 2: Destructive actions (require confirmation in ASK mode) ──
    if TRUST_LEVEL == TrustLevel.ASK:
        for keyword in DESTRUCTIVE_KEYWORDS:
            if keyword in message_lower:
                return SafetyResult(
                    is_safe=True,
                    requires_confirmation=True,
                    reason=(
                        f"This action contains '{keyword}' which could modify or remove data. "
                        f"Please confirm you want to proceed."
                    )
                )

    # ── All checks passed ──
    return SafetyResult(is_safe=True)


def get_safety_config() -> dict:
    """Return current safety configuration."""
    return {
        "trust_level": TRUST_LEVEL.value,
        "blocked_pattern_count": len(BLOCKED_PATTERNS),
        "destructive_keywords": DESTRUCTIVE_KEYWORDS,
        "confirmation_required_for_destructive": TRUST_LEVEL == TrustLevel.ASK
    }