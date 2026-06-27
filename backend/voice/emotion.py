# voice/emotion.py
# ARIS Emotion Detection — Hybrid Approach
# Method 1: Audio energy analysis (detects stress/excitement from voice)
# Method 2: Text keyword analysis (detects emotion from what was said)
# Combined: gives reliable emotion even with Indian accents + Hinglish
# Zero model downloads, no GPU needed, works instantly

import numpy as np

# ── Emotion keywords (EN + HI + Hinglish) ────────────────────
EMOTION_KEYWORDS = {
    "angry": [
        # English
        "angry", "frustrated", "hate", "annoyed", "stupid", "idiot",
        "useless", "terrible", "awful", "worst", "ridiculous", "pathetic",
        # Hindi
        "gussa", "ganda", "bakwaas", "bekar", "chup", "gadha", "bewakoof",
        "bura", "ghalat", "bekaar", "faltu",
        # Hinglish
        "kya bakwaas", "kya yaar", "ugh", "uff", "pagal",
    ],
    "sad": [
        # English
        "sad", "unhappy", "depressed", "miss", "lonely", "crying",
        "upset", "heartbroken", "tired", "exhausted", "disappointed",
        "hopeless", "miserable", "worried", "anxious", "scared",
        # Hindi
        "dukhi", "udaas", "rona", "dard", "takleef", "mushkil",
        "pareshan", "thaka", "darr", "chinta",
        # Hinglish
        "bahut bura", "kuch nahi ho raha", "nahi chahiye", "akela",
    ],
    "happy": [
        # English
        "happy", "excited", "great", "awesome", "love", "amazing",
        "wonderful", "fantastic", "brilliant", "excellent", "perfect",
        "thanks", "thank you", "appreciate", "beautiful", "enjoy",
        # Hindi
        "khush", "mast", "badiya", "achha", "zabardast", "shukriya",
        "bahut achha", "kamaal", "shandar", "maja",
        # Hinglish
        "ekdum mast", "too good", "bahut achha", "kya baat", "wah",
        "solid", "bindaas",
    ],
    "surprised": [
        "wow", "really", "seriously", "omg", "oh my", "no way",
        "unbelievable", "incredible", "shocking",
        "sach mein", "sacchi", "arre", "arrey", "matlab",
    ],
}

# ── How ARIS adapts its response per emotion ─────────────────
EMOTION_SYSTEM_PROMPTS = {
    "angry": (
        "The user sounds frustrated or angry. "
        "Be calm, patient and solution-focused. "
        "Acknowledge their frustration briefly, then help efficiently. "
        "Don't be overly cheerful."
    ),
    "sad": (
        "The user sounds sad, tired or upset. "
        "Be gentle, warm and empathetic. "
        "Offer emotional support before jumping to solutions. "
        "Keep your tone soft and caring."
    ),
    "happy": (
        "The user sounds happy and positive. "
        "Match their energy — be enthusiastic and upbeat. "
        "Feel free to be playful and engaging."
    ),
    "surprised": (
        "The user sounds surprised or curious. "
        "Be informative and engaging. "
        "Build on their curiosity."
    ),
    "neutral": (
        "Respond normally and helpfully."
    ),
    "stressed": (
        "The user sounds stressed or urgent (speaking loudly/fast). "
        "Be efficient and calm. Get straight to the point. "
        "Reassure them briefly if needed."
    ),
    "calm": (
        "The user sounds relaxed and calm. "
        "Match their calm energy. Be thoughtful and unhurried."
    ),
}

# ── Audio energy analysis ─────────────────────────────────────
def analyze_audio_energy(audio: np.ndarray, sample_rate: int = 16000) -> dict:
    """
    Analyzes voice energy patterns to detect stress/excitement.
    No ML model needed — uses signal processing only.

    Returns:
        energy_level : float  (0.0 = silent, 1.0 = very loud)
        speech_rate  : float  (estimated syllables per second)
        audio_emotion: str    (calm | neutral | stressed | excited)
    """
    if len(audio) == 0:
        return {"energy_level": 0.0, "speech_rate": 0.0, "audio_emotion": "neutral"}

    audio_float = audio.astype(np.float32)

    # ── RMS Energy (overall loudness) ─────────────────────────
    rms = np.sqrt(np.mean(audio_float ** 2))
    # Normalize to 0-1 range (32768 = max int16 value)
    energy_level = min(rms / 8000.0, 1.0)

    # ── Speech rate estimation via zero-crossing rate ─────────
    # Higher ZCR = faster speech / more fricatives = more stressed
    zero_crossings = np.sum(np.abs(np.diff(np.sign(audio_float)))) / 2
    zcr = zero_crossings / (len(audio_float) / sample_rate)
    # Normalize ZCR (typical range 0-3000 crossings/sec)
    speech_rate = min(zcr / 3000.0, 1.0)

    # ── Energy variance (how much volume changes) ─────────────
    # High variance = emotional/animated speech
    chunk_size = sample_rate // 4   # 250ms chunks
    chunks     = [audio_float[i:i+chunk_size]
                  for i in range(0, len(audio_float), chunk_size)
                  if len(audio_float[i:i+chunk_size]) == chunk_size]

    if chunks:
        chunk_rms     = [np.sqrt(np.mean(c**2)) for c in chunks]
        energy_variance = np.std(chunk_rms) / (np.mean(chunk_rms) + 1e-6)
    else:
        energy_variance = 0.0

    # ── Classify audio emotion ────────────────────────────────
    if energy_level < 0.05:
        audio_emotion = "neutral"      # Very quiet
    elif energy_level > 0.08 and speech_rate > 0.6:
        audio_emotion = "stressed"    # Loud + fast = stressed/angry
    elif energy_level > 0.5 and energy_variance > 0.4:
        audio_emotion = "excited"      # Loud + variable = excited
    elif energy_level < 0.2 and speech_rate < 0.3:
        audio_emotion = "calm"         # Quiet + slow = calm
    else:
        audio_emotion = "neutral"

    return {
        "energy_level"   : round(float(energy_level), 3),
        "speech_rate"    : round(float(speech_rate), 3),
        "energy_variance": round(float(energy_variance), 3),
        "audio_emotion"  : audio_emotion,
    }

