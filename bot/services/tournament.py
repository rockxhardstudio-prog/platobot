import sqlite3
from bot.database.db import get_conn, transaction


def get_active_tournament() -> sqlite3.Row | None:
    return get_conn().execute("SELECT * FROM tournaments WHERE is_active = 1").fetchone()


def create_tournament(name: str, user_id: str) -> None:
    with transaction() as conn:
        conn.execute("UPDATE tournaments SET is_active = 0 WHERE is_active = 1")
        conn.execute(
            "INSERT INTO tournaments (name, created_by, is_active) VALUES (?, ?, 1)",
            (name, user_id),
        )


def update_active_tournament_field(field: str, value: str | int) -> bool:
    allowed_fields = {
        "game", "event_date", "event_time", "registration_time",
        "format", "max_slots", "prize_info", "description_text",
        "rules_text", "host_mode", "host",
    }
    if field not in allowed_fields:
        return False
    if field == "max_slots":
        try:
            val_int = int(value)
            if val_int <= 0:
                return False
            value = val_int
        except (ValueError, TypeError):
            return False

    with transaction() as conn:
        row = conn.execute("SELECT id FROM tournaments WHERE is_active = 1").fetchone()
        if not row:
            return False
        t_id = row["id"]
        conn.execute(f"UPDATE tournaments SET {field} = ?, updated_at = datetime('now') WHERE is_active = 1", (value,))

        if field == "max_slots" and value is not None:
            count_reg = conn.execute(
                "SELECT COUNT(*) as c FROM registrations WHERE tournament_id = ? AND status = 'registered'",
                (t_id,),
            ).fetchone()["c"]
            available = value - count_reg
            if available > 0:
                waitlisted_rows = conn.execute(
                    "SELECT id FROM registrations WHERE tournament_id = ? AND status = 'waitlisted' ORDER BY registered_at ASC LIMIT ?",
                    (t_id, available),
                ).fetchall()
                for w in waitlisted_rows:
                    conn.execute("UPDATE registrations SET status = 'registered' WHERE id = ?", (w["id"],))
    return True


def clear_active_tournament() -> bool:
    with transaction() as conn:
        row = conn.execute("SELECT id FROM tournaments WHERE is_active = 1").fetchone()
        if not row:
            return False
        conn.execute("UPDATE tournaments SET status = 'completed', is_active = 0, updated_at = datetime('now') WHERE is_active = 1")
    return True


def set_active_tournament_status(status: str) -> bool:
    allowed_statuses = {"draft", "open", "closed", "ongoing", "completed"}
    if status not in allowed_statuses:
        return False
    with transaction() as conn:
        row = conn.execute("SELECT id FROM tournaments WHERE is_active = 1").fetchone()
        if not row:
            return False
        conn.execute("UPDATE tournaments SET status = ?, updated_at = datetime('now') WHERE is_active = 1", (status,))
    return True


def register_user(user_id: str, username: str, game_tag: str | None) -> str:
    with transaction() as conn:
        tourney = conn.execute("SELECT id, status, max_slots FROM tournaments WHERE is_active = 1").fetchone()
        if not tourney:
            return "No active tournament right now."
        if tourney["status"] != "open":
            return "Registration is currently closed."

        t_id = tourney["id"]

        existing = conn.execute(
            "SELECT id, status FROM registrations WHERE tournament_id = ? AND user_id = ?",
            (t_id, user_id),
        ).fetchone()
        if existing and existing["status"] in ("registered", "waitlisted"):
            return f"@{username} You are already {existing['status']} for this tournament."

        count_row = conn.execute(
            "SELECT COUNT(*) as c FROM registrations WHERE tournament_id = ? AND status = 'registered'",
            (t_id,),
        ).fetchone()
        current_registered = count_row["c"]

        status = "registered"
        if tourney["max_slots"] is not None and current_registered >= tourney["max_slots"]:
            status = "waitlisted"

        if existing and existing["status"] == "cancelled":
            conn.execute(
                "UPDATE registrations SET status = ?, username = ?, game_tag = ?, registered_at = datetime('now') WHERE id = ?",
                (status, username, game_tag, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO registrations (tournament_id, user_id, username, game_tag, status) VALUES (?, ?, ?, ?, ?)",
                (t_id, user_id, username, game_tag, status),
            )

        if status == "waitlisted":
            waitlist_pos_row = conn.execute(
                "SELECT COUNT(*) as c FROM registrations WHERE tournament_id = ? AND status = 'waitlisted'",
                (t_id,),
            ).fetchone()
            return f"@{username} Added to waitlist (position {waitlist_pos_row['c']})."

        slots_text = f" ({current_registered + 1}/{tourney['max_slots']})" if tourney["max_slots"] else ""
        return f"@{username} Registered successfully!{slots_text}"


def unregister_user(user_id: str, username: str = "") -> str:
    with transaction() as conn:
        tourney = conn.execute("SELECT id, max_slots FROM tournaments WHERE is_active = 1").fetchone()
        if not tourney:
            return "No active tournament right now."

        t_id = tourney["id"]

        existing = conn.execute(
            "SELECT id, status, username FROM registrations WHERE tournament_id = ? AND user_id = ? AND status IN ('registered', 'waitlisted')",
            (t_id, user_id),
        ).fetchone()
        if not existing:
            user_tag = f"@{username} " if username else ""
            return f"{user_tag}You are not registered for the active tournament."

        uname = existing["username"] or username or user_id
        conn.execute("UPDATE registrations SET status = 'cancelled' WHERE id = ?", (existing["id"],))

        if existing["status"] == "registered":
            waitlisted = conn.execute(
                "SELECT id FROM registrations WHERE tournament_id = ? AND status = 'waitlisted' ORDER BY registered_at ASC LIMIT 1",
                (t_id,),
            ).fetchone()
            if waitlisted:
                conn.execute("UPDATE registrations SET status = 'registered' WHERE id = ?", (waitlisted["id"],))

        return f"@{uname} Your registration has been cancelled."


def get_participants() -> list[sqlite3.Row]:
    tourney = get_active_tournament()
    if not tourney:
        return []
    return get_conn().execute(
        "SELECT username, game_tag, status FROM registrations WHERE tournament_id = ? AND status IN ('registered', 'waitlisted') ORDER BY status, registered_at ASC",
        (tourney["id"],),
    ).fetchall()
