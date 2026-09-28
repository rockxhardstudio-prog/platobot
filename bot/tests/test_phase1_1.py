"""Tests for Phase 1.1 requirements:
- 256-character limit utility
- /adminhelp gating
- interactive /tourneycreate session
- /tourneyset new fields
- /register rejects args
- /online removed
"""
import pytest
from bot.models.message import IncomingMessage
from bot.utils.text import chunk_text
from bot import handlers
import bot.handlers.admin as admin
import bot.handlers.core as core
import bot.handlers.community as community


@pytest.fixture
def admin_msg():
    return IncomingMessage(
        message_id="a1", group_id="storage", user_id="admin_user",
        username="Admin", text="/adminhelp", is_self=False, timestamp="2026-09-19T10:00:00Z"
    )

@pytest.fixture
def main_msg():
    return IncomingMessage(
        message_id="m1", group_id="main", user_id="regular_user",
        username="User", text="/adminhelp", is_self=False, timestamp="2026-09-19T10:00:00Z"
    )


# ── 256-character limit utility ───────────────────────────────────────────────

def test_chunk_text_short_passthrough():
    text = "Hello world!"
    assert chunk_text(text) == [text]

def test_chunk_text_exact_limit():
    text = "A" * 256
    assert chunk_text(text) == [text]

def test_chunk_text_splits_over_limit():
    text = "A" * 300
    chunks = chunk_text(text, limit=256)
    assert len(chunks) == 2
    assert all(len(c) <= 256 for c in chunks)

def test_chunk_text_prefers_newline_split():
    # Should split at the newline, not mid-word
    line_a = "A" * 200
    line_b = "B" * 200
    text = line_a + "\n" + line_b
    chunks = chunk_text(text, limit=256)
    assert len(chunks) == 2
    assert line_a in chunks[0]
    assert line_b in chunks[1]

def test_chunk_text_empty():
    assert chunk_text("") == [""]

def test_chunk_text_all_help_responses_fit():
    """All /help category responses must be ≤256 chars."""
    import bot.config as cfg
    original = cfg.config.main_group_id
    cfg.config.main_group_id = "main"
    try:
        msg = IncomingMessage("x","main","u","U","/help",False,"2026")
        for cat in ["", "core", "community", "tourney", "fun"]:
            res = core._handle_help(msg, cat)
            assert len(res) <= 256, f"/help {cat!r} response is {len(res)} chars (>256)"
    finally:
        cfg.config.main_group_id = original


# ── /online removed ───────────────────────────────────────────────────────────

def test_online_not_in_handlers():
    assert "online" not in handlers.HANDLERS, "/online should be removed from HANDLERS"

def test_online_not_in_help(main_msg, monkeypatch):
    monkeypatch.setattr(core.config, "main_group_id", "main")
    main_msg_copy = IncomingMessage("x","main","u","U","/help",False,"2026")
    res = core._handle_help(main_msg_copy, "")
    assert "/online" not in res


# ── /adminhelp permission gating ─────────────────────────────────────────────

def test_adminhelp_blocked_for_regular_user(main_msg):
    """Regular user in the wrong group can't see admin help."""
    res = admin._handle_adminhelp(main_msg, "")
    assert "Admin" not in res or "not allowed" in res.lower() or "permission" in res.lower() or "ADMIN HELP" not in res