# ── Text keyword analysis ─────────────────────────────────────
def analyze_text_emotion(text: str) -> dict:
    """
    Detects emotion from transcribed text keywords.
    Works with English, Hindi, and Hinglish.

    Returns:
        text_emotion : str   (angry|sad|happy|surprised|neutral)
        matched_word : str   (which keyword triggered it)
        confidence   : str   (high|medium|low)
    """
    text_lower = text.lower().strip()
    matches    = {}

    for emotion, keywords in EMOTION_KEYWORDS.items():
        matched = [kw for kw in keywords if kw in text_lower]
        if matched:
            matches[emotion] = matched

    if not matches:
        return {
            "text_emotion": "neutral",
            "matched_words": [],
            "confidence": "low"
        }

    # Pick emotion with most keyword matches
    dominant = max(matches, key=lambda e: len(matches[e]))
    return {
        "text_emotion" : dominant,
        "matched_words": matches[dominant],
        "confidence"   : "high" if len(matches[dominant]) > 1 else "medium"
    }

# ── Combined emotion detection ────────────────────────────────
def detect_emotion(text: str, audio: np.ndarray = None,
                   sample_rate: int = 16000) -> dict:
    """
    Main emotion detection function for ARIS.
    Combines audio energy + text analysis for best accuracy.

    Args:
        text       : Whisper transcription of what user said
        audio      : Raw audio array (optional but improves accuracy)
        sample_rate: Audio sample rate (default 16000)

    Returns full emotion analysis dict including system prompt injection.
    """
    # Text analysis (always runs)
    text_result = analyze_text_emotion(text)

    # Audio analysis (runs if audio provided)
    audio_result = {"audio_emotion": "neutral", "energy_level": 0.0,
                    "speech_rate": 0.0, "energy_variance": 0.0}
    if audio is not None and len(audio) > 0:
        audio_result = analyze_audio_energy(audio, sample_rate)

    # ── Combine both signals ──────────────────────────────────
    text_emotion  = text_result["text_emotion"]
    audio_emotion = audio_result["audio_emotion"]

    # Priority rules:
    # 1. Text with HIGH confidence always wins
    # 2. Stressed audio + neutral text → stressed
    # 3. Otherwise text emotion wins over audio
    if text_result["confidence"] == "high":
        final_emotion = text_emotion
    elif audio_emotion == "stressed" and text_emotion == "neutral":
        final_emotion = "stressed"
    elif audio_emotion == "excited" and text_emotion == "neutral":
        final_emotion = "happy"
    elif text_emotion != "neutral":
        final_emotion = text_emotion
    else:
        final_emotion = audio_emotion if audio_emotion != "neutral" else "neutral"

    # Get system prompt for ARIS
    system_prompt = EMOTION_SYSTEM_PROMPTS.get(
        final_emotion,
        EMOTION_SYSTEM_PROMPTS["neutral"]
    )

    return {
        "emotion"       : final_emotion,
        "system_prompt" : system_prompt,
        "text_emotion"  : text_emotion,
        "audio_emotion" : audio_emotion,
        "matched_words" : text_result["matched_words"],
        "confidence"    : text_result["confidence"],
        "energy_level"  : audio_result["energy_level"],
        "speech_rate"   : audio_result["speech_rate"],
    }

# ── Emoji for UI display ──────────────────────────────────────
EMOTION_EMOJI = {
    "happy"    : "😊",
    "sad"      : "😢",
    "angry"    : "😠",
    "surprised": "😲",
    "stressed" : "😤",
    "calm"     : "😌",
    "neutral"  : "😐",
}

def get_emotion_emoji(emotion: str) -> str:
    return EMOTION_EMOJI.get(emotion, "😐")