"""
ai/nlu.py
=========
Natural Language Understanding module.

Strategy (offline-first, no paid APIs):
  1. Rule-based intent + entity extraction using regex + dateparser.
     Works 100% offline, no model download needed, covers most real-world inputs.
  2. Optional Ollama backend (llama3 / mistral) for complex / multilingual queries.
     Falls back to rule-based if Ollama is unavailable.

Intents: add_task | delete_task | complete_task | show_tasks | update_task | unknown
Entities: task_name (str), task_id (int), due_datetime (ISO-8601 str)
"""

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

logger = logging.getLogger(__name__)

# ─── Ollama config ────────────────────────────────────────────────────────────
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"          # change to mistral, phi3, etc.

# ─── Intent keyword maps (multilingual basics) ────────────────────────────────
ADD_KEYWORDS      = ["add", "create", "new", "remind", "schedule", "agregar",
                     "ajouter", "hinzufügen", "añadir", "추가", "追加", "जोड़"]
DELETE_KEYWORDS   = ["delete", "remove", "cancel", "eliminar", "supprimer",
                     "löschen", "삭제", "削除", "हटाएं"]
COMPLETE_KEYWORDS = ["complete", "done", "finish", "completar", "terminer",
                     "abschließen", "완료", "完了", "पूरा"]
SHOW_KEYWORDS     = ["show", "list", "display", "view", "tasks", "what",
                     "mostrar", "afficher", "anzeigen", "보여", "表示", "दिखाओ"]
UPDATE_KEYWORDS   = ["update", "edit", "change", "rename", "reschedule",
                     "actualizar", "modifier", "bearbeiten", "업데이트"]


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


# ─── Ollama fallback ──────────────────────────────────────────────────────────

_OLLAMA_SYSTEM = """You are an intent and entity extractor for a to-do app.
Given a user message in ANY language, respond ONLY with a JSON object:
{
  "intent": "add_task|delete_task|complete_task|show_tasks|update_task|unknown",
  "task_name": "<name or null>",
  "task_id": <integer or null>,
  "due_datetime": "<ISO-8601 datetime or null>"
}
No explanation. No markdown. Only JSON."""


def _ollama_parse(text: str) -> dict | None:
    """Call local Ollama model. Returns parsed dict or None on failure."""
    if not REQUESTS_AVAILABLE:
        return None
    try:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": f"User message: {text}",
            "system": _OLLAMA_SYSTEM,
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
    """
    if not text or not text.strip():
        return {"intent": "unknown", "task_name": None,
                "task_id": None, "due_datetime": None, "raw": text}

    # Try Ollama first for richer understanding
    if use_ollama:
        result = _ollama_parse(text)
        if result and result.get("intent") in (
            "add_task","delete_task","complete_task","show_tasks","update_task","unknown"
        ):
            result["raw"] = text
            return result

    # Fall back to rule-based
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
