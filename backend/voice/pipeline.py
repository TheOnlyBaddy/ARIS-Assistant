# voice/pipeline.py
# ARIS Full Voice Pipeline
# Wake word → STT → Emotion Detection → Screen Vision check → ARIS Brain → TTS
# Uses rolling buffer — captures audio BEFORE gate fires so nothing is missed

import threading
import collections
import tempfile
import os
import time
import requests
import numpy as np
import sounddevice as sd
import whisper
from scipy.io.wavfile import write as wav_write
from openwakeword.model import Model as WakeWordModel
from voice.tts import speak, get_tts_status
from voice.emotion import detect_emotion, get_emotion_emoji

# ── Config ────────────────────────────────────────────────────
SAMPLE_RATE      = 16000
CHUNK_SIZE       = 1280
SILENCE_THRESH   = 50
GATE_THRESH      = 0.1
PAUSE_AFTER_ACK  = 1.5
QUESTION_SECS    = 6
PRE_BUFFER_SECS  = 1.5
POST_BUFFER_SECS = 2.0
ARIS_URL         = "http://localhost:8000/chat"
WHISPER_PROMPT   = "ARIS, hey ARIS, hello ARIS, wake up ARIS, अरिस, हे अरिस"

# ── Wake phrases (EN + HI + Hinglish) ────────────────────────
WAKE_PHRASES = [
    "hey aris", "hello aris", "aris", "wake up aris",
    "ok aris", "okay aris", "hi aris", "yo aris",
    "aris listen", "aris help", "good morning aris",
    "अरिस", "हे अरिस", "अरिस सुनो", "अरिस जागो",
    "सुनो अरिस", "अरिस मदद करो",
    "aris sun", "sun aris", "aris uth", "aris bhai",
    "aris yaar", "aris suno", "aris jago", "aris help kar",
]

# ── Screen vision trigger phrases ─────────────────────────────
SCREEN_PHRASES = [
    "what's on my screen", "what is on my screen",
    "see my screen", "look at my screen",
    "describe my screen", "what do you see",
    "screen pe kya hai", "mera screen dekho",
    "screen dekho", "screen describe karo",
]

# ── Camera vision trigger phrases ─────────────────────────────
CAMERA_PHRASES = [
    "what do you see", "what can you see", "look at this",
    "camera dekho", "kya dikh raha hai", "describe this",
    "what am i holding", "who is here", "what is in front",
    "camera se dekho", "mujhe dekho",
]

# ── OCR trigger phrases ────────────────────────────────────────
OCR_PHRASES = [
    "read this", "read the text", "what does it say",
    "scan this", "read my screen", "what is written",
    "translate this", "read that document",
    "ye padho", "kya likha hai", "padhke batao",
    "is mein kya likha hai", "scan karo",
]

# ── Pipeline state ────────────────────────────────────────────
pipeline_state = {
    "running"       : False,
    "status"        : "off",
    "last_heard"    : "",
    "last_reply"    : "",
    "wake_count"    : 0,
    "emotion"       : "neutral",
    "emotion_emoji" : "😐",
    "error"         : None,
}

_pipeline_thread = None
_stop_event      = threading.Event()

# ── Auto-detect mic ───────────────────────────────────────────
def _get_mic():
    devices = sd.query_devices()
    mic_keywords = ['kreo', 'sonik', 'microphone']
    for keyword in mic_keywords:
        for i, d in enumerate(devices):
            if (d['max_input_channels'] > 0 and
                keyword in d['name'].lower() and
                'stereo mix' not in d['name'].lower()):
                print(f"Mic auto-selected: [{i}] {d['name']}")
                return i
    for i, d in enumerate(devices):
        if (d['max_input_channels'] > 0 and
            'stereo mix' not in d['name'].lower() and
            'loopback' not in d['name'].lower()):
            print(f"Mic fallback: [{i}] {d['name']}")
            return i
    raise RuntimeError("No input device found! Check mic is plugged in.")

# ── Wake phrase check ─────────────────────────────────────────
def _is_wake_phrase(text: str) -> bool:
    t = text.lower().strip()
    return any(p.lower() in t for p in WAKE_PHRASES)

# ── Screen phrase check ───────────────────────────────────────
def _is_screen_request(text: str) -> bool:
    t = text.lower().strip()
    return any(p.lower() in t for p in SCREEN_PHRASES)

# ── Silence check ─────────────────────────────────────────────
def _is_silent(audio: np.ndarray) -> bool:
    rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
    return rms < SILENCE_THRESH

# ── Transcribe ────────────────────────────────────────────────
def _transcribe(model, audio: np.ndarray) -> str:
    if _is_silent(audio):
        return ""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_write(tmp.name, SAMPLE_RATE, audio.astype(np.int16))
        path = tmp.name
    try:
        result = model.transcribe(
            path,
            fp16=False,
            verbose=False,
            initial_prompt=WHISPER_PROMPT
        )
        return result["text"].strip()
    finally:
        os.unlink(path)

