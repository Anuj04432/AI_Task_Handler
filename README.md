# 🤖 AI-Powered To-Do System

> A production-ready, voice-enabled, multilingual task management system  
> built with Python + Streamlit. 100% free, works offline.

---

## 📁 Project Structure

```
ai_todo/
├── ui/
│   └── app.py                  ← Streamlit entry point (run this)
├── modules/
│   ├── database/
│   │   └── db.py               ← SQLite schema + all CRUD operations
│   ├── auth/
│   │   └── auth.py             ← Register, login, session persistence
│   ├── ai/
│   │   └── nlu.py              ← Intent detection + entity extraction (multilingual)
│   ├── voice/
│   │   └── voice.py            ← STT (SpeechRecognition) + TTS (pyttsx3)
│   ├── tasks/
│   │   └── task_manager.py     ← Business logic, motivational messages
│   └── scheduler/
│       └── scheduler.py        ← APScheduler: reminders + missed-task marking
├── data/
│   └── todo.db                 ← SQLite DB (auto-created on first run)
├── tests/
│   └── test_suite.py           ← pytest unit tests
├── .streamlit/
│   └── config.toml             ← Dark theme config
├── requirements.txt            ← Full (local) dependencies
├── requirements-cloud.txt      ← Streamlit Cloud (no audio)
└── README.md                   ← This file
```

---

## ✅ Features

| Feature | Status |
|---|---|
| Voice input (STT) | ✅ SpeechRecognition + Google Web Speech (free) |
| Voice output (TTS) | ✅ pyttsx3 (fully offline) |
| Multilingual NLU | ✅ Rule-based + dateparser + optional Ollama LLM |
| Add / Delete / Complete / Update tasks | ✅ |
| Due date/time on tasks | ✅ |
| Missed task locking | ✅ Non-editable after deadline |
| Reminder system | ✅ APScheduler (10 min before due) |
| Motivational messages | ✅ On completion and missed |
| User auth (register/login) | ✅ bcrypt hashed passwords |
| Session persistence | ✅ Token stored in DB |
| SQLite database | ✅ Users + tasks + sessions |
| Dashboard with stats | ✅ |
| Streamlit web UI | ✅ Mobile + desktop |
| Offline support | ✅ All local |
| Deployable to cloud | ✅ Streamlit Cloud |

---

## 🚀 Local Installation & Setup

### 1. Prerequisites
- Python 3.11+
- `pip`
- (Optional) [Ollama](https://ollama.com) for enhanced AI understanding

### 2. Clone the repo
```bash
git clone https://github.com/Anuj04432/AI_Task_Handler.git
cd AI_Task_Handler
```

### 3. Create a virtual environment
```bash
python -m venv venv

# macOS/Linux:
source venv/bin/activate

# Windows:
venv\Scripts\activate
```

### 4. Install dependencies

**For local (with voice):**
```bash
pip install -r requirements.txt
```

> **Note on PyAudio** (required for microphone):
> - **macOS**: `brew install portaudio && pip install PyAudio`
> - **Ubuntu/Debian**: `sudo apt-get install python3-pyaudio portaudio19-dev`
> - **Windows**: `pip install PyAudio` (pre-built wheel — usually works directly)

### 5. (Optional) Install Ollama for enhanced multilingual AI
```bash
# macOS/Linux
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3     # or: ollama pull mistral

# Then start it:
ollama serve
```

### 6. Run the app
```bash
streamlit run ui/app.py
```

Open your browser at **http://localhost:8501**

---

## 🧪 Running Tests

```bash
pytest tests/test_suite.py -v
```

---

## 🌐 Deployment to Streamlit Cloud

### Step 1: Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit — AI To-Do System"
git remote add origin https://github.com/YOUR_USERNAME/ai-todo.git
git push -u origin main
```

### Step 2: Deploy on Streamlit Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click **"New app"**
3. Select your GitHub repo
4. Set **Main file path** to: `ui/app.py`
5. Set **requirements file** to: `requirements-cloud.txt`
6. Click **Deploy**

> **Important**: On Streamlit Cloud, voice I/O is disabled (no microphone/speaker).
> The app automatically falls back to text-only mode. All other features work normally.

---

## 🤖 AI / NLU Details

### How intent detection works

```
User input
    │
    ▼
[Ollama LLM] ──(unavailable)──► [Rule-based keywords + regex]
    │                                       │
    ▼                                       ▼
  intent + entities               intent + entities
    │                                       │
    └───────────────────┬───────────────────┘
                        ▼
            {intent, task_name, task_id, due_datetime}
```

### Supported intents
| Intent | Example |
|---|---|
| `add_task` | "Add buy groceries by Friday 6pm" |
| `delete_task` | "Remove task 3" / "Eliminar tarea 3" |
| `complete_task` | "Mark task 5 done" / "완료 작업 2" |
| `show_tasks` | "Show my tasks" / "Afficher mes tâches" |
| `update_task` | "Rename task 1 to 'Read book'" |

---

## 🗄️ Database Schema

```sql
users   (id, username, password_hash, created_at)
tasks   (id, user_id→users, name, created_at, due_at, status)
sessions(id, user_id→users, token, created_at)
```

---

## 🔔 Reminder & Scheduler Logic

```
Every 60 seconds (background thread):
  ┌─────────────────────────────────────┐
  │ 1. Find pending tasks where         │
  │    due_at ≤ NOW  → mark MISSED      │
  │    + speak motivational message     │
  │                                     │
  │ 2. Find pending tasks where         │
  │    NOW < due_at ≤ NOW+10min         │
  │    → speak reminder alert           │
  └─────────────────────────────────────┘
```

---

## 🔐 Security Notes



- Passwords are hashed with **bcrypt** (work factor 12) — never stored in plaintext.
- Session tokens are 64-character cryptographically random hex strings.
- SQLite foreign keys enforced (`PRAGMA foreign_keys = ON`).
- All user input sanitized before DB insertion.

---

## 🔮 Future Improvements

1. **Google Calendar sync** — push tasks as calendar events
2. **Email/SMS reminders** — via Twilio (free tier) or SMTP
3. **Recurring tasks** — daily / weekly / monthly patterns
4. **Team collaboration** — shared task lists
5. **Mobile PWA** — installable on phone home screen
6. **Fully offline STT** — Vosk model download (already wired in)
7. **WhatsApp bot** — task management via WhatsApp (Twilio)
8. **Tagging & priorities** — High / Medium / Low with color coding
9. **Export to CSV/PDF**
10. **Dark/Light theme toggle**

---

## 📦 Key Dependencies

| Package | Purpose |
|---|---|
| `streamlit` | Web UI framework |
| `bcrypt` | Password hashing |
| `dateparser` | Multilingual date/time parsing |
| `SpeechRecognition` | Speech-to-text |
| `pyttsx3` | Text-to-speech (offline) |
| `APScheduler` | Background reminder scheduler |
| `requests` | Ollama HTTP calls |

---

## 👤 Author

Built as a complete production-ready system.  
License: MIT