def test_adminhelp_works_for_admin(admin_msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    res = admin._handle_adminhelp(admin_msg, "")
    assert "ADMIN HELP" in res
    assert len(res) <= 256

def test_adminhelp_tourney_category(admin_msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    res = admin._handle_adminhelp(admin_msg, "tourney")
    assert "/tourneycreate" in res
    assert len(res) <= 256

def test_adminhelp_mod_category(admin_msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    res = admin._handle_adminhelp(admin_msg, "mod")
    assert "/warn" in res
    assert len(res) <= 256


# ── Interactive /tourneycreate session ────────────────────────────────────────

def test_tourneycreate_starts_session(admin_msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    # Clear any existing session
    from bot.services import session
    session.end_session(admin_msg.user_id)
    res = admin._handle_tourneycreate(admin_msg, "")
    assert "title" in res.lower() or "Tournament" in res
    sess = session.get_session(admin_msg.user_id)
    assert sess is not None
    assert sess["command"] == "tourneycreate"
    assert sess["step"] == "title"
    session.end_session(admin_msg.user_id)

def test_interactive_session_full_flow(admin_msg, monkeypatch):
    """Step through the full tourneycreate conversation flow."""
    from bot.services import session
    import bot.services.tournament as tournament
    
    session.end_session(admin_msg.user_id)
    
    created = {}
    def mock_create(name, uid):
        created["name"] = name
    updated = {}
    def mock_update(field, value):
        updated[field] = value
        return True

    monkeypatch.setattr(admin.tournament, "create_tournament", mock_create)
    monkeypatch.setattr(admin.tournament, "update_active_tournament_field", mock_update)

    def make_msg(text):
        return IncomingMessage("x", admin_msg.group_id, admin_msg.user_id, admin_msg.username, text, False, "2026")

    # Start session
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    admin._handle_tourneycreate(admin_msg, "")

    steps = [
        ("2VS2 TOUR",       "Game?"),             # title → game
        ("Mixed Games",     "Date?"),             # game → date
        ("Sep 20",          "Time?"),             # date → time
        ("5 PM GMT",        "Registration time?"),# time → reg_time
        ("30 min prior",    "Description?"),      # reg_time → desc
        ("Great tournament","Rules?"),            # desc → rules
        ("No cheating",     "Slots?"),            # rules → slots
        ("10",              "Prize?"),            # slots → prize
        ("50 Pips",         "Host mode? (auto/manual)"),  # prize → host_mode
        ("auto",            None),               # host_mode → creates tournament
    ]

    for answer, expected_prompt in steps:
        sess = session.get_session(admin_msg.user_id)
        assert sess is not None, "Session lost prematurely"
        response = admin.handle_interactive_session(make_msg(answer), sess)
        if expected_prompt:
            assert expected_prompt in response
        else:
            assert "created" in response.lower()

    # Session should be cleared after completion
    assert session.get_session(admin_msg.user_id) is None
    # Tournament create was called with the correct name
    assert created.get("name") == "2VS2 TOUR"
    assert updated.get("host_mode") == "auto"


# ── /tourneyset new fields ────────────────────────────────────────────────────

def test_tourneyset_accepts_desc(admin_msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    monkeypatch.setattr(admin.tournament, "update_active_tournament_field", lambda f, v: True)
    res = admin._handle_tourneyset(admin_msg, "desc Funky promo text")
    assert "Updated" in res

def test_tourneyset_accepts_regtime(admin_msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    monkeypatch.setattr(admin.tournament, "update_active_tournament_field", lambda f, v: True)
    res = admin._handle_tourneyset(admin_msg, "regtime 30 minutes prior")
    assert "Updated" in res

def test_tourneyset_rejects_unknown_field(admin_msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    res = admin._handle_tourneyset(admin_msg, "bio something")
    assert "Unknown field" in res


# ── /register rejects args ────────────────────────────────────────────────────

def test_register_no_args_ok(monkeypatch):
    msg = IncomingMessage("x","main","u","User","/register",False,"2026")
    monkeypatch.setattr(community.require_main, "__code__", (lambda m: None).__code__)
    monkeypatch.setattr(community.tournament, "register_user", lambda uid, uname, tag: f"Registered {uname}")
    res = community._handle_register(msg, "")
    assert "Registered" in res

def test_register_rejects_args(monkeypatch):
    msg = IncomingMessage("x","main","u","User","/register MyTag",False,"2026")
    monkeypatch.setattr(community.require_main, "__code__", (lambda m: None).__code__)
    res = community._handle_register(msg, "MyTag")
    assert "Usage" in res


# ── Sticker commands basic check ─────────────────────────────────────────────

def test_all_sticker_commands_registered():
    expected = {"slap","kiss","wink","hug","pat","bonk","disgust","rip","clap","laugh","cry"}
    registered = set(handlers.HANDLERS.keys())
    assert expected.issubset(registered), f"Missing sticker commands: {expected - registered}"

def test_sticker_missing_target(monkeypatch):
    import bot.handlers.fun as fun
    msg = IncomingMessage("x","main","u","User","/hug",False,"2026")
    monkeypatch.setattr(fun.require_main, "__code__", (lambda m: None).__code__)
    res = fun.HANDLERS["hug"](msg, "")
    assert "Usage" in res


# ── /8ball, /dice, /coin removed ─────────────────────────────────────────────

def test_removed_commands_not_in_handlers():
    for cmd in ("8ball", "dice", "coin"):
        assert cmd not in handlers.HANDLERS, f"/{cmd} should have been removed"