# ── Speak and block until done ────────────────────────────────
def _speak_and_wait(text: str):
    pipeline_state["status"] = "speaking"
    speak(text)
    time.sleep(PAUSE_AFTER_ACK)

# ── Send to ARIS brain with emotion context ───────────────────
def _ask_aris(text: str, emotion_context: str = "") -> str:
    try:
        r = requests.post(
            ARIS_URL,
            json={
                "message"        : text,
                "user_id"        : "shubh",
                "emotion_context": emotion_context,
            },
            timeout=30
        )
        if r.status_code == 200:
            d = r.json()
            return d.get("response") or d.get("message") or d.get("reply") or str(d)
        return f"Sorry, error {r.status_code} from my brain."
    except requests.exceptions.ConnectionError:
        return "Sorry, FastAPI is not running. Start it with uvicorn first."
    except requests.exceptions.Timeout:
        return "Sorry boss, that took too long. Please try again."
    except Exception as e:
        return f"Sorry, something went wrong: {str(e)}"

# ── Record question from mic ──────────────────────────────────
def _record_question(mic, seconds: int) -> np.ndarray:
    audio = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype='int16',
        device=mic
    )
    sd.wait()
    return audio.flatten()

# ── Main pipeline ─────────────────────────────────────────────
def _run_pipeline():
    global pipeline_state

    print("\n" + "=" * 55)
    print("  ARIS Voice Pipeline Starting...")
    print("=" * 55)
    pipeline_state["status"] = "loading"

    print("Loading OpenWakeWord gate...")
    oww = WakeWordModel(wakeword_models=["hey_jarvis"], inference_framework="onnx")
    print("Wake word gate ready")

    print("Loading Whisper small...")
    whisper_model = whisper.load_model("small")
    print("Whisper ready")

    mic = _get_mic()

    pre_buffer_chunks = int(PRE_BUFFER_SECS * SAMPLE_RATE / CHUNK_SIZE)
    pre_buffer        = collections.deque(maxlen=pre_buffer_chunks)
    post_chunks       = int(POST_BUFFER_SECS * SAMPLE_RATE / CHUNK_SIZE)

    print(f"\nARIS is listening. Say 'Hey ARIS' to activate.")
    print(f"   Pre-buffer  : {PRE_BUFFER_SECS}s")
    print(f"   Post-buffer : {POST_BUFFER_SECS}s")
    print(f"   Gate thresh : {GATE_THRESH}\n")

    pipeline_state["running"] = True
    pipeline_state["status"]  = "listening"

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='int16',
            device=mic,
            blocksize=CHUNK_SIZE
        ) as stream:

            while not _stop_event.is_set():

                # ── Read chunk + rolling buffer ────────────────
                chunk, _    = stream.read(CHUNK_SIZE)
                audio_chunk = chunk.flatten()
                pre_buffer.append(audio_chunk.copy())

                # ── OpenWakeWord gate ──────────────────────────
                prediction = oww.predict(audio_chunk)
                max_score  = max(prediction.values()) if prediction else 0.0

                if max_score > 0.05:
                    print(f"  [gate] score={max_score:.3f}", end='\r')

                if max_score < GATE_THRESH:
                    pipeline_state["status"] = "listening"
                    continue

                # ── Gate fired — collect full audio ────────────
                print(f"\nGate triggered (score={max_score:.3f})")
                pipeline_state["status"] = "wake_detected"

                post_audio = []
                for _ in range(post_chunks):
                    c, _ = stream.read(CHUNK_SIZE)
                    post_audio.append(c.flatten())

                full_audio = np.concatenate(
                    list(pre_buffer) + [audio_chunk] + post_audio
                ).astype(np.int16)

                print(f"   Audio captured: {len(full_audio)/SAMPLE_RATE:.1f}s")

                # ── Transcribe to check wake phrase ────────────
                pipeline_state["status"] = "transcribing"
                print("Transcribing...")
                text = _transcribe(whisper_model, full_audio)

                if not text:
                    print("   (nothing heard — back to listening)\n")
                    pipeline_state["status"] = "listening"
                    pre_buffer.clear()
                    continue

                print(f"   Heard: \"{text}\"")
                pipeline_state["last_heard"] = text

                if not _is_wake_phrase(text):
                    print(f"   ✗ Not a wake phrase — listening\n")
                    pipeline_state["status"] = "listening"
                    pre_buffer.clear()
                    continue

                # ── Wake confirmed ─────────────────────────────
                pipeline_state["wake_count"] += 1
                print(f"\nARIS activated! (#{pipeline_state['wake_count']})")

                pre_buffer.clear()
                oww.reset()

                _speak_and_wait("Yes boss?")

                # ── Record question ────────────────────────────
                print(f"Listening for your question ({QUESTION_SECS}s)...")
                pipeline_state["status"] = "recording"
                question_audio = _record_question(mic, QUESTION_SECS)

                # ── Transcribe question ────────────────────────
                pipeline_state["status"] = "transcribing"
                print("Transcribing question...")
                question = _transcribe(whisper_model, question_audio)

                if not question:
                    _speak_and_wait("I did not catch that. Please try again.")
                    pipeline_state["status"] = "listening"
                    continue

                print(f"Question: \"{question}\"")
                pipeline_state["last_heard"] = question

                # ── Detect emotion ─────────────────────────────
                emotion_result = detect_emotion(
                    text        = question,
                    audio       = question_audio,
                    sample_rate = SAMPLE_RATE
                )
                emoji = get_emotion_emoji(emotion_result["emotion"])
                print(f"Emotion: {emoji} {emotion_result['emotion']} "
                      f"(text={emotion_result['text_emotion']}, "
                      f"audio={emotion_result['audio_emotion']})")

                pipeline_state["emotion"]       = emotion_result["emotion"]
                pipeline_state["emotion_emoji"] = emoji

                # ── Screen vision shortcut ─────────────────────
                # If user asks about screen, bypass ARIS brain
                # and respond directly with Gemini Vision result
                if _is_screen_request(question):
                    print("Screen vision requested!")
                    pipeline_state["status"] = "thinking"
                    try:
                        from vision.screen import describe_screen
                        screen_desc = describe_screen()
                        reply = f"I can see your screen. {screen_desc}"
                        print(f"Screen: {screen_desc[:80]}...")
                    except Exception as e:
                        reply = f"Sorry, I could not capture the screen. Error: {str(e)}"
                        print(f"Screen vision error: {e}")

                    pipeline_state["last_reply"] = reply
                    _speak_and_wait(reply)
                    print("Back to listening...\n")
                    pipeline_state["status"] = "listening"
                    continue
                
                # ── Camera vision shortcut ─────────────────────────────────
                elif any(p in question.lower() for p in CAMERA_PHRASES):
                    print("Camera vision requested!")
                    pipeline_state["status"] = "thinking"
                    try:
                        from vision.camera import describe_camera
                        cam_desc = describe_camera()
                        reply = f"Looking through the camera, I can see: {cam_desc}"
                        print(f"Camera: {cam_desc[:80]}...")
                    except Exception as e:
                        reply = f"Sorry, I could not access the camera. Error: {str(e)}"
                        print(f"Camera error: {e}")
                    pipeline_state["last_reply"] = reply
                    _speak_and_wait(reply)
                    print("Back to listening...\n")
                    pipeline_state["status"] = "listening"
                    continue

                # ── OCR shortcut ────────────────────────────────────────────
                elif any(p in question.lower() for p in OCR_PHRASES):
                    print("OCR requested!")
                    pipeline_state["status"] = "thinking"
                    try:
                        from vision.ocr import read_screen
                        text = read_screen()
                        reply = f"Here's what I read: {text}"
                    except Exception as e:
                        reply = f"Sorry, I could not read the text. Error: {str(e)}"
                    pipeline_state["last_reply"] = reply
                    _speak_and_wait(reply)
                    print("Back to listening...\n")
                    pipeline_state["status"] = "listening"
                    continue

                # ── Send to ARIS brain with emotion context ────
                pipeline_state["status"] = "thinking"
                print("Thinking...")
                reply = _ask_aris(
                    text            = question,
                    emotion_context = emotion_result["system_prompt"]
                )
                print(f"ARIS: \"{reply[:100]}{'...' if len(reply)>100 else ''}\"")
                pipeline_state["last_reply"] = reply

                # ── Speak response ─────────────────────────────
                _speak_and_wait(reply)

                print("Back to listening...\n")
                pipeline_state["status"] = "listening"

    except Exception as e:
        print(f"\nPipeline error: {e}")
        import traceback
        traceback.print_exc()
        pipeline_state["error"]   = str(e)
        pipeline_state["status"]  = "error"
        pipeline_state["running"] = False

    finally:
        pipeline_state["running"] = False
        pipeline_state["status"]  = "off"
        print("\nVoice pipeline stopped.")

# ── Public API ────────────────────────────────────────────────
def start_pipeline():
    global _pipeline_thread, _stop_event
    if pipeline_state["running"]:
        return {"status": "already_running"}
    _stop_event.clear()
    _pipeline_thread = threading.Thread(
        target=_run_pipeline,
        daemon=True,
        name="ARISVoicePipeline"
    )
    _pipeline_thread.start()
    time.sleep(0.5)
    return {"status": "started"}

def stop_pipeline():
    _stop_event.set()
    pipeline_state["status"]  = "stopping"
    pipeline_state["running"] = False
    return {"status": "stopped"}

def get_pipeline_status() -> dict:
    return {**pipeline_state, "tts": get_tts_status()}