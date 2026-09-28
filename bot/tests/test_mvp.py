import importlib
import os
import sys
import tempfile
from datetime import datetime, timezone

import pytest


@pytest.fixture
def bot(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("BOT_DB_PATH", db_path)
    monkeypatch.setenv("MAIN_GROUP_ID", "main")
    monkeypatch.setenv("STORAGE_GROUP_ID", "storage")
    monkeypatch.setenv("ADMIN_IDS", "admin")
    monkeypatch.setenv("MAX_SPAM_REPETITIONS", "3")
    monkeypatch.setenv("SPAM_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("BOT_TIMEZONE", "Asia/Kolkata")
    for name in list(sys.modules):
        if name.startswith("bot."):
            del sys.modules[name]
    db = importlib.import_module("bot.database.db")
    db.init_db()
    router = importlib.import_module("bot.commands.router")
    message = importlib.import_module("bot.models.message").IncomingMessage
    yield router, message, db
    db.get_conn().close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(db_path + suffix)
        except FileNotFoundError:
            pass


def send(router, message, ident, group, user, text, timestamp=None, self_message=False):
    return router.handle_message(message(ident, group, user, user.title(), text, self_message, timestamp))


def test_spam_accepts_spacing_variants_and_queues_messages(bot):
    router, message, _ = bot
    assert send(router, message, "s1", "storage", "admin", "/spamset 1 hello") == "Saved spam message 1."
    assert send(router, message, "m1", "main", "user", "/spam : 1 + 2") == "Queued message 1 2 times."
    pending = router.plato_client.pending("main", 10)
    assert [item["text"] for item in pending] == ["hello", "hello", "Queued message 1 2 times."]
    assert send(router, message, "m2", "main", "user2", "/spam:1+1") == "Queued message 1 1 time."
    assert send(router, message, "m3", "main", "user3", "/spam 1 + 1") == "Queued message 1 1 time."


def test_spam_rejects_bad_count_and_wrong_group(bot):
    router, message, _ = bot
    send(router, message, "s1", "storage", "admin", "/spamset 1 hello")
    assert "1 to 3" in send(router, message, "m1", "main", "user", "/spam:1+4")
    assert "Usage" in send(router, message, "m2", "main", "user", "/spam:bad")
    assert "Main Group" in send(router, message, "s2", "storage", "admin", "/spam:1+1")


def test_spam_requires_existing_entry_and_enforces_cooldown(bot):
    router, message, _ = bot
    assert "No stored" in send(router, message, "m0", "main", "other-user", "/spam:99+1")
    send(router, message, "s1", "storage", "admin", "/spamset 1 hello")
    router.config.spam_cooldown_seconds = 60
    assert send(router, message, "m1", "main", "user", "/spam:1+1").startswith("Queued")
    assert "Please wait" in send(router, message, "m2", "main", "user", "/spam:1+1")


def test_storage_updates_require_admin_and_invite_is_returned(bot):
    router, message, _ = bot
    assert "Only a bot admin" in send(router, message, "s1", "storage", "person", "/inviteset https://plato.example/invite")
    assert "valid http" in send(router, message, "s2", "storage", "admin", "/inviteset not-a-link")
    assert send(router, message, "s3", "storage", "admin", "/inviteset https://plato.example/invite") == "Invite link saved."
    assert send(router, message, "m1", "main", "person", "/invite") == "https://plato.example/invite"


def test_add_creates_and_updates_mapping(bot):
    router, message, db = bot
    assert send(router, message, "s1", "storage", "admin", "/add Yuvraj:1") == "Saved ID 1 for Yuvraj."
    assert send(router, message, "s2", "storage", "admin", "/add Alex:1") == "Saved ID 1 for Alex."
    row = db.get_conn().execute("SELECT username FROM user_id_map WHERE id=1").fetchone()
    assert row["username"] == "Alex"
    assert "Storage Group" in send(router, message, "m1", "main", "admin", "/add Other:2")


def test_summary_counts_main_messages_once_and_ranks_users(bot):
    router, message, _ = bot
    today = datetime.now(timezone.utc).isoformat()
    send(router, message, "m1", "main", "alice", "hello", today)
    send(router, message, "m2", "main", "alice", "again", today)
    send(router, message, "m3", "main", "bob", "hi", today)
    send(router, message, "other", "storage", "admin", "not counted", today)
    send(router, message, "m1", "main", "alice", "duplicate", today)
    response = send(router, message, "summary", "main", "bob", "/summary", today)
    assert "Active members: 2" in response
    assert "Total messages: 4" in response  # includes the /summary command itself
    assert "1. Alice — 2 messages" in response


def test_summary_honors_kolkata_day_boundary(bot):
    _, _, db = bot
    from bot.services.mvp import activity_summary

    conn = db.get_conn()
    conn.executemany(
        "INSERT INTO messages (message_id, group_id, user_id, username, text, created_at) VALUES (?, 'main', ?, ?, 'x', ?)",
        [
            ("before", "a", "Alice", "2026-09-04T18:29:59+00:00"),
            ("start", "a", "Alice", "2026-09-04T18:30:00+00:00"),
            ("later", "b", "Bob", "2026-09-05T10:00:00+00:00"),
        ],
    )
    conn.commit()
    total, active, ranked, _ = activity_summary("main", datetime(2026, 9, 5, 12, tzinfo=timezone.utc))
    assert (total, active, ranked) == (2, 2, [("Alice", 1), ("Bob", 1)])


def test_self_messages_and_duplicates_are_not_recorded(bot):
    router, message, db = bot
    send(router, message, "self", "main", "bot", "I sent this", self_message=True)
    send(router, message, "d1", "main", "alice", "hello")
    send(router, message, "d1", "main", "alice", "hello again")
    assert db.get_conn().execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1


