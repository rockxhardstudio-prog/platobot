import sqlite3
from bot.database.db import get_conn

def add_warning(user_id: str, username: str, reason: str, admin_id: str) -> int:
    conn = get_conn()
    conn.execute(
        "INSERT INTO warnings (user_id, username, reason, issued_by) VALUES (?, ?, ?, ?)",
        (user_id, username, reason, admin_id)
    )
    conn.commit()
    
    row = conn.execute("SELECT COUNT(*) as c FROM warnings WHERE user_id = ?", (user_id,)).fetchone()
    return row["c"]

def get_warnings(username: str) -> list[sqlite3.Row]:
    return get_conn().execute(
        "SELECT reason, created_at FROM warnings WHERE username = ? COLLATE NOCASE ORDER BY created_at ASC",
        (username,)
    ).fetchall()
    
def clear_warnings(username: str) -> int:
    conn = get_conn()
    cursor = conn.execute("DELETE FROM warnings WHERE username = ? COLLATE NOCASE", (username,))
    conn.commit()
    return cursor.rowcount
