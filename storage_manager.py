"""
SQLite-backed storage for interview chat sessions.
Stores Q&A pairs per session with naming, rename, and delete support.
DB stored at ~/.interviewagent/chats.db
"""

import sqlite3
import datetime
from config import DB_PATH, ensure_dirs


def _get_connection() -> sqlite3.Connection:
    """Get a database connection, creating tables if needed."""
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            ended_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    return conn


def start_session() -> int:
    """Start a new interview session. Returns the session ID."""
    conn = _get_connection()
    now = datetime.datetime.now().isoformat()
    cursor = conn.execute(
        "INSERT INTO sessions (name, created_at) VALUES (?, ?)",
        (f"Interview {now[:16].replace('T', ' ')}", now),
    )
    conn.commit()
    session_id = cursor.lastrowid
    conn.close()
    return session_id


def end_session(session_id: int, name: str = None):
    """End a session, optionally setting a name."""
    conn = _get_connection()
    now = datetime.datetime.now().isoformat()
    if name:
        conn.execute(
            "UPDATE sessions SET ended_at = ?, name = ? WHERE id = ?",
            (now, name, session_id),
        )
    else:
        conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (now, session_id),
        )
    conn.commit()
    conn.close()


def add_message(session_id: int, role: str, content: str):
    """Add a Q&A message to a session. Role is 'question' or 'answer'."""
    conn = _get_connection()
    now = datetime.datetime.now().isoformat()
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, role, content, now),
    )
    conn.commit()
    conn.close()


def get_all_sessions() -> list:
    """Get all sessions ordered by most recent first."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT id, name, created_at, ended_at FROM sessions ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_messages(session_id: int) -> list:
    """Get all messages for a session in chronological order."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT role, content, timestamp FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def rename_session(session_id: int, new_name: str):
    """Rename a session."""
    conn = _get_connection()
    conn.execute("UPDATE sessions SET name = ? WHERE id = ?", (new_name, session_id))
    conn.commit()
    conn.close()


def delete_session(session_id: int):
    """Delete a session and all its messages."""
    conn = _get_connection()
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
