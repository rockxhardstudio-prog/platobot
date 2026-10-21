import sqlite3
import threading
from contextlib import contextmanager

from bot.config import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS groups (
    group_id TEXT PRIMARY KEY,
    name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS permissions (
    user_id TEXT PRIMARY KEY,
    role TEXT NOT NULL DEFAULT 'user',
    updated_by TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS command_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    group_id TEXT,
    command TEXT,
    args TEXT,
    result TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT UNIQUE,
    group_id TEXT NOT NULL,
    user_id TEXT,
    username TEXT,
    text TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    delivered_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_id TEXT,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS spam_messages (
    id INTEGER PRIMARY KEY,
    message_text TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS invite_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    invite_url TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_id_map (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_group_time ON messages(group_id, created_at);

CREATE TABLE IF NOT EXISTS community_content (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    info_text TEXT,
    rules_text TEXT,
    tourney_rules_text TEXT,
    announcement_text TEXT,
    insta_url TEXT,
    dc_url TEXT,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS config_kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bridge_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    target_group_id TEXT NOT NULL DEFAULT 'main',
    target_group_title TEXT,
    summon_expires_at TEXT,
    navigation_pending INTEGER NOT NULL DEFAULT 0,
    current_group_id TEXT,
    current_group_title TEXT,
    last_heartbeat_at TEXT,
    last_error TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    game TEXT,
    event_date TEXT,
    event_time TEXT,
    registration_time TEXT,
    format TEXT,
    max_slots INTEGER,
    prize_info TEXT,
    description_text TEXT,
    rules_text TEXT,
    host_mode TEXT,
    host TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    is_active INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tournaments_active ON tournaments(is_active);

CREATE TABLE IF NOT EXISTS registrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id),
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    game_tag TEXT,
    status TEXT NOT NULL DEFAULT 'registered',
    registered_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(tournament_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_registrations_status ON registrations(tournament_id, status);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    event_date TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'upcoming',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'manual',
    reason TEXT NOT NULL,
    issued_by TEXT NOT NULL,
    delivered INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_warnings_user ON warnings(user_id);

CREATE TABLE IF NOT EXISTS tourney_winners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tourney_name TEXT,
    tab_label TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    added_by TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tourney_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    game TEXT,
    rules_text TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS tourney_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    match_number INTEGER NOT NULL,
    player1_id TEXT NOT NULL,
    player1_name TEXT NOT NULL,
    player2_id TEXT,
    player2_name TEXT,
    winner_id TEXT,
    winner_name TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    win_reason TEXT,
    p1_last_active TEXT,
    p2_last_active TEXT,
    afk_reported_against TEXT,
    afk_reported_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS tourney_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER,
    round_number INTEGER,
    match_number INTEGER,
    reporter_id TEXT NOT NULL,
    reporter_name TEXT NOT NULL,
    opponent_name TEXT,
    issue_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS giveaways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    game TEXT NOT NULL DEFAULT 'Bingo',
    seats_per_tab INTEGER NOT NULL DEFAULT 15,
    target_winners INTEGER NOT NULL DEFAULT 10,
    online_count INTEGER NOT NULL DEFAULT 30,
    current_batch INTEGER NOT NULL DEFAULT 0,
    tabs_in_current_batch INTEGER NOT NULL DEFAULT 0,
    winners_in_current_batch INTEGER NOT NULL DEFAULT 0,
    info_text TEXT,
    rules_text TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS moderation_notices (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    warning_count INTEGER NOT NULL DEFAULT 5,
    reasons_summary TEXT NOT NULL DEFAULT '',
    first_flagged_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved INTEGER NOT NULL DEFAULT 0,
    resolved_by TEXT,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS allowed_domains (
    domain TEXT PRIMARY KEY,
    added_by TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS xp_profiles (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    total_xp INTEGER NOT NULL DEFAULT 0,
    level INTEGER NOT NULL DEFAULT 1,
    rank_title TEXT NOT NULL DEFAULT 'Recruit',
    eligible_messages INTEGER NOT NULL DEFAULT 0,
    last_xp_at TEXT,
    last_message_hash TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS xp_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    delta_xp INTEGER NOT NULL,
    reason TEXT NOT NULL,
    actor_id TEXT NOT NULL DEFAULT 'system',
    old_level INTEGER NOT NULL DEFAULT 1,
    new_level INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_xp_events_user ON xp_events(user_id, created_at);
"""


def get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(config.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    else:
        try:
            _local.conn.execute("SELECT 1")
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            conn = sqlite3.connect(config.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.row_factory = sqlite3.Row
            _local.conn = conn
    return _local.conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)

    conn.execute(
        "INSERT OR IGNORE INTO community_content (id, updated_by) VALUES (1, 'system')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO bridge_state (id, target_group_id, target_group_title) VALUES (1, ?, ?)",
        (config.main_group_id or "main", config.main_group_title or "-» NOVΛ ⟡ BLΛZΞ «-"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO allowed_domains (domain, added_by) VALUES ('platoapp.com', 'system')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO allowed_domains (domain, added_by) VALUES ('plato.app', 'system')"
    )

    bs_cols = {row["name"] for row in conn.execute("PRAGMA table_info(bridge_state)")}
    if "navigation_pending" not in bs_cols:
        conn.execute("ALTER TABLE bridge_state ADD COLUMN navigation_pending INTEGER NOT NULL DEFAULT 0")

    warn_cols = {row["name"] for row in conn.execute("PRAGMA table_info(warnings)")}
    if "category" not in warn_cols:
        conn.execute("ALTER TABLE warnings ADD COLUMN category TEXT NOT NULL DEFAULT 'manual'")
    if "delivered" not in warn_cols:
        conn.execute("ALTER TABLE warnings ADD COLUMN delivered INTEGER NOT NULL DEFAULT 1")

    cc_cols = {row["name"] for row in conn.execute("PRAGMA table_info(community_content)")}
    if "insta_url" not in cc_cols:
        conn.execute("ALTER TABLE community_content ADD COLUMN insta_url TEXT")
    if "dc_url" not in cc_cols:
        conn.execute("ALTER TABLE community_content ADD COLUMN dc_url TEXT")
    if "tourney_rules_text" not in cc_cols:
        conn.execute("ALTER TABLE community_content ADD COLUMN tourney_rules_text TEXT")

    perm_cols = {row["name"] for row in conn.execute("PRAGMA table_info(permissions)")}
    if "updated_by" not in perm_cols:
        conn.execute("ALTER TABLE permissions ADD COLUMN updated_by TEXT")
    if "updated_at" not in perm_cols:
        conn.execute("ALTER TABLE permissions ADD COLUMN updated_at TEXT")

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(tournaments)")}
    if "description_text" not in columns:
        conn.execute("ALTER TABLE tournaments ADD COLUMN description_text TEXT")
    if "registration_time" not in columns:
        conn.execute("ALTER TABLE tournaments ADD COLUMN registration_time TEXT")
    if "host_mode" not in columns:
        conn.execute("ALTER TABLE tournaments ADD COLUMN host_mode TEXT")
    if "host" not in columns:
        conn.execute("ALTER TABLE tournaments ADD COLUMN host TEXT")

    outbox_cols = {row["name"] for row in conn.execute("PRAGMA table_info(outbox)")}
    if "attempts" not in outbox_cols:
        conn.execute("ALTER TABLE outbox ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
    if "last_attempt_at" not in outbox_cols:
        conn.execute("ALTER TABLE outbox ADD COLUMN last_attempt_at TEXT")
    if "error" not in outbox_cols:
        conn.execute("ALTER TABLE outbox ADD COLUMN error TEXT")

    conn.executescript("""
    DROP TABLE IF EXISTS transactions;
    DROP TABLE IF EXISTS balances;
    DROP TABLE IF EXISTS stats;
    DROP TABLE IF EXISTS daily_claims;
    """)

    cmd_cols = {row["name"] for row in conn.execute("PRAGMA table_info(command_log)")}
    if "result" not in cmd_cols:
        conn.execute("ALTER TABLE command_log ADD COLUMN result TEXT")

    if config.admin_ids != {"admin"}:
        conn.execute(
            "DELETE FROM permissions WHERE user_id IN ('testuid','testuid1','regularuser','u_hawt','u_tuhin','user_123','user_456','phone-user','floatsystem','unknown','hawtshot','tuhin')"
        )
        for owner_uid in ("TUHIN", "HawtShot", "zuriah", "AD4RSHH"):
            conn.execute(
                "INSERT OR REPLACE INTO permissions (user_id, role, updated_by, updated_at) VALUES (?, 'owner', 'system', datetime('now'))",
                (owner_uid,),
            )
        conn.execute(
            "UPDATE permissions SET role='mod' WHERE LOWER(user_id) NOT IN ('tuhin','hawtshot','zuriah','ad4rshh') AND role='user'"
        )
    conn.commit()


@contextmanager
def transaction():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
