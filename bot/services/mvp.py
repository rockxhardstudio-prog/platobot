from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from bot.config import config
from bot.database.db import get_conn

ROLE_RANKS = {
    "banned": -1,
    "user": 0,
    "mod": 1,
    "admin": 2,
    "owner": 3,
}

DEFAULT_CONFIG_KV = {
    "timezone": config.bot_timezone or "Asia/Kolkata",
    "summon_timeout_seconds": "300",
    "english_only": "true",
    "spam_threshold": "4",
    "xp_cooldown_seconds": "45",
}


PERMANENT_OWNERS = {"tuhin", "hawtshot", "zuriah", "ad4rshh"}


def _seed_owners_lower() -> set[str]:
    return {uid.strip().lower() for uid in config.admin_ids if uid.strip()} | PERMANENT_OWNERS


def get_role(user_id: str) -> str:
    clean = (user_id or "").strip().lstrip("@")
    if not clean:
        return "user"
    if clean in config.admin_ids or clean.lower() in _seed_owners_lower():
        return "owner"
    conn = get_conn()
    row = conn.execute(
        "SELECT role FROM permissions WHERE LOWER(user_id) = LOWER(?)",
        (clean,),
    ).fetchone()
    if row and row["role"] in ROLE_RANKS:
        return str(row["role"])
    return "user"


def is_owner(user_id: str) -> bool:
    return ROLE_RANKS.get(get_role(user_id), 0) >= ROLE_RANKS["owner"]


def is_admin(user_id: str) -> bool:
    return ROLE_RANKS.get(get_role(user_id), 0) >= ROLE_RANKS["admin"]


def is_staff(user_id: str) -> bool:
    return ROLE_RANKS.get(get_role(user_id), 0) >= ROLE_RANKS["mod"]


def set_staff_role(target_user: str, role: str, actor_id: str) -> str:
    clean_target = target_user.strip().lstrip("@")
    clean_role = role.strip().lower()
    if clean_role not in {"mod", "admin"}:
        raise ValueError("Role must be 'mod' or 'admin'.")
    if not clean_target:
        raise ValueError("Target user cannot be empty.")

    conn = get_conn()
    existing = conn.execute(
        "SELECT user_id FROM permissions WHERE LOWER(user_id) = LOWER(?)",
        (clean_target,),
    ).fetchone()
    key = existing["user_id"] if existing else clean_target
    conn.execute(
        "INSERT INTO permissions (user_id, role, updated_by, updated_at) VALUES (?, ?, ?, datetime('now')) "
        "ON CONFLICT(user_id) DO UPDATE SET role=excluded.role, updated_by=excluded.updated_by, updated_at=datetime('now')",
        (key, clean_role, actor_id),
    )
    conn.commit()
    audit(actor_id, "staff_role_set", key, clean_role)
    return key


def remove_staff_role(target_user: str, actor_id: str) -> bool:
    clean_target = target_user.strip().lstrip("@")
    if not clean_target:
        return False
    if clean_target in config.admin_ids or clean_target.lower() in _seed_owners_lower():
        raise PermissionError("Cannot remove a seed owner defined in ADMIN_IDS.")
    conn = get_conn()
    existing = conn.execute(
        "SELECT user_id, role FROM permissions WHERE LOWER(user_id) = LOWER(?)",
        (clean_target,),
    ).fetchone()
    if not existing or existing["role"] not in {"mod", "admin"}:
        return False
    conn.execute(
        "UPDATE permissions SET role='user', updated_by=?, updated_at=datetime('now') WHERE user_id=?",
        (actor_id, existing["user_id"]),
    )
    conn.commit()
    audit(actor_id, "staff_role_removed", existing["user_id"], "user")
    return True


