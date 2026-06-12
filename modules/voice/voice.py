"""
voice/voice.py
==============
Voice I/O module.

Speech-to-Text  : SpeechRecognition library (Google Web Speech — free, online)
                  Falls back to Vosk (offline) if available.
Text-to-Speech  : pyttsx3 (fully offline, cross-platform).

In Streamlit Cloud (no audio device) both STT and TTS are gracefully disabled
and the app falls back to text-only mode.
"""

import logging
import threading
import queue
from typing import Optional

logger = logging.getLogger(__name__)

# ─── TTS ─────────────────────────────────────────────────────────────────────

try:
    import pyttsx3
    _tts_engine = pyttsx3.init()
    _tts_engine.setProperty("rate", 160)   # words-per-minute
    _tts_engine.setProperty("volume", 1.0)
    TTS_AVAILABLE = True
except Exception as _e:
    TTS_AVAILABLE = False
    logger.info("pyttsx3 not available (%s). TTS disabled.", _e)

# Serialize TTS calls (pyttsx3 is not thread-safe)
_tts_lock = threading.Lock()


def speak(text: str) -> None:
    """
    Convert text to speech and play it.
    Safe to call from any thread. No-op if TTS unavailable.
    """
    if not TTS_AVAILABLE:
        logger.info("[TTS disabled] Would say: %s", text)
        return
    def _run():
        with _tts_lock:
            try:
                _tts_engine.say(text)
                _tts_engine.runAndWait()
            except Exception as exc:
                logger.warning("TTS error: %s", exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


# ─── STT ──────────────────────────────────────────────────────────────────────

try:
    import speech_recognition as sr
    STT_AVAILABLE = True
    _recognizer = sr.Recognizer()
except ImportError:
    STT_AVAILABLE = False
    logger.info("SpeechRecognition not installed. STT disabled.")


def listen(timeout: int = 5, phrase_time_limit: int = 10) -> Optional[str]:
    """
    Record from the default microphone and return transcribed text.
    Returns None on failure / silence.

    timeout            : seconds to wait for speech to start
    phrase_time_limit  : max seconds to record
    """
    if not STT_AVAILABLE:
        logger.info("STT disabled.")
        return None

    try:
        with sr.Microphone() as source:
            logger.info("Adjusting for ambient noise…")
            _recognizer.adjust_for_ambient_noise(source, duration=0.5)
            logger.info("Listening…")
            audio = _recognizer.listen(
                source, timeout=timeout, phrase_time_limit=phrase_time_limit
            )

        # Primary: Google Web Speech (free, multilingual, online)
        try:
            text = _recognizer.recognize_google(audio, language="en-US")
            logger.info("STT result (Google): %s", text)
            return text
        except sr.UnknownValueError:
            logger.info("Google STT: could not understand audio.")
        except sr.RequestError as e:
            logger.warning("Google STT failed (%s). Trying offline Vosk…", e)

        # Fallback: Vosk offline (optional)
        try:
            from vosk import Model, KaldiRecognizer  # type: ignore
            import json as _json, os as _os
            model_path = _os.path.join(_os.path.dirname(__file__), "vosk-model-small-en-us")
            if _os.path.exists(model_path):
                model = Model(model_path)
                rec   = KaldiRecognizer(model, 16000)
                raw   = audio.get_wav_data(convert_rate=16000, convert_width=2)
                rec.AcceptWaveform(raw)
                result = _json.loads(rec.FinalResult())
                text   = result.get("text", "")
                if text:
                    logger.info("STT result (Vosk): %s", text)
                    return text
        except Exception as vosk_err:
            logger.debug("Vosk error: %s", vosk_err)

    except Exception as exc:
        logger.warning("listen() error: %s", exc)

    return None


# ─── Convenience messages ────────────────────────────────────────────────────

MESSAGES = {
    "task_added":       "Task added. Do you want to add more tasks?",
    "task_deleted":     "Task deleted successfully.",
    "task_completed":   "Great job! Task marked as completed. Keep up the momentum!",
    "task_missed":      "You missed a task. That's okay — learn, adapt, and come back stronger.",
    "task_list_empty":  "You have no tasks right now. Ready to add one?",
    "task_locked":      "This task has been missed and cannot be edited.",
    "login_success":    "Welcome back! You are now logged in.",
    "register_success": "Account created! Let's get productive.",
    "error_generic":    "Something went wrong. Please try again.",
}


def announce(key: str, custom: str | None = None) -> str:
    """
    Speak a predefined message (by key) or a custom string.
    Returns the text spoken so the UI can display it too.
    """
    text = custom if custom else MESSAGES.get(key, key)
    speak(text)
    return text
