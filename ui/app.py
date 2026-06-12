"""
ui/app.py  (entry point: run with `streamlit run ui/app.py`)
=============================================================
Complete Streamlit UI for the AI-powered To-Do system.
Pages:
  - Login / Register
  - Dashboard (stats + task list)
  - Add Task (text or voice)
  - AI Command (natural language input)
  - Settings / Logout
"""

import sys, os
# Ensure project root is on the path so modules resolve correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import threading
from datetime import datetime

import streamlit as st
from streamlit_js_eval import streamlit_js_eval   # for browser notifications (optional)

from modules.database   import db
from modules.auth       import auth as auth_mod
from modules.tasks      import task_manager as tm
from modules.ai         import nlu
from modules.voice      import voice
from modules.scheduler  import scheduler

# ─── One-time init ────────────────────────────────────────────────────────────
db.init_db()
scheduler.start_scheduler()

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI To-Do",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Google Font ── */
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

html, body, [class*="css"] { font-family: 'Sora', sans-serif; }

/* ── Color palette ── */
:root {
    --bg:       #0f1117;
    --surface:  #1a1d27;
    --accent:   #6ee7b7;
    --warn:     #fbbf24;
    --danger:   #f87171;
    --text:     #e2e8f0;
    --muted:    #64748b;
    --radius:   12px;
}

/* ── Card ── */
.card {
    background: var(--surface);
    border: 1px solid rgba(110,231,183,.15);
    border-radius: var(--radius);
    padding: 1.2rem 1.5rem;
    margin-bottom: .8rem;
    transition: border-color .2s;
}
.card:hover { border-color: rgba(110,231,183,.4); }

