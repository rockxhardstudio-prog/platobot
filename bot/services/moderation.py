import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from bot.config import config
from bot.database.db import get_conn
from bot.models.message import IncomingMessage
from bot.services import community, mvp

NOTICE_THRESHOLD = 5
AUTO_WARN_COOLDOWN_SECONDS = 8.0

# Per-user sliding window state for Main GC spam detection
# user_key -> list of (timestamp, normalized_text)
_recent_user_messages: dict[str, list[tuple[float, str]]] = {}
_last_auto_warn_at: dict[str, float] = {}

_URL_RE = re.compile(
    r"(?:https?://[^\s<>\"']+|www\.[^\s<>\"']+|"
    r"\b(?:discord\.gg|discord\.com/invite|t\.me|bit\.ly|tinyurl\.com|youtu\.be|"
    r"youtube\.com|instagram\.com|platoapp\.com|plato\.app)/[^\s<>\"']*|"
    r"\b[a-zA-Z0-9-]{2,63}\.(?:com|gg|org|net|io|me|co|in|app|xyz|link|ly|tv)/[^\s<>\"']+)",
    re.IGNORECASE,
)

# Non-Latin script character ranges (Devanagari, Bengali, Gurmukhi, Gujarati, Tamil, Telugu,
# Kannada, Malayalam, Sinhala, Thai, Arabic, Hebrew, Cyrillic, Hangul, CJK)
_NON_LATIN_SCRIPT_RE = re.compile(
    r"[\u0400-\u052F\u0590-\u06FF\u0750-\u077F\u0900-\u0D7F\u0E00-\u0E7F"
    r"\u1100-\u11FF\u3040-\u30FF\u3130-\u318F\u4E00-\u9FFF\uAC00-\uD7AF]"
)

# Unmistakable Hinglish / Romanized Hindi & non-English chat words (single token is already strong,
# and 2+ tokens in any message is definitive)
_STRONG_HINGLISH_WORDS = {
    "kya", "kaise", "kaisa", "kaisi", "kyu", "kyun", "nahi", "nhi", "haan",
    "accha", "acha", "bhai", "bhaiya", "yaar", "tum", "tumhe", "tumhara",
    "mera", "meri", "mere", "tera", "teri", "tere", "uska", "uski", "apna",
    "apni", "apne", "hum", "hamara", "mujhe", "mujhko", "tujhe", "tujhko",
    "karo", "karna", "krna", "karke", "krke", "karega", "karegi", "raha",
    "rahi", "rahe", "rha", "rhi", "rhe", "gaya", "gayi", "gaye", "gya",
    "gyi", "bohot", "bahut", "bht", "abhi", "kuch", "kuchh", "sabhi",
    "baat", "bolo", "batao", "btao", "dekho", "suno", "chalo", "jao",
    "aao", "khana", "paisa", "mazak", "pagal", "bakwas", "samajh", "smjh",
    "maloom", "lagta", "waise", "lekin", "phir", "fir", "subah", "shaam",
    "raat", "dost", "zindagi", "pyaar", "dimag", "kaha", "kahan", "kidhar",
    "idhar", "udhar", "yaha", "yahan", "waha", "wahan", "kaun", "kon",
    "kitna", "kitne", "kitni", "chahiye", "chaiye", "milega", "milegi",
    "lagao", "banao", "nikal", "niklo", "chup", "rukja", "ruko", "arre",
    "arrey", "abe", "abey", "oye", "behen", "bhen", "sala", "saala",
    "matlab", "mtlb", "kyuki", "kyunki", "isliye", "islie", "bilkul",
    "shayad", "zaroor", "jaldi", "dhire", "aaram", "bekar", "mast",
    "jugaad", "faltu", "timepass", "sahi", "galat", "pक्का", "pakka",
    # Common non-English Romanized words
    "hola", "gracias", "porfavor", "buenos", "buenas", "noches", "como",
    "estas", "wallah", "wallahi", "habibi", "inshallah", "mashallah",
}

# Context Hinglish particles (only count when combined with another Hinglish word)
_CONTEXT_HINGLISH_PARTICLES = {
    "hai", "hain", "ho", "tha", "thi", "the", "na", "mat", "bhi", "toh",
    "aur", "par", "pe", "se", "ko", "ka", "ki", "ke", "ne", "ye", "yeh",
    "wo", "woh", "tu", "aaj", "kal", "ab", "jab", "tab", "kab", "koi",
    "sab", "log", "dil", "pata", "kr", "kar", "de", "le", "ja", "aa",
}


def reset_runtime_state() -> None:
    _recent_user_messages.clear()
    _last_auto_warn_at.clear()