def list_staff() -> list[tuple[str, str]]:
    staff_map: dict[str, tuple[str, str]] = {}
    for uid in sorted(set(config.admin_ids) | PERMANENT_OWNERS, key=lambda s: s.lower()):
        clean = uid.strip()
        if clean and clean.lower() != (config.bot_plato_user_id or "").lower():
            staff_map[clean.lower()] = (clean, "owner")

    conn = get_conn()
    for row in conn.execute(
        "SELECT user_id, role FROM permissions WHERE role IN ('owner', 'admin', 'mod') ORDER BY user_id ASC"
    ):
        uid = str(row["user_id"])
        role = str(row["role"])
        if uid.lower() in staff_map and staff_map[uid.lower()][1] == "owner":
            continue
        staff_map[uid.lower()] = (uid, role)

    return sorted(
        staff_map.values(),
        key=lambda item: (-ROLE_RANKS.get(item[1], 0), item[0].lower()),
    )


def get_config_value(key: str, default: str | None = None) -> str | None:
    clean_key = key.strip().lower()
    row = get_conn().execute("SELECT value FROM config_kv WHERE key=?", (clean_key,)).fetchone()
    if row:
        return str(row["value"])
    if default is not None:
        return default
    return DEFAULT_CONFIG_KV.get(clean_key)


def set_config_value(key: str, value: str, actor_id: str) -> None:
    clean_key = key.strip().lower()
    clean_val = value.strip()
    conn = get_conn()
    conn.execute(
        "INSERT INTO config_kv (key, value, updated_by, updated_at) VALUES (?, ?, ?, datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by, updated_at=datetime('now')",
        (clean_key, clean_val, actor_id),
    )
    conn.commit()
    audit(actor_id, "config_set", clean_key, clean_val)


def list_config_values() -> dict[str, str]:
    merged = dict(DEFAULT_CONFIG_KV)
    for row in get_conn().execute("SELECT key, value FROM config_kv ORDER BY key ASC"):
        merged[str(row["key"])] = str(row["value"])
    return merged


def get_bridge_state(now: datetime | None = None) -> dict[str, object]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM bridge_state WHERE id = 1").fetchone()
    main_id = config.main_group_id or "main"
    main_title = config.main_group_title or "-» NOVΛ ⟡ BLΛZΞ «-"
    if not row:
        return {
            "target_group_id": main_id,
            "target_group_title": main_title,
            "summon_expires_at": None,
            "summon_remaining_seconds": 0,
            "navigation_pending": False,
            "current_group_id": None,
            "current_group_title": None,
            "last_heartbeat_at": None,
            "last_error": None,
        }

    current_utc = now or datetime.now(timezone.utc)
    target_group_id = row["target_group_id"] or main_id
    target_group_title = row["target_group_title"] or main_title
    expires_raw = row["summon_expires_at"]
    nav_pending = bool(row["navigation_pending"]) if "navigation_pending" in row.keys() else False
    remaining_seconds = 0

    if expires_raw and target_group_id not in (main_id, "off"):
        try:
            expires_dt = _parse_timestamp(expires_raw)
            diff = (expires_dt - current_utc).total_seconds()
            if diff <= 0:
                target_group_id = main_id
                target_group_title = main_title
                expires_raw = None
                nav_pending = True
                conn.execute(
                    "UPDATE bridge_state SET target_group_id=?, target_group_title=?, summon_expires_at=NULL, navigation_pending=1, updated_at=datetime('now') WHERE id=1",
                    (main_id, main_title),
                )
                conn.commit()
            else:
                remaining_seconds = int(diff)
        except ValueError:
            pass

    return {
        "target_group_id": target_group_id,
        "target_group_title": target_group_title,
        "summon_expires_at": expires_raw,
        "summon_remaining_seconds": remaining_seconds,
        "navigation_pending": nav_pending,
        "current_group_id": row["current_group_id"],
        "current_group_title": row["current_group_title"],
        "last_heartbeat_at": row["last_heartbeat_at"],
        "last_error": row["last_error"],
    }


