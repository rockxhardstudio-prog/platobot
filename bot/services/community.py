from bot.database.db import get_conn

def set_info(text: str, user_id: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE community_content SET info_text = ?, updated_by = ? WHERE id = 1", (text, user_id))
    conn.commit()

def get_info() -> str | None:
    row = get_conn().execute("SELECT info_text FROM community_content WHERE id = 1").fetchone()
    return row["info_text"] if row else None

def set_rules(text: str, user_id: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE community_content SET rules_text = ?, updated_by = ? WHERE id = 1", (text, user_id))
    conn.commit()

def get_rules() -> str | None:
    row = get_conn().execute("SELECT rules_text FROM community_content WHERE id = 1").fetchone()
    return row["rules_text"] if row else None

def set_announcement(text: str | None, user_id: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE community_content SET announcement_text = ?, updated_by = ? WHERE id = 1", (text, user_id))
    conn.commit()

def get_announcement() -> str | None:
    row = get_conn().execute("SELECT announcement_text FROM community_content WHERE id = 1").fetchone()
    return row["announcement_text"] if row else None
