"""
ai/nlu.py
=========
Natural Language Understanding module.

Strategy (best result, with offline fallback):
  1. Gemini API (free tier via Google AI Studio, new `google-genai` SDK) —
     best multilingual/Hinglish understanding. Requires GEMINI_API_KEY env var.
     Needs internet.
  2. Ollama backend (local LLM: phi3, gemma:2b, qwen2:1.5b, etc.) — offline,
     used if Gemini key is missing or the call fails.
  3. Rule-based regex + dateparser — always available, 100% offline fallback.

Intents: add_task | delete_task | complete_task | show_tasks | update_task | unknown
Entities: task_name (str), task_id (int), due_datetime (ISO-8601 str)
"""

import os
import re
import json
import logging
from datetime import datetime

try:
    import dateparser
    DATEPARSER_AVAILABLE = True
except ImportError:
    DATEPARSER_AVAILABLE = False

try:
    import requests as _requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from google import genai as _genai
    GEMINI_SDK_AVAILABLE = True
except ImportError:
    GEMINI_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)

# ─── Gemini config ────────────────────────────────────────────────────────────
# Set this via environment variable, e.g.:
#   Windows (cmd):        set GEMINI_API_KEY=your_key_here
#   Windows (PowerShell): $env:GEMINI_API_KEY="your_key_here"
#   macOS/Linux:          export GEMINI_API_KEY=your_key_here
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-2.5-flash-lite"   # fast + free tier, confirmed working
# Lazily-created client (avoids error at import time if key is missing)
_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None and GEMINI_SDK_AVAILABLE and GEMINI_API_KEY:
        try:
            _gemini_client = _genai.Client(api_key=GEMINI_API_KEY)
        except Exception as exc:
            logger.debug("Failed to create Gemini client: %s", exc)
            _gemini_client = False  # mark as failed, don't retry every call
    return _gemini_client or None


# ─── Ollama config ────────────────────────────────────────────────────────────
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2:1.5b"          # change to phi3, gemma:2b, etc.

# ─── Intent keyword maps (multilingual basics + Hinglish) ─────────────────────
ADD_KEYWORDS = [
    # Hindi / Hinglish
    "jana hai", "karna hai", "yaad", "yaad dilana",
    "yaad rakhna", "kaam", "kaam hai", "note karo",
    "save karo", "add karo", "task banao",
    "reminder lagao", "alarm lagao", "mujhe yaad dilana",

    # Marathi
    "aathavan", "aathavan karun de", "lakshat thev",
    "karaycha aahe", "kaam aahe", "nond kar",
    "visru nako",

    # Kannada
    "nenapu", "nenapisu", "madbeku", "madabeku",
    "kelasa", "serisu", "haaku", "naale",
    "mareyabeda", "reminder haaku",

    # Telugu
    "gurtu", "gurtu cheyyi", "gurthunchuko",
    "cheyyali", "pani", "jodinchu",
    "repu", "marchipoku", "reminder pettu",

    # Tamil
    "nyabagam", "nyabagam paduthu", "ninaivu",
    "ninaivootu", "seiyanum", "velai",
    "serka", "naalai", "marakkathe",
    "reminder podu",

    # Malayalam
    "orma", "ormippikku", "cheyyanam",
    "joli", "cherkkuka", "nale",
    "marakkaruthu", "reminder vekku",

    # Gujarati
    "yaad karavjo", "yaad rakhjo",
    "karvanu che", "kaam che",
    "nondh karo", "umero",

    # Punjabi
    "yaad kara de", "yaad rakh",
    "karna hai", "kam hai",
    "note kar", "reminder la de",

    # Bengali
    "mone rakho", "mone koriye dao",
    "kaj ache", "korte hobe",
    "jog koro",

    # Odia
    "mane rakha", "mane paka",
    "karibaku achhi", "kaam achhi",
    "joda"
]

DELETE_KEYWORDS = [
    "hatao", "hata do", "mita do", "delete karo",
    "kadhun taka", "hatva",
    "tegedu haaku", "alisu",
    "teesey", "tholaginchu",
    "neekku", "azhithu vidu",
    "ozhivakku", "kalayuka",
    "dur karo", "kadhi nakho",
    "hata de", "mita de",
    "bad diye dao", "soriye dao",
    "jhada"
]

