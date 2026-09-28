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
    role TEXT NOT NULL DEFAULT 'user'
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
    announcement_text TEXT,
    updated_by TEXT NOT NULL,
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
    reason TEXT NOT NULL,
    issued_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_warnings_user ON warnings(user_id);
"""


def get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
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
