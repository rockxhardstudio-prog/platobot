from bot.database.db import get_conn


def already_processed(message_id: str) -> bool:
    row = get_conn().execute(
        "SELECT 1 FROM processed_messages WHERE message_id=?", (message_id,)
    ).fetchone()
    return row is not None


def mark_processed(message_id: str):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)", (message_id,))
    conn.commit()
