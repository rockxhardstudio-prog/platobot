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

def set_insta(url: str | None, user_id: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE community_content SET insta_url = ?, updated_by = ?, updated_at = datetime('now') WHERE id = 1",
        (url, user_id),
    )
    conn.commit()

def get_insta() -> str | None:
    row = get_conn().execute("SELECT insta_url FROM community_content WHERE id = 1").fetchone()
    return row["insta_url"] if row else None

def set_dc(url: str | None, user_id: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE community_content SET dc_url = ?, updated_by = ?, updated_at = datetime('now') WHERE id = 1",
        (url, user_id),
    )
    conn.commit()

def get_dc() -> str | None:
    row = get_conn().execute("SELECT dc_url FROM community_content WHERE id = 1").fetchone()
    return row["dc_url"] if row else None

def get_socials() -> dict[str, str | None]:
    row = get_conn().execute("SELECT insta_url, dc_url FROM community_content WHERE id = 1").fetchone()
    if not row:
        return {"insta": None, "dc": None}
    return {"insta": row["insta_url"], "dc": row["dc_url"]}


def set_tourney_rules(text: str | None, user_id: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE community_content SET tourney_rules_text = ?, updated_by = ?, updated_at = datetime('now') WHERE id = 1",
        (text, user_id),
    )
    conn.commit()


def get_tourney_rules() -> str | None:
    row = get_conn().execute("SELECT tourney_rules_text FROM community_content WHERE id = 1").fetchone()
    if row and row["tourney_rules_text"]:
        return str(row["tourney_rules_text"])
    t_row = get_conn().execute("SELECT rules_text FROM tournaments WHERE is_active = 1").fetchone()
    if t_row and t_row["rules_text"]:
        return str(t_row["rules_text"])
    return None
