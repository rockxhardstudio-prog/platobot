import pytest
from bot.models.message import IncomingMessage
from bot.handlers import core

@pytest.fixture
def msg():
    return IncomingMessage(
        message_id="test1",
        group_id="main",
        user_id="u1",
        username="TestUser",
        text="/help",
        is_self=False,
        timestamp="2026-09-19T10:00:00Z"
    )

def test_handle_help(msg, monkeypatch):
    monkeypatch.setattr(core.config, "main_group_id", "main")
    res = core._handle_help(msg, "")
    assert "BOT HELP" in res
    assert "/help tourney" in res
    assert len(res) <= 256

def test_handle_help_category_tourney(msg, monkeypatch):
    monkeypatch.setattr(core.config, "main_group_id", "main")
    res = core._handle_help(msg, "tourney")
    assert "/tourney" in res
    assert len(res) <= 256

def test_handle_help_category_fun(msg, monkeypatch):
    monkeypatch.setattr(core.config, "main_group_id", "main")
    res = core._handle_help(msg, "fun")
    assert "/roast" in res
    assert len(res) <= 256

def test_handle_info_empty(msg, monkeypatch):
    monkeypatch.setattr(core.config, "main_group_id", "main")
    monkeypatch.setattr(core, "get_info", lambda: None)
    assert core._handle_info(msg, "") == "No community info has been set yet."

def test_handle_info_set(msg, monkeypatch):
    monkeypatch.setattr(core.config, "main_group_id", "main")
    monkeypatch.setattr(core, "get_info", lambda: "Welcome to Plato!")
    assert core._handle_info(msg, "") == "Welcome to Plato!"

def test_handle_announce(msg, monkeypatch):
    monkeypatch.setattr(core.config, "main_group_id", "main")
    monkeypatch.setattr(core, "get_announcement", lambda: "Server restart in 5 mins")
    assert core._handle_announce(msg, "") == "📢 Server restart in 5 mins"
