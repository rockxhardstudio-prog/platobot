import pytest
import sqlite3
import os
import tempfile
from bot.services.tournament import create_tournament, register_user, unregister_user, get_participants, update_active_tournament_field, set_active_tournament_status

@pytest.fixture
def db_conn(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("BOT_DB_PATH", db_path)
    
    import importlib
    import sys
    for name in list(sys.modules):
        if name.startswith("bot.database"):
            del sys.modules[name]
            
    db = importlib.import_module("bot.database.db")
    db.init_db()
    
    # Reload tournament module to ensure it uses the new db conn
    for name in list(sys.modules):
        if name.startswith("bot.services.tournament"):
            del sys.modules[name]
    global create_tournament, register_user, unregister_user, get_participants, update_active_tournament_field, set_active_tournament_status
    tourn = importlib.import_module("bot.services.tournament")
    create_tournament = tourn.create_tournament
    register_user = tourn.register_user
    unregister_user = tourn.unregister_user
    get_participants = tourn.get_participants
    update_active_tournament_field = tourn.update_active_tournament_field
    set_active_tournament_status = tourn.set_active_tournament_status
    
    yield db.get_conn()
    
    db.get_conn().close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(db_path + suffix)
        except FileNotFoundError:
            pass

def test_registration_state_transitions(db_conn):
    # Create tournament
    create_tournament("Test Tourney", "admin_1")
    update_active_tournament_field("max_slots", 2)
    
    # Try register while draft
    assert "closed" in register_user("u1", "User1", None)
    
    # Open
    set_active_tournament_status("open")
    
    # Register u1
    res1 = register_user("u1", "User1", None)
    assert "Registered successfully" in res1
    
    # Duplicate
    assert "already registered" in register_user("u1", "User1", None)
    
    # Register u2
    res2 = register_user("u2", "User2", None)
    assert "Registered successfully" in res2
    
    # Register u3 (should waitlist since max_slots is 2)
    res3 = register_user("u3", "User3", None)
    assert "waitlist (position 1)" in res3
    
    # Verify participants
    parts = get_participants()
    assert len(parts) == 3
    assert parts[0]["status"] == "registered"
    assert parts[1]["status"] == "registered"
    assert parts[2]["status"] == "waitlisted"
    
    # Unregister u1
    assert "cancelled" in unregister_user("u1")
    
    # Now u3 should be promoted
    parts = get_participants()
    assert len(parts) == 2  # u1 is cancelled, so not returned
    assert parts[0]["username"] == "User2"
    assert parts[0]["status"] == "registered"
    assert parts[1]["username"] == "User3"
    assert parts[1]["status"] == "registered"
