import hashlib
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bot.config import config
from bot.database.db import get_conn
from bot.models.message import IncomingMessage
from bot.services import moderation, mvp

XP_PER_LEVEL = 100

RANK_TIERS: list[tuple[int, str]] = [
    (21, "Apex"),
    (16, "Commander"),
    (12, "Sentinel"),
    (8, "Vanguard"),
    (5, "Operative"),
    (3, "Initiate"),
    (1, "Recruit"),
]

# In-memory cooldown tracker for fast checks (persisted in xp_profiles.last_xp_at as well)
_last_xp_ts: dict[str, float] = {}


def reset_runtime_state() -> None:
    _last_xp_ts.clear()


def level_for_xp(total_xp: int) -> int:
    return max(1, (max(0, int(total_xp)) // XP_PER_LEVEL) + 1)


def next_level_xp(level: int) -> int:
    return max(1, int(level)) * XP_PER_LEVEL


def rank_title_for_level(level: int) -> str:
    lvl = max(1, int(level))
    for min_lvl, title in RANK_TIERS:
        if lvl >= min_lvl:
            return title
    return "Recruit"


def _normalize_text_hash(text: str) -> str:
    cleaned = " ".join((text or "").strip().lower().split())
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:16]


def ensure_profile(user_id: str, username: str) -> dict[str, object]:
    conn = get_conn()
    clean_uid = user_id.strip().lstrip("@").lower()
    clean_uname = username.strip().lstrip("@") or clean_uid
    row = conn.execute(
        "SELECT * FROM xp_profiles WHERE LOWER(user_id) = ? OR LOWER(username) = ?",
        (clean_uid, clean_uname.lower()),
    ).fetchone()
    if row:
        return dict(row)

    conn.execute(
        "INSERT OR IGNORE INTO xp_profiles (user_id, username, total_xp, level, rank_title, eligible_messages) "
        "VALUES (?, ?, 0, 1, 'Recruit', 0)",
        (clean_uid, clean_uname),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM xp_profiles WHERE user_id = ?", (clean_uid,)).fetchone()
    return dict(row) if row else {
        "user_id": clean_uid,
        "username": clean_uname,
        "total_xp": 0,
        "level": 1,
        "rank_title": "Recruit",
        "eligible_messages": 0,
        "last_xp_at": None,
        "last_message_hash": None,
    }


def process_message_xp(msg: IncomingMessage, now_ts: float | None = None) -> dict[str, object] | None:
    """Award XP for an eligible Main GC message.
    Returns metadata dict (including leveled_up=True/False) if XP was awarded, or None if ineligible.
    """
    if not (config.main_group_id and msg.group_id == config.main_group_id):
        return None
    if msg.is_self:
        return None
    stripped = (msg.text or "").strip()
    if len(stripped) < 2 or stripped.startswith("/"):
        return None

    clean_uid = msg.user_id.strip().lstrip("@").lower()
    clean_uname = (msg.username or clean_uid).strip().lstrip("@")
    if not clean_uid or clean_uid == "unknown":
        return None

    try:
        cooldown_sec = max(0, int(mvp.get_config_value("xp_cooldown_seconds", "45") or "45"))
    except ValueError:
        cooldown_sec = 45

    try:
        xp_gain = max(1, int(mvp.get_config_value("xp_per_message", "15") or "15"))
    except ValueError:
        xp_gain = 15

    ts = now_ts if now_ts is not None else time.time()
    last_ts = _last_xp_ts.get(clean_uid, 0.0)
    if cooldown_sec > 0 and (ts - last_ts < cooldown_sec):
        return None

    prof = ensure_profile(clean_uid, clean_uname)
    msg_hash = _normalize_text_hash(stripped)
    if prof.get("last_message_hash") == msg_hash:
        return None

    old_xp = int(prof.get("total_xp") or 0)
    old_level = int(prof.get("level") or 1)
    old_rank = str(prof.get("rank_title") or "Recruit")

    new_xp = old_xp + xp_gain
    new_level = level_for_xp(new_xp)
    new_rank = rank_title_for_level(new_level)
    new_msgs = int(prof.get("eligible_messages") or 0) + 1
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = get_conn()
    conn.execute(
        "UPDATE xp_profiles SET username=?, total_xp=?, level=?, rank_title=?, "
        "eligible_messages=?, last_xp_at=?, last_message_hash=?, updated_at=datetime('now') "
        "WHERE user_id=?",
        (clean_uname, new_xp, new_level, new_rank, new_msgs, now_iso, msg_hash, prof["user_id"]),
    )
    conn.execute(
        "INSERT INTO xp_events (user_id, username, delta_xp, reason, actor_id, old_level, new_level, created_at) "
        "VALUES (?, ?, ?, 'message', 'system', ?, ?, ?)",
        (prof["user_id"], clean_uname, xp_gain, old_level, new_level, now_iso),
    )
    conn.commit()
    _last_xp_ts[clean_uid] = ts

    return {
        "user_id": prof["user_id"],
        "username": clean_uname,
        "delta_xp": xp_gain,
        "total_xp": new_xp,
        "old_level": old_level,
        "new_level": new_level,
        "old_rank": old_rank,
        "new_rank": new_rank,
        "leveled_up": new_level > old_level,
        "rank_promoted": new_rank != old_rank and new_level > old_level,
    }


def adjust_xp(
    target: str,
    delta: int,
    actor_id: str,
    reason: str = "admin_adjustment",
) -> dict[str, object]:
    clean_target = target.strip().lstrip("@")
    if not clean_target:
        raise ValueError("Target username cannot be empty.")

    prof = ensure_profile(clean_target.lower(), clean_target)
    old_xp = int(prof.get("total_xp") or 0)
    old_level = int(prof.get("level") or 1)
    new_xp = max(0, old_xp + int(delta))
    new_level = level_for_xp(new_xp)
    new_rank = rank_title_for_level(new_level)
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = get_conn()
    conn.execute(
        "UPDATE xp_profiles SET total_xp=?, level=?, rank_title=?, updated_at=datetime('now') WHERE user_id=?",
        (new_xp, new_level, new_rank, prof["user_id"]),
    )
    conn.execute(
        "INSERT INTO xp_events (user_id, username, delta_xp, reason, actor_id, old_level, new_level, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (prof["user_id"], prof["username"], int(delta), reason, actor_id, old_level, new_level, now_iso),
    )
    conn.commit()
    mvp.audit(actor_id, "xp_adjusted", str(prof["user_id"]), f"delta={delta}; total={new_xp}; level={new_level}")

    return get_profile(str(prof["username"]))


def get_leaderboard(limit: int = 10) -> list[dict[str, object]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT user_id, username, total_xp, level, rank_title, eligible_messages "
        "FROM xp_profiles WHERE total_xp > 0 "
        "ORDER BY total_xp DESC, eligible_messages DESC, LOWER(username) ASC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_profile(target: str) -> dict[str, object]:
    clean = target.strip().lstrip("@")
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM xp_profiles WHERE LOWER(user_id) = LOWER(?) OR LOWER(username) = LOWER(?)",
        (clean, clean),
    ).fetchone()
    if not row:
        user_row = conn.execute(
            "SELECT user_id, username FROM users WHERE LOWER(user_id) = LOWER(?) OR LOWER(username) = LOWER(?)",
            (clean, clean),
        ).fetchone()
        uname = str(user_row["username"]) if user_row else clean
        uid = str(user_row["user_id"]).lower() if user_row else clean.lower()
        prof = ensure_profile(uid, uname)
    else:
        prof = dict(row)

    total_xp = int(prof.get("total_xp") or 0)
    level = int(prof.get("level") or 1)
    rank_title = str(prof.get("rank_title") or "Recruit")
    uname = str(prof.get("username") or clean)
    uid = str(prof.get("user_id") or clean.lower())

    # Calculate server rank position (1-based)
    higher = conn.execute(
        "SELECT COUNT(*) AS c FROM xp_profiles WHERE total_xp > ?",
        (total_xp,),
    ).fetchone()
    rank_pos = int(higher["c"]) + 1 if total_xp > 0 else 0

    warns = moderation.get_warnings(uname)
    role = mvp.get_role(uid)
    if role == "user" and mvp.get_role(uname) != "user":
        role = mvp.get_role(uname)

    return {
        "user_id": uid,
        "username": uname,
        "role": role,
        "total_xp": total_xp,
        "level": level,
        "next_level_xp": next_level_xp(level),
        "rank_title": rank_title,
        "rank_position": rank_pos,
        "eligible_messages": int(prof.get("eligible_messages") or 0),
        "warnings_count": len(warns),
    }


def xp_summary_for_period(now: datetime | None = None, period: str = "today") -> dict[str, object]:
    tz_name = mvp.get_config_value("timezone", config.bot_timezone) or config.bot_timezone
    try:
        local_zone = ZoneInfo(tz_name)
    except Exception:
        local_zone = ZoneInfo(config.bot_timezone)

    local_now = (now or datetime.now(timezone.utc)).astimezone(local_zone)
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period.strip().lower() == "yesterday":
        day_start = day_start - timedelta(days=1)
    day_end = day_start + timedelta(days=1)

    total_xp_awarded = 0
    level_ups: list[tuple[str, int, str]] = []
    earners: dict[str, int] = {}

    for row in get_conn().execute(
        "SELECT username, delta_xp, old_level, new_level, created_at FROM xp_events"
    ):
        try:
            raw_ts = str(row["created_at"]).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(raw_ts)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            occurred = parsed.astimezone(local_zone)
        except ValueError:
            continue
        if day_start <= occurred < day_end:
            delta = int(row["delta_xp"] or 0)
            uname = str(row["username"] or "Unknown")
            if delta > 0:
                total_xp_awarded += delta
                earners[uname] = earners.get(uname, 0) + delta
            old_lvl = int(row["old_level"] or 1)
            new_lvl = int(row["new_level"] or 1)
            if new_lvl > old_lvl:
                level_ups.append((uname, new_lvl, rank_title_for_level(new_lvl)))

    top_earners = sorted(earners.items(), key=lambda item: (-item[1], item[0].lower()))[:5]
    return {
        "total_xp_awarded": total_xp_awarded,
        "level_ups": level_ups,
        "top_earners": top_earners,
    }
