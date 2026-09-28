import pytest
from bot.models.message import IncomingMessage
from bot.handlers import community

@pytest.fixture
def msg():
    return IncomingMessage(
        message_id="test1",
        group_id="main",
        user_id="u1",
        username="TestUser",
        text="/tourney",
        is_self=False,
        timestamp="2026-09-19T10:00:00Z"
    )

def test_handle_tourney_none(msg, monkeypatch):
    monkeypatch.setattr(community.require_main, "__code__", (lambda m: None).__code__)
    monkeypatch.setattr(community.tournament, "get_active_tournament", lambda: None)
    assert community._handle_tourney(msg, "") == "No tournament is currently active."

def test_handle_tourney_active(msg, monkeypatch):
    monkeypatch.setattr(community.require_main, "__code__", (lambda m: None).__code__)
    mock_tourney = {
        "name": "Test Cup", "status": "open", "game": "Valorant",
        "format": "5v5", "event_date": "Oct 1", "event_time": "8 PM",
        "registration_time": "30m prior",
        "max_slots": 10, "prize_info": "1000", "rules_text": "No cheating"
    }
    monkeypatch.setattr(community.tournament, "get_active_tournament", lambda: mock_tourney)
    res = community._handle_tourney(msg, "")
    assert "Test Cup" in res
    assert "OPEN" in res
    assert "Valorant" in res

def test_handle_events_empty(msg, monkeypatch):
    monkeypatch.setattr(community.require_main, "__code__", (lambda m: None).__code__)
    monkeypatch.setattr(community.events, "get_upcoming_events", lambda: [])
    assert community._handle_events(msg, "") == "No upcoming events scheduled."

def test_handle_register(msg, monkeypatch):
    monkeypatch.setattr(community.require_main, "__code__", (lambda m: None).__code__)
    monkeypatch.setattr(community.tournament, "register_user", lambda uid, uname, tag: f"Reg: {uname}")
    assert community._handle_register(msg, "") == "Reg: TestUser"
    assert "Usage: just /register" in community._handle_register(msg, "MyTag")
    
def test_handle_unregister(msg, monkeypatch):
    monkeypatch.setattr(community.require_main, "__code__", (lambda m: None).__code__)
    monkeypatch.setattr(community.tournament, "unregister_user", lambda uid: "Unregistered")
    assert community._handle_unregister(msg, "") == "Unregistered"
