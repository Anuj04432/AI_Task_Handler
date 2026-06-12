"""
auth/auth.py
============
Authentication logic: register, login, session token generation, and
Streamlit session-state helpers for persistent login.
"""

import secrets
import streamlit as st
from modules.database import db


def generate_token() -> str:
    """Generate a cryptographically secure 64-hex-char session token."""
    return secrets.token_hex(32)


def register(username: str, password: str) -> tuple[bool, str]:
    """
    Register a new user.
    Returns (success: bool, message: str).
    """
    if not username or not password:
        return False, "Username and password cannot be empty."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    user = db.create_user(username, password)
    if user is None:
        return False, f"Username '{username}' is already taken."
    return True, f"Account created! Welcome, {username}."


def login(username: str, password: str) -> tuple[bool, str]:
    """
    Authenticate and persist session.
    Returns (success: bool, message: str).
    On success, sets st.session_state['user'] and saves token to DB.
    """
    user = db.authenticate_user(username, password)
    if not user:
        return False, "Invalid username or password."

    token = generate_token()
    db.save_session(user["id"], token)

    # Persist in Streamlit session state
    st.session_state["user"] = user
    st.session_state["session_token"] = token
    return True, f"Welcome back, {user['username']}!"


def logout() -> None:
    """Clear session from DB and Streamlit state."""
    token = st.session_state.get("session_token")
    if token:
        db.delete_session(token)
    st.session_state.pop("user", None)
    st.session_state.pop("session_token", None)


def restore_session() -> bool:
    """
    Try to restore a previous login from session_state token.
    Returns True if the user is (or becomes) authenticated.
    """
    # Already loaded in this run
    if st.session_state.get("user"):
        return True

    # Check for a persisted token stored in the query params trick
    # (Streamlit doesn't have cookies natively; we store token in session_state
    #  which persists for the browser tab lifetime — good enough for most use cases)
    token = st.session_state.get("session_token")
    if token:
        user = db.get_session(token)
        if user:
            st.session_state["user"] = user
            return True

    return False


def current_user() -> dict | None:
    """Return the currently logged-in user dict, or None."""
    return st.session_state.get("user")
