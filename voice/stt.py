# voice/stt.py
# ARIS Speech-to-Text Engine
# Uses fine-tuned Whisper if available, falls back to base Whisper
# Drop-in replacement — all ARIS modules call transcribe()

import os
import tempfile
import numpy as np
from scipy.io.wavfile import write as wav_write

FINETUNED_MODEL = "voice/whisper-aris"   # Your trained model
FALLBACK_MODEL  = "small"                # Base Whisper fallback

_model      = None
_model_type = None  # "finetuned" or "base"

def _load_model():
    global _model, _model_type

    # Try fine-tuned model first
    if os.path.exists(FINETUNED_MODEL):
        try:
            from transformers import pipeline
            print(f"⏳ Loading fine-tuned ARIS Whisper from {FINETUNED_MODEL}...")
            _model = pipeline(
                "automatic-speech-recognition",
                model=FINETUNED_MODEL,
                device=0          # GPU
            )
            _model_type = "finetuned"
            print("✅ Fine-tuned Whisper loaded (Hindi + Indian English optimized)")
            return
        except Exception as e:
            print(f"⚠️  Fine-tuned model failed: {e}")

    # Fallback to base Whisper
    import whisper
    print(f"⏳ Loading base Whisper {FALLBACK_MODEL}...")
    _model      = whisper.load_model(FALLBACK_MODEL)
    _model_type = "base"
    print(f"✅ Base Whisper {FALLBACK_MODEL} loaded")

def get_model():
    if _model is None:
        _load_model()
    return _model, _model_type

def transcribe(audio: np.ndarray, sample_rate: int = 16000) -> dict:
    """
    Transcribe audio array to text.
    Returns dict with 'text' and 'language' keys.
    Auto-detects Hindi / English / Hinglish.
    """
    model, model_type = get_model()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_write(tmp.name, sample_rate, audio.astype(np.int16))
        tmp_path = tmp.name

    try:
        if model_type == "finetuned":
            result = model(tmp_path, return_timestamps=False)
            return {
                "text"    : result["text"].strip(),
                "language": "hi/en",
                "model"   : "finetuned"
            }
        else:
            result = model.transcribe(
                tmp_path,
                fp16=True,
                verbose=False,
                initial_prompt="ARIS, hey ARIS, hello ARIS, अरिस"
            )
            return {
                "text"    : result["text"].strip(),
                "language": result.get("language", "en"),
                "model"   : "base"
            }
    finally:
        os.unlink(tmp_path)

def transcribe_file(file_path: str) -> dict:
    """Transcribe directly from a file path"""
    import soundfile as sf
    audio, sr = sf.read(file_path, dtype='int16')
    return transcribe(audio, sr)