/* ── Status badges ── */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 99px;
    font-size: .75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .05em;
}
.badge-pending   { background:#1e3a5f; color:#93c5fd; }
.badge-completed { background:#064e3b; color:var(--accent); }
.badge-missed    { background:#450a0a; color:var(--danger); }

/* ── Metric box ── */
.metric-box {
    background: var(--surface);
    border: 1px solid rgba(110,231,183,.12);
    border-radius: var(--radius);
    padding: 1rem;
    text-align: center;
}
.metric-box .num  { font-size: 2.2rem; font-weight: 700; color: var(--accent); }
.metric-box .lbl  { font-size: .8rem;  color: var(--muted); text-transform: uppercase; letter-spacing:.08em; }

/* ── Voice button ── */
.voice-btn {
    background: linear-gradient(135deg, #6ee7b7, #3b82f6) !important;
    color: #0f1117 !important;
    font-weight: 700 !important;
    border-radius: 99px !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] { background: var(--surface) !important; }

/* ── Inputs ── */
input, textarea { background: var(--bg) !important; color: var(--text) !important; }

/* ── Hide Streamlit branding ── */
#MainMenu, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def badge(status: str) -> str:
    cls = f"badge badge-{status}"
    return f'<span class="{cls}">{status}</span>'


def fmt_dt(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d %b %Y  %H:%M")
    except Exception:
        return iso


def notify_browser(title: str, body: str) -> None:
    """Fire a browser notification via JS (best-effort)."""
    try:
        js = f"""
        if (Notification.permission === 'granted') {{
            new Notification('{title}', {{body: '{body}'}});
        }} else if (Notification.permission !== 'denied') {{
            Notification.requestPermission().then(p => {{
                if (p === 'granted') new Notification('{title}', {{body: '{body}'}});
            }});
        }}
        """
        streamlit_js_eval(js_expressions=js)
    except Exception:
        pass   # streamlit_js_eval optional


# ═════════════════════════════════════════════════════════════════════════════
# AUTH PAGES
# ═════════════════════════════════════════════════════════════════════════════

def render_auth_page() -> None:
    st.markdown("## 🤖 AI To-Do — Sign In")
    tab_login, tab_reg = st.tabs(["🔑 Login", "📝 Register"])

    with tab_login:
        with st.form("login_form"):
            uname = st.text_input("Username")
            pwd   = st.text_input("Password", type="password")
            sub   = st.form_submit_button("Login", use_container_width=True)
        if sub:
            ok, msg = auth_mod.login(uname, pwd)
            if ok:
                st.success(msg)
                voice.announce("login_success")
                st.rerun()
            else:
                st.error(msg)

    with tab_reg:
        with st.form("reg_form"):
            uname_r = st.text_input("Choose Username")
            pwd_r   = st.text_input("Choose Password (min 6 chars)", type="password")
            sub_r   = st.form_submit_button("Create Account", use_container_width=True)
        if sub_r:
            ok, msg = auth_mod.register(uname_r, pwd_r)
            if ok:
                st.success(msg)
                voice.announce("register_success")
            else:
                st.error(msg)


# ═════════════════════════════════════════════════════════════════════════════
# MAIN APP PAGES
# ═════════════════════════════════════════════════════════════════════════════

def render_dashboard(user: dict) -> None:
    st.markdown(f"### 👋 Welcome back, **{user['username']}**")
    stats = tm.get_task_stats(user["id"])

    c1, c2, c3, c4 = st.columns(4)
    for col, key, label in [
        (c1, "total",     "Total"),
        (c2, "pending",   "Pending"),
        (c3, "completed", "Completed"),
        (c4, "missed",    "Missed"),
    ]:
        with col:
            st.markdown(
                f'<div class="metric-box"><div class="num">{stats[key]}</div>'
                f'<div class="lbl">{label}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")
    st.markdown("#### 📋 My Tasks")

    tasks = tm.get_tasks(user["id"])
    if not tasks:
        st.info("No tasks yet — add one from the sidebar! 🚀")
        voice.announce("task_list_empty")
        return

    # Filter
    filter_status = st.selectbox(
        "Filter by status", ["all", "pending", "completed", "missed"],
        label_visibility="collapsed"
    )
    if filter_status != "all":
        tasks = [t for t in tasks if t["status"] == filter_status]

    for task in tasks:
        locked = task["status"] == "missed"
        with st.container():
            st.markdown(
                f'<div class="card">'
                f'<b>#{task["id"]}  {task["name"]}</b>&nbsp;&nbsp;'
                f'{badge(task["status"])}<br>'
                f'<small style="color:#64748b">Created: {fmt_dt(task["created_at"])} &nbsp;|&nbsp; Due: {fmt_dt(task["due_at"])}</small>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if not locked and task["status"] == "pending":
                col_done, col_del, _ = st.columns([1, 1, 6])
                with col_done:
                    if st.button("✅ Done", key=f"done_{task['id']}"):
                        ok, msg = tm.complete_task(task["id"], user["id"])
                        if ok:
                            notify_browser("Task Completed! 🎉", msg)
                            st.success(msg)
                        else:
                            st.warning(msg)
                        st.rerun()
                with col_del:
                    if st.button("🗑 Delete", key=f"del_{task['id']}"):
                        tm.delete_task(task["id"], user["id"])
                        st.rerun()
            elif locked:
                st.caption("🔒 Missed — this task is locked and cannot be edited.")


def render_add_task(user: dict) -> None:
    st.markdown("#### ➕ Add New Task")

    method = st.radio("Input method", ["⌨️ Type", "🎙️ Voice"], horizontal=True)

    task_name = ""
    due_input = ""

    if method == "⌨️ Type":
        with st.form("add_task_form"):
            task_name = st.text_input("Task name")
            due_input = st.text_input(
                "Due date/time (e.g. 'tomorrow at 3pm' or '2025-12-31 18:00')",
                placeholder="optional"
            )
            submitted = st.form_submit_button("Add Task", use_container_width=True)

        if submitted and task_name:
            _save_task(user, task_name, due_input)

    else:  # Voice
        st.info("🎙️ Click **Listen** to speak your task.")
        if st.button("🎙️ Listen", use_container_width=True):
            with st.spinner("Listening…"):
                spoken = voice.listen()
            if spoken:
                st.success(f"Heard: **{spoken}**")
                parsed = nlu.parse_command(spoken)
                if parsed["task_name"]:
                    _save_task(user, parsed["task_name"], parsed.get("due_datetime"))
                else:
                    st.warning("Couldn't extract task name. Please rephrase.")
            else:
                st.error("No speech detected. Check your microphone.")


def _save_task(user: dict, name: str, due_raw) -> None:
    """
    Resolve due date (string or pre-parsed ISO) and save.
    """
    due_iso = None
    if due_raw:
        if isinstance(due_raw, str) and "T" in due_raw or (
            isinstance(due_raw, str) and len(due_raw) >= 10
            and due_raw[4] == "-"
        ):
            # Looks like ISO — accept directly
            due_iso = due_raw
        else:
            # Parse natural language
            try:
                import dateparser
                dt = dateparser.parse(str(due_raw), settings={"PREFER_DATES_FROM": "future"})
                due_iso = dt.isoformat(timespec="seconds") if dt else None
            except Exception:
                due_iso = None

    try:
        task = tm.add_task(user["id"], name, due_iso)
        st.success(f"✅ Task **'{task['name']}'** added!")
        if due_iso:
            st.info(f"Due: {fmt_dt(due_iso)}")
    except ValueError as e:
        st.error(str(e))


def render_ai_command(user: dict) -> None:
    st.markdown("#### 🤖 AI Natural Language Command")
    st.caption("Type (or speak) a command in any language. Examples: "
               "*'Add buy groceries by Friday'*, "
               "*'Eliminar tarea 3'*, "
               "*'내일 오후 3시에 회의 추가'*")

    col_text, col_voice = st.columns([4, 1])
    with col_text:
        cmd = st.text_input("Your command", key="ai_cmd_text",
                            placeholder="e.g. 'Complete task 2'")
    with col_voice:
        st.write("")
        if st.button("🎙️", key="ai_voice_btn", help="Speak command"):
            with st.spinner("Listening…"):
                spoken = voice.listen()
            if spoken:
                cmd = spoken
                st.info(f"Heard: **{spoken}**")

    if st.button("▶ Execute", use_container_width=True) and cmd:
        with st.spinner("Parsing…"):
            parsed = nlu.parse_command(cmd)

        st.json(parsed)   # show parsed intent for transparency

        intent = parsed.get("intent", "unknown")
        tid    = parsed.get("task_id")
        tname  = parsed.get("task_name")
        tdue   = parsed.get("due_datetime")

        if intent == "add_task":
            if tname:
                _save_task(user, tname, tdue)
            else:
                st.warning("Task name not detected. Please be more specific.")

        elif intent == "delete_task":
            if tid:
                ok = tm.delete_task(tid, user["id"])
                st.success(f"Deleted task #{tid}.") if ok else st.error("Task not found.")
            else:
                st.warning("Which task to delete? Include the task number.")

        elif intent == "complete_task":
            if tid:
                ok, msg = tm.complete_task(tid, user["id"])
                (st.success if ok else st.warning)(msg)
            else:
                st.warning("Which task to complete? Include the task number.")

        elif intent == "show_tasks":
            st.rerun()   # navigate back to dashboard implicitly

        elif intent == "update_task":
            if tid:
                ok, msg = tm.update_task(tid, user["id"], name=tname, due_at=tdue)
                (st.success if ok else st.warning)(msg)
            else:
                st.warning("Specify the task ID to update.")

        else:
            st.info("Intent not recognized. Try: 'add', 'delete', 'complete', 'show tasks'.")


def render_settings(user: dict) -> None:
    st.markdown("#### ⚙️ Settings")
    st.write(f"**Username:** {user['username']}")
    st.write(f"**Member since:** {fmt_dt(user.get('created_at', ''))}")
    st.markdown("---")

    # Voice test
    if st.button("🔊 Test Voice Output"):
        voice.speak("Hello! Voice is working correctly.")
        st.success("Spoke a test message.")

    # Offline AI info
    with st.expander("🤖 AI / NLP Status"):
        try:
            import dateparser
            st.success("✅ dateparser (multilingual NLU) — installed")
        except ImportError:
            st.warning("⚠️ dateparser not installed. Run: pip install dateparser")
        try:
            import speech_recognition
            st.success("✅ SpeechRecognition (STT) — installed")
        except ImportError:
            st.warning("⚠️ SpeechRecognition not installed. Run: pip install SpeechRecognition")
        try:
            import pyttsx3
            st.success("✅ pyttsx3 (TTS) — installed")
        except ImportError:
            st.warning("⚠️ pyttsx3 not installed. Run: pip install pyttsx3")
        try:
            import requests
            r = requests.get("http://localhost:11434", timeout=2)
            st.success("✅ Ollama (offline LLM) — running")
        except Exception:
            st.info("ℹ️ Ollama not detected. Rule-based NLU will be used instead.")

    st.markdown("---")
    if st.button("🚪 Logout", type="primary"):
        auth_mod.logout()
        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# SIDEBAR NAV
# ═════════════════════════════════════════════════════════════════════════════

def render_sidebar(user: dict) -> str:
    with st.sidebar:
        st.markdown("## ✅ AI To-Do")
        st.markdown(f"👤 **{user['username']}**")
        st.markdown("---")
        pages = {
            "📊 Dashboard":   "dashboard",
            "➕ Add Task":    "add_task",
            "🤖 AI Command":  "ai_command",
            "⚙️ Settings":    "settings",
        }
        for label, key in pages.items():
            if st.button(label, use_container_width=True, key=f"nav_{key}"):
                st.session_state["page"] = key

        st.markdown("---")
        # Quick stats in sidebar
        stats = tm.get_task_stats(user["id"])
        st.metric("Pending",   stats["pending"])
        st.metric("Completed", stats["completed"])
        st.metric("Missed",    stats["missed"])

    return st.session_state.get("page", "dashboard")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    # Try to restore session
    auth_mod.restore_session()
    user = auth_mod.current_user()

    if not user:
        render_auth_page()
        return

    page = render_sidebar(user)

    if page == "dashboard":
        render_dashboard(user)
    elif page == "add_task":
        render_add_task(user)
    elif page == "ai_command":
        render_ai_command(user)
    elif page == "settings":
        render_settings(user)
    else:
        render_dashboard(user)


if __name__ == "__main__":
    main()