COMPLETE_KEYWORDS = [
    "ho gaya", "kar diya", "khatam",
    "poora ho gaya", "complete ho gaya",
    "zala", "purna zala",
    "aaytu", "mugitu",
    "ayipoyindi", "poorthi ayindi",
    "mudinju", "mudinjiduchu",
    "kazhinju", "poorthiyayi",
    "thai gayu", "purn thai gayu",
    "ho gya", "muk gaya",
    "hoye geche",
    "sari gala"
]

SHOW_KEYWORDS = [
    "dikhao", "kya hai", "batao",
    "mere task", "mere kaam",
    "dakhav", "yadi dakhav",
    "torisu", "list torisu",
    "chuupinchu", "list chupinchu",
    "kaatu", "list kaatu",
    "kaanikku", "list kaanikku",
    "batavo", "yaadi batavo",
    "dikha de", "list dikha",
    "dekhao", "kaj dekhao",
    "dekha", "talika dekha"
]

UPDATE_KEYWORDS = [
    "badlo", "badal do", "sudharo",
    "update karo", "naam badlo",
    "time badlo",

    "badla", "sudhar",
    "badalisi", "hesaru badalisi",
    "marchu", "peru marchu",
    "maatru", "peyar maatru",
    "maattuka", "per maattuka",
    "naam badlo",
    "badal de", "naam badal de",
    "poriborton koro",
    "badala"
]


def _detect_intent_rule(text: str) -> str:
    """Keyword-based intent detection. Fast and offline."""
    lower = text.lower()
    if any(k in lower for k in COMPLETE_KEYWORDS):
        return "complete_task"
    if any(k in lower for k in DELETE_KEYWORDS):
        return "delete_task"
    if any(k in lower for k in ADD_KEYWORDS):
        return "add_task"
    if any(k in lower for k in UPDATE_KEYWORDS):
        return "update_task"
    if any(k in lower for k in SHOW_KEYWORDS):
        return "show_tasks"
    return "unknown"


def _extract_task_id(text: str) -> int | None:
    """Pull a task ID from text like 'delete task 3' or 'complete #5'."""
    m = re.search(r"(?:task\s*#?|#)(\d+)", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Last bare number in the string
    nums = re.findall(r"\b(\d+)\b", text)
    return int(nums[-1]) if nums else None


def _extract_due_datetime(text: str) -> str | None:
    """
    Extract a due date/time string using dateparser (multilingual).
    Returns ISO-8601 string or None.
    """
    if not DATEPARSER_AVAILABLE:
        return None
    try:
        # dateparser handles "tomorrow at 3pm", "lunes a las 5", "내일 오후 3시", etc.
        dt = dateparser.parse(
            text,
            settings={
                "PREFER_DATES_FROM": "future",
                "RETURN_AS_TIMEZONE_AWARE": False,
            }
        )
        if dt and dt > datetime.now():
            return dt.isoformat(timespec="seconds")
    except Exception as exc:
        logger.warning("dateparser error: %s", exc)
    return None


def _extract_task_name(text: str, intent: str) -> str:
    """
    Strip intent keywords and time expressions to isolate the task name.
    Rough but effective for most real-world inputs.
    """
    cleaned = text.strip()

    # Remove leading intent verb
    all_kws = ADD_KEYWORDS + DELETE_KEYWORDS + COMPLETE_KEYWORDS + UPDATE_KEYWORDS
    for kw in sorted(all_kws, key=len, reverse=True):
        pattern = rf"^\s*{re.escape(kw)}\s+(a\s+task\s+(?:called|named)\s+|task\s+)?"\
                  r"(?:called\s+|named\s+)?"
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    # Remove trailing date/time phrases (simple English patterns)
    date_phrases = [
        r"\b(?:by|before|on|at|for|due)\s+.+$",
        r"\b(?:tomorrow|today|tonight|next\s+\w+)\b.*$",
        r"\b\d{1,2}[/:]\d{2}.*$",
    ]
    for pat in date_phrases:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()

    return cleaned if cleaned else text.strip()


# ─── Shared system prompt for LLM-based parsing ───────────────────────────────

_LLM_SYSTEM = """You are an intent and entity extractor for a to-do app.
Given a user message in ANY language, including English, Hindi, Hinglish, Marathi, Kannada, Telugu, Tamil, Malayalam, Gujarati, Punjabi, Bengali, Odia, Assamese, Konkani, or code-mixed text written in either native scripts or English transliteration, respond ONLY with a JSON object:
{
  "intent": "add_task|delete_task|complete_task|show_tasks|update_task|unknown",
  "task_name": "<short task description in English or original language, or null>",
  "task_id": <integer or null>,
  "due_datetime": "<ISO-8601 datetime, e.g. 2025-06-13T09:00:00, or null>"
}
Recognize task-related phrases, reminders, dates, times, and natural language expressions in all supported Indian languages and their English transliterations.
Today's date/time is """ + datetime.now().isoformat(timespec="seconds") + """.
No explanation. No markdown. Only JSON."""


# ─── Gemini (free tier API, new google-genai SDK) ─────────────────────────────

def _gemini_parse(text: str) -> dict | None:
    """Call Gemini API for intent/entity extraction. Returns dict or None."""
    client = _get_gemini_client()
    if client is None:
        return None
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"User message: {text}",
            config={
                "system_instruction": _LLM_SYSTEM,
                "response_mime_type": "application/json",
            },
        )
        raw = (response.text or "").strip()
        raw = re.sub(r"```(?:json)?|```", "", raw).strip()
        return json.loads(raw)
    except Exception as exc:
        logger.debug("Gemini unavailable (%s), trying next fallback.", exc)
        return None