def summon_to_staff(
    actor_id: str,
    duration_seconds: int | None = None,
    now: datetime | None = None,
    target_title_override: str | None = None,
) -> int:
    if duration_seconds is None:
        raw_cfg = get_config_value("summon_timeout_seconds", "300") or "300"
        try:
            duration_seconds = max(30, int(raw_cfg))
        except ValueError:
            duration_seconds = 300

    current_utc = now or datetime.now(timezone.utc)
    expires_at = (current_utc + timedelta(seconds=duration_seconds)).isoformat()
    staff_id = config.storage_group_id or "storage"
    staff_title = target_title_override or "-⊹ STAFF ⟡ GROUP ⊹-"

    conn = get_conn()
    conn.execute(
        "INSERT INTO bridge_state (id, target_group_id, target_group_title, summon_expires_at, navigation_pending, updated_at) "
        "VALUES (1, ?, ?, ?, 1, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET target_group_id=excluded.target_group_id, "
        "target_group_title=excluded.target_group_title, summon_expires_at=excluded.summon_expires_at, "
        "navigation_pending=1, updated_at=datetime('now')",
        (staff_id, staff_title, expires_at),
    )
    conn.commit()
    audit(actor_id, "summon_to_staff", staff_id, f"seconds={duration_seconds}; title={staff_title}")
    return duration_seconds


def return_to_main(actor_id: str) -> None:
    main_id = config.main_group_id or "main"
    main_title = config.main_group_title or "-» NOVΛ ⟡ BLΛZΞ «-"
    conn = get_conn()
    conn.execute(
        "INSERT INTO bridge_state (id, target_group_id, target_group_title, summon_expires_at, navigation_pending, updated_at) "
        "VALUES (1, ?, ?, NULL, 1, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET target_group_id=excluded.target_group_id, "
        "target_group_title=excluded.target_group_title, summon_expires_at=NULL, "
        "navigation_pending=1, updated_at=datetime('now')",
        (main_id, main_title),
    )
    conn.commit()
    audit(actor_id, "return_to_main", main_id, "")


def turn_off_gc(actor_id: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO bridge_state (id, target_group_id, target_group_title, summon_expires_at, navigation_pending, updated_at) "
        "VALUES (1, 'off', 'OFF', NULL, 1, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET target_group_id='off', target_group_title='OFF', "
        "summon_expires_at=NULL, navigation_pending=1, updated_at=datetime('now')"
    )
    conn.commit()
    audit(actor_id, "turn_off_gc", "off", "")


def resume_from_off(group_id: str | None = None, group_title: str | None = None) -> None:
    gid = group_id or config.main_group_id or "main"
    title = group_title or config.main_group_title or "-» NOVΛ ⟡ BLΛZΞ «-"
    conn = get_conn()
    conn.execute(
        "UPDATE bridge_state SET target_group_id=?, target_group_title=?, navigation_pending=0, updated_at=datetime('now') WHERE id=1 AND target_group_id='off'",
        (gid, title),
    )
    conn.commit()


def update_bridge_heartbeat(
    current_group_id: str | None,
    current_group_title: str | None,
    last_error: str | None = None,
    ack_navigation: bool = False,
) -> dict[str, object]:
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    if ack_navigation:
        conn.execute(
            "UPDATE bridge_state SET current_group_id=?, current_group_title=?, last_heartbeat_at=?, last_error=?, navigation_pending=0, updated_at=datetime('now') WHERE id=1",
            (current_group_id, current_group_title, now_iso, last_error),
        )
    else:
        conn.execute(
            "UPDATE bridge_state SET current_group_id=?, current_group_title=?, last_heartbeat_at=?, last_error=?, updated_at=datetime('now') WHERE id=1",
            (current_group_id, current_group_title, now_iso, last_error),
        )
    conn.commit()
    return get_bridge_state()


def get_outbox_pending_count() -> int:
    row = get_conn().execute(
        "SELECT COUNT(*) AS cnt FROM outbox WHERE status IN ('pending', 'sending')"
    ).fetchone()
    return int(row["cnt"]) if row else 0


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


def activity_summary(
    group_id: str,
    now: datetime | None = None,
    period: str = "today",
) -> tuple[int, int, list[tuple[str, int]], str]:
    tz_name = get_config_value("timezone", config.bot_timezone) or config.bot_timezone
    try:
        local_zone = ZoneInfo(tz_name)
    except Exception:
        local_zone = ZoneInfo(config.bot_timezone)

    local_now = (now or datetime.now(timezone.utc)).astimezone(local_zone)
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period.strip().lower() == "yesterday":
        day_start = day_start - timedelta(days=1)
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
    return sum(counts.values()), len(counts), ranked, f"{day_start.strftime('%B')} {day_start.day}"
