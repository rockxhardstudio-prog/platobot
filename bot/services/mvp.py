from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from bot.config import config
from bot.database.db import get_conn


def is_admin(user_id: str) -> bool:
    if user_id in config.admin_ids:
        return True
    row = get_conn().execute("SELECT role FROM permissions WHERE user_id=?", (user_id,)).fetchone()
    return bool(row and row["role"] == "admin")


def audit(actor_id: str, action: str, target_id: str | None = None, detail: str = "") -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_log (actor_id, action, target_id, detail) VALUES (?, ?, ?, ?)",
        (actor_id, action, target_id, detail),
    )
    conn.commit()


def set_spam_message(message_id: int, text: str, actor_id: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO spam_messages (id, message_text, created_by, updated_at) VALUES (?, ?, ?, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET message_text=excluded.message_text, updated_at=datetime('now')",
        (message_id, text, actor_id),
    )
    conn.commit()
    audit(actor_id, "spam_message_set", str(message_id), text)


def get_spam_message(message_id: int) -> str | None:
    row = get_conn().execute("SELECT message_text FROM spam_messages WHERE id=?", (message_id,)).fetchone()
    return row["message_text"] if row else None


def valid_invite_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def set_invite(url: str, actor_id: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO invite_config (id, invite_url, updated_by, updated_at) VALUES (1, ?, ?, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET invite_url=excluded.invite_url, updated_by=excluded.updated_by, updated_at=datetime('now')",
        (url, actor_id),
    )
    conn.commit()
    audit(actor_id, "invite_set", None, url)


def get_invite() -> str | None:
    row = get_conn().execute("SELECT invite_url FROM invite_config WHERE id=1").fetchone()
    return row["invite_url"] if row else None


def set_user_mapping(mapping_id: int, username: str, actor_id: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO user_id_map (id, username, created_by, updated_at) VALUES (?, ?, ?, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET username=excluded.username, updated_at=datetime('now')",
        (mapping_id, username, actor_id),
    )
    conn.commit()
    audit(actor_id, "user_mapping_set", str(mapping_id), username)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def activity_summary(group_id: str, now: datetime | None = None) -> tuple[int, int, list[tuple[str, int]], str]:
    local_zone = ZoneInfo(config.bot_timezone)
    local_now = (now or datetime.now(timezone.utc)).astimezone(local_zone)
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    counts: dict[str, int] = {}
    for row in get_conn().execute("SELECT username, created_at FROM messages WHERE group_id=?", (group_id,)):
        try:
            occurred = _parse_timestamp(row["created_at"]).astimezone(local_zone)
        except ValueError:
            continue
        if day_start <= occurred < day_end:
            username = row["username"] or "Unknown"
            counts[username] = counts.get(username, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))[:10]
    return sum(counts.values()), len(counts), ranked, f"{local_now.strftime('%B')} {local_now.day}"