def _sync_notice_list(user_id: str, username: str, actor_id: str = "system") -> int:
    conn = get_conn()
    clean_uid = user_id.strip().lower()
    rows = conn.execute(
        "SELECT reason, category FROM warnings WHERE LOWER(user_id) = ? OR LOWER(username) = ? ORDER BY id ASC",
        (clean_uid, username.strip().lower()),
    ).fetchall()
    count = len(rows)

    if count >= NOTICE_THRESHOLD:
        recent_reasons = [f"[{r['category']}] {r['reason']}" for r in rows[-3:]]
        summary = "; ".join(recent_reasons)[:240]
        conn.execute(
            "INSERT INTO moderation_notices (user_id, username, warning_count, reasons_summary, first_flagged_at, updated_at, resolved) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'), 0) "
            "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, warning_count=excluded.warning_count, "
            "reasons_summary=excluded.reasons_summary, updated_at=datetime('now'), resolved=0, resolved_by=NULL, resolved_at=NULL",
            (clean_uid, username, count, summary),
        )
    else:
        conn.execute(
            "UPDATE moderation_notices SET warning_count=?, resolved=1, resolved_by=?, resolved_at=datetime('now'), updated_at=datetime('now') "
            "WHERE LOWER(user_id)=? OR LOWER(username)=?",
            (count, actor_id, clean_uid, username.strip().lower()),
        )
    conn.commit()
    return count


def add_warning(
    user_id: str,
    username: str,
    reason: str,
    admin_id: str,
    category: str = "manual",
    delivered: bool | None = None,
) -> int:
    conn = get_conn()
    clean_uid = user_id.strip().lstrip("@").lower()
    clean_uname = username.strip().lstrip("@")
    clean_cat = category.strip().lower() or "manual"
    is_deliv = (clean_cat != "manual") if delivered is None else bool(delivered)
    conn.execute(
        "INSERT INTO warnings (user_id, username, category, reason, issued_by, delivered) VALUES (?, ?, ?, ?, ?, ?)",
        (clean_uid, clean_uname, clean_cat, reason, admin_id, 1 if is_deliv else 0),
    )
    conn.commit()
    return _sync_notice_list(clean_uid, clean_uname, admin_id)


def pop_pending_warnings(user_id: str, username: str) -> str | None:
    conn = get_conn()
    clean_uid = (user_id or "").strip().lstrip("@").lower()
    clean_uname = (username or clean_uid).strip().lstrip("@")
    if not clean_uid or clean_uid == "unknown":
        return None

    pending = conn.execute(
        "SELECT id, reason FROM warnings WHERE (LOWER(user_id) = ? OR LOWER(username) = ?) AND delivered = 0 ORDER BY id ASC",
        (clean_uid, clean_uname.lower()),
    ).fetchall()
    if not pending:
        return None

    ids = [int(r["id"]) for r in pending]
    placeholders = ",".join("?" for _ in ids)
    conn.execute(f"UPDATE warnings SET delivered = 1 WHERE id IN ({placeholders})", ids)
    conn.commit()

    from bot.utils.scifi import render_progress_bar
    total_warns = len(get_warnings(clean_uname))
    reasons_str = "; ".join(str(r["reason"]) for r in pending)
    bar = render_progress_bar(total_warns, NOTICE_THRESHOLD, width=5)
    msg = (
        f"🗲 NOTICE // @{clean_uname}\n"
        f"➥ Warning ({total_warns}/{NOTICE_THRESHOLD}): {reasons_str}\n"
        f"➥ Status: {bar}"
    )
    if total_warns >= NOTICE_THRESHOLD:
        msg += "\n➥ Flagged to Staff Notice List for review."
    return msg


def remove_single_warning(
    username: str,
    warning_id: int | None = None,
    actor_id: str = "system",
) -> tuple[bool, int]:
    conn = get_conn()
    clean_target = username.strip().lstrip("@")
    if warning_id is not None:
        row = conn.execute(
            "SELECT id, user_id, username FROM warnings WHERE id = ? AND (LOWER(username) = LOWER(?) OR LOWER(user_id) = LOWER(?))",
            (warning_id, clean_target, clean_target),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id, user_id, username FROM warnings WHERE LOWER(username) = LOWER(?) OR LOWER(user_id) = LOWER(?) ORDER BY id DESC LIMIT 1",
            (clean_target, clean_target),
        ).fetchone()

    if not row:
        rem = conn.execute(
            "SELECT COUNT(*) AS c FROM warnings WHERE LOWER(username) = LOWER(?) OR LOWER(user_id) = LOWER(?)",
            (clean_target, clean_target),
        ).fetchone()["c"]
        return False, int(rem)

    conn.execute("DELETE FROM warnings WHERE id = ?", (row["id"],))
    conn.commit()
    remaining = _sync_notice_list(str(row["user_id"]), str(row["username"]), actor_id)
    mvp.audit(actor_id, "warning_removed", clean_target, f"id={row['id']}; remaining={remaining}")
    return True, remaining


