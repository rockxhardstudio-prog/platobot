import pytest
from bot.models.message import IncomingMessage
from bot.handlers import fun

@pytest.fixture
def msg():
    return IncomingMessage(
        message_id="test1",
        group_id="main",
        user_id="u1",
        username="TestUser",
        text="/roast",
        is_self=False,
        timestamp="2026-09-19T10:00:00Z"
    )

def test_extract_target():
    assert fun._extract_target(" @bob ") == "@bob"
    assert fun._extract_target(" @bob @alice ", require_two=True) == "@bob @alice"
    assert fun._extract_target(" @bob ", require_two=True) is None

def test_handle_roast(msg, monkeypatch):
    monkeypatch.setattr(fun.require_main, "__code__", (lambda m: None).__code__)
    res = fun._handle_roast(msg, "@bob")
    assert "@bob" in res
    
def test_handle_ship(msg, monkeypatch):
    monkeypatch.setattr(fun.require_main, "__code__", (lambda m: None).__code__)
    res = fun._handle_ship(msg, "@bob @alice")
    assert "Ship compatibility" in res
    assert "@bob" in res
    
def test_handle_bully(msg, monkeypatch):
    monkeypatch.setattr(fun.require_main, "__code__", (lambda m: None).__code__)
    res = fun._handle_bully(msg, "@bob")
    assert "@bob" in res

def test_handle_slap(msg, monkeypatch):
    monkeypatch.setattr(fun.require_main, "__code__", (lambda m: None).__code__)
    res = fun.HANDLERS["slap"](msg, "@bob")
    assert "[STICKER:SLAP]" in res
    assert "slaps @bob" in res
