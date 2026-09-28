import sqlite3
from bot.database.db import get_conn

def add_event(name: str, event_date: str, description: str, user_id: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO events (name, event_date, description, created_by) VALUES (?, ?, ?, ?)",
        (name, event_date, description, user_id)
    )
    conn.commit()

def delete_event(name: str) -> bool:
    conn = get_conn()
    cursor = conn.execute("DELETE FROM events WHERE name = ? COLLATE NOCASE", (name,))
    conn.commit()
    return cursor.rowcount > 0

def get_upcoming_events() -> list[sqlite3.Row]:
    return get_conn().execute(
        "SELECT name, event_date, description FROM events WHERE status = 'upcoming' ORDER BY event_date ASC, created_at ASC"
    ).fetchall()