def get_warnings(username: str) -> list[sqlite3.Row]:
    clean = username.strip().lstrip("@")
    return get_conn().execute(
        "SELECT id, category, reason, issued_by, created_at FROM warnings "
        "WHERE username = ? COLLATE NOCASE OR user_id = ? COLLATE NOCASE ORDER BY id ASC",
        (clean, clean),
    ).fetchall()


def clear_warnings(username: str, actor_id: str = "system") -> int:
    conn = get_conn()
    clean = username.strip().lstrip("@")
    cursor = conn.execute(
        "DELETE FROM warnings WHERE username = ? COLLATE NOCASE OR user_id = ? COLLATE NOCASE",
        (clean, clean),
    )
    conn.commit()
    _sync_notice_list(clean.lower(), clean, actor_id)
    return cursor.rowcount


def get_notice_list(include_resolved: bool = False) -> list[dict[str, object]]:
    conn = get_conn()
    if include_resolved:
        rows = conn.execute(
            "SELECT * FROM moderation_notices ORDER BY resolved ASC, warning_count DESC, updated_at DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM moderation_notices WHERE resolved = 0 ORDER BY warning_count DESC, updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def normalize_domain(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.netloc or parsed.path.split("/")[0]).strip().lower()
    if ":" in host:
        host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host.strip(".")


def add_allowed_domain(domain: str, actor_id: str) -> str:
    clean = normalize_domain(domain)
    if not clean or "." not in clean:
        raise ValueError("Please provide a valid domain (e.g., youtube.com).")
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO allowed_domains (domain, added_by, created_at) VALUES (?, ?, datetime('now'))",
        (clean, actor_id),
    )
    conn.commit()
    mvp.audit(actor_id, "domain_allowed", clean, "")
    return clean


def remove_allowed_domain(domain: str, actor_id: str) -> bool:
    clean = normalize_domain(domain)
    if not clean:
        return False
    conn = get_conn()
    cur = conn.execute("DELETE FROM allowed_domains WHERE domain = ?", (clean,))
    conn.commit()
    if cur.rowcount > 0:
        mvp.audit(actor_id, "domain_removed", clean, "")
        return True
    return False


def list_allowed_domains() -> list[str]:
    domains = {"platoapp.com", "plato.app"}
    conn = get_conn()
    for row in conn.execute("SELECT domain FROM allowed_domains ORDER BY domain ASC"):
        if row["domain"]:
            domains.add(str(row["domain"]).lower())
    # Automatically include domains of staff-configured social/invite links
    socials = community.get_socials()
    invite = mvp.get_invite()
    for url in (socials.get("insta"), socials.get("dc"), invite):
        if url:
            dom = normalize_domain(url)
            if dom:
                domains.add(dom)
    return sorted(domains)


def _domain_is_allowed(domain: str, allowed: list[str]) -> bool:
    d = domain.lower()
    for a in allowed:
        if d == a or d.endswith("." + a):
            return True
    return False


def extract_unapproved_domains(text: str) -> list[str]:
    if not text:
        return []
    matches = _URL_RE.findall(text)
    if not matches:
        return []
    allowed = list_allowed_domains()
    unapproved: list[str] = []
    for m in matches:
        dom = normalize_domain(m)
        if dom and not _domain_is_allowed(dom, allowed) and dom not in unapproved:
            unapproved.append(dom)
    return unapproved


def detect_non_english(text: str) -> str | None:
    if not text:
        return None
    stripped = text.strip()
    if not stripped or stripped.startswith("/"):
        return None

    # Check non-Latin scripts first (Devanagari, Arabic, Cyrillic, CJK, etc.)
    if _NON_LATIN_SCRIPT_RE.search(stripped):
        return "Non-English script detected (English-only chat)"

    # Strip @mentions and URLs before tokenizing
    cleaned = re.sub(r"@[A-Za-z0-9_.-]+", " ", stripped)
    cleaned = _URL_RE.sub(" ", cleaned)
    tokens = re.findall(r"[a-zA-Z]{2,}", cleaned.lower())
    if not tokens:
        return None

    strong_hits = [t for t in tokens if t in _STRONG_HINGLISH_WORDS]
    context_hits = [t for t in tokens if t in _CONTEXT_HINGLISH_PARTICLES]

    if len(strong_hits) >= 2:
        return "Non-English / Hinglish detected (English-only chat)"
    if len(strong_hits) == 1 and (len(context_hits) >= 1 or len(tokens) <= 4):
        return "Non-English / Hinglish detected (English-only chat)"
    if len(context_hits) >= 3 and len(context_hits) / max(len(tokens), 1) >= 0.5:
        return "Non-English / Hinglish detected (English-only chat)"

    return None