# ─── Ollama (local LLM fallback) ───────────────────────────────────────────────

def _ollama_parse(text: str) -> dict | None:
    """Call local Ollama model. Returns parsed dict or None on failure."""
    if not REQUESTS_AVAILABLE:
        return None
    try:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": f"User message: {text}",
            "system": _LLM_SYSTEM,
            "stream": False,
        }
        resp = _requests.post(OLLAMA_URL, json=payload, timeout=10)
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        # Strip markdown fences if model adds them
        raw = re.sub(r"```(?:json)?|```", "", raw).strip()
        return json.loads(raw)
    except Exception as exc:
        logger.debug("Ollama unavailable (%s), using rule-based NLU.", exc)
        return None


# ─── Public API ───────────────────────────────────────────────────────────────

_VALID_INTENTS = (
    "add_task", "delete_task", "complete_task",
    "show_tasks", "update_task", "unknown"
)


def parse_command(text: str, use_ollama: bool = True) -> dict:
    """
    Parse a natural-language command and return a structured dict:
    {
        "intent":        str,
        "task_name":     str | None,
        "task_id":       int | None,
        "due_datetime":  str | None,   # ISO-8601
        "raw":           str,
    }

    Resolution order:
      1. Gemini (if GEMINI_API_KEY is set)
      2. Ollama (if running locally and use_ollama=True)
      3. Rule-based (always available, offline)
    """
    if not text or not text.strip():
        return {"intent": "unknown", "task_name": None,
                "task_id": None, "due_datetime": None, "raw": text}

    # 1. Try Gemini first (best multilingual/Hinglish quality)
    result = _gemini_parse(text)

    # 2. Fall back to Ollama
    if result is None and use_ollama:
        result = _ollama_parse(text)

    if result and result.get("intent") in _VALID_INTENTS:
        result.setdefault("task_name", None)
        result.setdefault("task_id", None)
        result.setdefault("due_datetime", None)
        result["raw"] = text
        return result

    # 3. Fall back to rule-based
    intent      = _detect_intent_rule(text)
    task_id     = _extract_task_id(text)
    due_dt      = _extract_due_datetime(text)
    task_name   = _extract_task_name(text, intent) if intent in (
        "add_task", "update_task") else None

    return {
        "intent":       intent,
        "task_name":    task_name,
        "task_id":      task_id,
        "due_datetime": due_dt,
        "raw":          text,
    }