import pytest
from bot.models.message import IncomingMessage
from bot.handlers import admin

@pytest.fixture
def msg():
    return IncomingMessage(
        message_id="test1",
        group_id="storage",
        user_id="admin_user",
        username="Admin",
        text="/setinfo",
        is_self=False,
        timestamp="2026-09-19T10:00:00Z"
    )

def test_handle_setinfo(msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    monkeypatch.setattr(admin.community, "set_info", lambda text, uid: None)
    assert admin._handle_setinfo(msg, "New Info") == "Community info updated."

def test_handle_tourneyset(msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    
    updates = []
    def mock_update(field, value):
        updates.append((field, value))
        return True
        
    monkeypatch.setattr(admin.tournament, "update_active_tournament_field", mock_update)
    
    res = admin._handle_tourneyset(msg, "slots 10")
    assert res == "Updated slots."
    assert updates[0] == ("max_slots", 10)
    
    res = admin._handle_tourneyset(msg, "game Valorant")
    assert res == "Updated game."
    assert updates[1] == ("game", "Valorant")
    
def test_handle_tourneyset_bad_field(msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    res = admin._handle_tourneyset(msg, "invalid 123")
    assert "Unknown field" in res

def test_handle_warn(msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    monkeypatch.setattr(admin.moderation, "add_warning", lambda uid, un, r, admin: 3)
    res = admin._handle_warn(msg, "badguy spamming")
    assert "Warned badguy for: spamming" in res
    assert "reached 3 warnings" in res

def test_handle_clearwarn(msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    monkeypatch.setattr(admin.moderation, "clear_warnings", lambda u: 2)
    assert admin._handle_clearwarn(msg, "badguy") == "Cleared 2 warnings for badguy."

def test_handle_tourneyclear(msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    monkeypatch.setattr(admin.tournament, "clear_active_tournament", lambda: True)
    assert admin._handle_tourneyclear(msg, "") == "Active tournament archived."

def test_handle_eventadd(msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    monkeypatch.setattr(admin.events, "add_event", lambda n, d, desc, uid: None)
    assert admin._handle_eventadd(msg, "Game Night | Oct 1 | Fun times") == "Event 'Game Night' added."

def test_handle_eventdel(msg, monkeypatch):
    monkeypatch.setattr(admin.require_storage_admin, "__code__", (lambda m: None).__code__)
    monkeypatch.setattr(admin.events, "delete_event", lambda n: True)
    assert admin._handle_eventdel(msg, "Game Night") == "Event 'Game Night' deleted."