def _check_spam_violation(user_id: str, text: str, now_ts: float) -> str | None:
    stripped = text.strip()
    if not stripped or stripped.startswith("/"):
        return None

    # 1. Character flood (e.g. "aaaaaaaaaaaaaaa" >= 18 consecutive identical characters)
    if re.search(r"(.)\1{17,}", stripped):
        return "Character flood / spam"

    try:
        spam_threshold = max(3, int(mvp.get_config_value("spam_threshold", "4") or "4"))
    except ValueError:
        spam_threshold = 4

    key = user_id.strip().lower()
    history = _recent_user_messages.setdefault(key, [])
    norm_text = " ".join(stripped.lower().split())
    history.append((now_ts, norm_text))
    # Prune entries older than 30s
    history[:] = [(ts, t) for ts, t in history if now_ts - ts <= 30.0]

    # 2. Duplicate message spam: 3+ identical messages within 30 seconds
    dup_count = sum(1 for ts, t in history if t == norm_text and (now_ts - ts <= 30.0))
    if dup_count >= 3:
        return "Repeated duplicate messages"

    # 3. Rapid burst flood: >= spam_threshold messages within 10 seconds
    burst_count = sum(1 for ts, _ in history if now_ts - ts <= 10.0)
    if burst_count >= spam_threshold:
        return "Rapid message flooding"

    return None


def check_message(msg: IncomingMessage, now_ts: float | None = None) -> str | None:
    """Run Sentinel moderation checks on a Main GC message.
    Returns a warning reply string if a violation occurred, or None if clean/exempt.
    """
    if not (config.main_group_id and msg.group_id == config.main_group_id):
        return None
    if msg.is_self:
        return None
    # Staff (mod, admin, owner) are exempt from automated Sentinel enforcement
    if mvp.is_staff(msg.user_id) or mvp.is_staff(msg.username):
        return None

    ts = now_ts if now_ts is not None else time.time()
    user_key = msg.user_id.strip().lower()

    category: str | None = None
    reason: str | None = None

    # 1. Spam check
    spam_reason = _check_spam_violation(user_key, msg.text, ts)
    if spam_reason:
        category = "spam"
        reason = spam_reason

    # 2. Prohibited link check
    if not reason:
        bad_domains = extract_unapproved_domains(msg.text)
        if bad_domains:
            category = "link"
            reason = f"Unapproved link ({bad_domains[0]})"

    # 3. Strict English-only check
    if not reason:
        eng_only = (mvp.get_config_value("english_only", "true") or "true").strip().lower()
        if eng_only in {"true", "1", "on", "yes"}:
            lang_reason = detect_non_english(msg.text)
            if lang_reason:
                category = "language"
                reason = lang_reason

    if not category or not reason:
        return None

    # Cooldown so a single burst doesn't issue multiple warnings in the same second
    last_warn = _last_auto_warn_at.get(user_key, 0.0)
    if ts - last_warn < AUTO_WARN_COOLDOWN_SECONDS:
        return None
    _last_auto_warn_at[user_key] = ts

    count = add_warning(user_key, msg.username, reason, "sentinel", category=category)
    mention = f"@{msg.username}" if msg.username and msg.username != "unknown" else "Member"
    from bot.utils.scifi import render_progress_bar
    bar = render_progress_bar(count, NOTICE_THRESHOLD, width=5)
    reply = (
        f"🗲 NOTICE // {mention}\n"
        f"➥ Reason: {reason}\n"
        f"➥ Status: {bar} Warning ({count}/{NOTICE_THRESHOLD})"
    )
    if count >= NOTICE_THRESHOLD:
        reply += "\n➥ 5 warnings reached! Flagged to Staff Notice List."
    return reply


def warnings_summary_for_period(now: datetime | None = None, period: str = "today") -> dict[str, object]:
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

    by_category: dict[str, int] = {}
    total = 0
    for row in get_conn().execute("SELECT category, created_at FROM warnings"):
        try:
            raw_ts = str(row["created_at"]).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(raw_ts)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            occurred = parsed.astimezone(local_zone)
        except ValueError:
            continue
        if day_start <= occurred < day_end:
            cat = str(row["category"] or "manual").lower()
            by_category[cat] = by_category.get(cat, 0) + 1
            total += 1

    notices = get_notice_list(include_resolved=False)
    return {
        "total": total,
        "by_category": by_category,
        "notices": notices,
    }
