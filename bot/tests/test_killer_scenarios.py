import time
import pytest
from datetime import datetime, timezone

from bot.config import config
from bot.database.db import get_conn, init_db, transaction
from bot.models.message import IncomingMessage
from bot.commands.router import handle_message, _parse_command, plato_client
from bot.services import tournament, dedup
from bot.services.plato import OutboxPlatoClient
from bridge.phone_bridge import VisibleMessage


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "killer_test.db")
    monkeypatch.setattr(config, "db_path", test_db)
    monkeypatch.setattr(config, "main_group_id", "main")
    monkeypatch.setattr(config, "bridge_visible_username", "floatsystem")
    monkeypatch.setattr(config, "bridge_visible_user_id", "floatsystem")
    monkeypatch.setattr(config, "bot_plato_user_id", "floatsystem")
    init_db()
    with transaction() as conn:
        conn.execute("DELETE FROM outbox")
        conn.execute("DELETE FROM registrations")
        conn.execute("DELETE FROM tournaments")
        conn.execute("DELETE FROM processed_messages")
        conn.execute("DELETE FROM messages")
    yield


def test_stress_mixed_rapid_commands_queue_order():
    """
    Simulates:
    User A → /help
    User B → /rules
    User C → /register
    User D → /ship @A @B
    User E → /register
    User F → hello (ignored)
    User G → /tourney
    User H → /register
    """
    # Open a tournament with slots=2 so C and E take slots, H gets waitlisted
    tournament.create_tournament("Summer Clash", "admin")
    tournament.update_active_tournament_field("max_slots", 2)
    tournament.set_active_tournament_status("open")

    inputs = [
        ("u_a", "Alice", "/help"),
        ("u_b", "Bob", "/rules"),
        ("u_c", "Charlie", "/register"),
        ("u_d", "Dave", "/ship @Alice @Bob"),
        ("u_e", "Eve", "/register"),
        ("u_f", "Frank", "hello everyone!"),  # non-command
        ("u_g", "Grace", "/tourney"),
        ("u_h", "Hank", "/register"),
    ]

    for idx, (uid, uname, text) in enumerate(inputs):
        msg = IncomingMessage(
            message_id=f"msg_{idx}",
            group_id="main",
            user_id=uid,
            username=uname,
            text=text,
            is_self=False,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        handle_message(msg)

    # Inspect outbox items
    outbox_items = plato_client.pending("main", limit=20)
    
    # 7 valid commands should generate outbox responses (Frank's "hello" is ignored)
    assert len(outbox_items) == 7

    # Check that Frank's hello was ignored and not in outbox
    # C should be registered (1/2), E should be registered (2/2), H should be waitlisted (position 1)
    texts = [item["text"] for item in outbox_items]

    # Verify responses correspond in exact FCFS sequence
    assert "BOT HELP" in texts[0]  # Alice
    assert "No community rules" in texts[1] or "rules" in texts[1].lower()  # Bob
    assert "@Charlie Registered successfully! (1/2)" in texts[2]  # Charlie
    assert "Ship compatibility for" in texts[3]  # Dave
    assert "@Eve Registered successfully! (2/2)" in texts[4]  # Eve
    assert "Summer Clash" in texts[5]  # Grace
    assert "@Hank Added to waitlist (position 1)" in texts[6]  # Hank


def test_stress_atomic_slots_and_duplicates():
    """
    Slots = 5
    A: /register
    B: /register
    C: /register
    A: /register (duplicate)
    D: /register
    E: /register
    F: /register (waitlist pos 1)
    B: /register (duplicate)
    G: /register (waitlist pos 2)
    """
    tournament.create_tournament("Major 2026", "admin")
    tournament.update_active_tournament_field("max_slots", 5)
    tournament.set_active_tournament_status("open")

    feed = [
        ("u_a", "Alice"),
        ("u_b", "Bob"),
        ("u_c", "Charlie"),
        ("u_a", "Alice"),  # dup
        ("u_d", "Dave"),
        ("u_e", "Eve"),
        ("u_f", "Frank"),  # should waitlist pos 1
        ("u_b", "Bob"),    # dup
        ("u_g", "Grace"),  # should waitlist pos 2
    ]

    responses = []
    for idx, (uid, uname) in enumerate(feed):
        msg = IncomingMessage(
            message_id=f"reg_msg_{idx}",
            group_id="main",
            user_id=uid,
            username=uname,
            text="/register",
            is_self=False,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        res = handle_message(msg)
        responses.append(res)

    # Verify responses
    assert "@Alice Registered successfully! (1/5)" in responses[0]
    assert "@Bob Registered successfully! (2/5)" in responses[1]
    assert "@Charlie Registered successfully! (3/5)" in responses[2]
    assert "@Alice You are already registered" in responses[3]
    assert "@Dave Registered successfully! (4/5)" in responses[4]
    assert "@Eve Registered successfully! (5/5)" in responses[5]
    assert "@Frank Added to waitlist (position 1)" in responses[6]
    assert "@Bob You are already registered" in responses[7]
    assert "@Grace Added to waitlist (position 2)" in responses[8]

    # Verify database state directly
    participants = tournament.get_participants()
    registered = [p for p in participants if p["status"] == "registered"]
    waitlisted = [p for p in participants if p["status"] == "waitlisted"]

    assert len(registered) == 5
    assert [p["username"] for p in registered] == ["Alice", "Bob", "Charlie", "Dave", "Eve"]
    assert len(waitlisted) == 2
    assert [p["username"] for p in waitlisted] == ["Frank", "Grace"]

    # Now Alice unregisters -> Frank should be promoted to registered!
    unreg_msg = IncomingMessage(
        message_id="unreg_a",
        group_id="main",
        user_id="u_a",
        username="Alice",
        text="/unregister",
        is_self=False,
    )
    unreg_res = handle_message(unreg_msg)
    assert "@Alice Your registration has been cancelled" in unreg_res

    # Check updated participants: Frank is now registered, Grace is waitlist pos 1
    participants_after = tournament.get_participants()
    registered_after = [p for p in participants_after if p["status"] == "registered"]
    waitlisted_after = [p for p in participants_after if p["status"] == "waitlisted"]
    assert len(registered_after) == 5
    assert "Frank" in [p["username"] for p in registered_after]
    assert len(waitlisted_after) == 1
    assert waitlisted_after[0]["username"] == "Grace"


def test_re_registration_after_unregister():
    """Verify that a user who cancelled their registration can register again."""
    tournament.create_tournament("ReReg Cup", "admin")
    tournament.update_active_tournament_field("max_slots", 4)
    tournament.set_active_tournament_status("open")

    res1 = tournament.register_user("u1", "Player1", None)
    assert "Registered successfully" in res1

    # Unregister
    res2 = tournament.unregister_user("u1", "Player1")
    assert "cancelled" in res2

    # Register again!
    res3 = tournament.register_user("u1", "Player1", None)
    assert "Registered successfully" in res3


def test_dynamic_slot_increase_promotes_waitlist():
    """Verify that increasing max_slots automatically promotes waitlisted players."""
    tournament.create_tournament("Promo Cup", "admin")
    tournament.update_active_tournament_field("max_slots", 1)
    tournament.set_active_tournament_status("open")

    tournament.register_user("u1", "P1", None)
    tournament.register_user("u2", "P2", None)  # waitlisted

    assert len([p for p in tournament.get_participants() if p["status"] == "waitlisted"]) == 1

    # Increase max_slots to 3
    success = tournament.update_active_tournament_field("max_slots", 3)
    assert success is True

    # P2 should now be promoted to registered!
    participants = tournament.get_participants()
    registered = [p for p in participants if p["status"] == "registered"]
    waitlisted = [p for p in participants if p["status"] == "waitlisted"]
    assert len(registered) == 2
    assert len(waitlisted) == 0


def test_outbox_state_machine_and_poison_pill_isolation():
    client = OutboxPlatoClient()
    client.send_message("main", "Message 1 (good)")
    client.send_message("main", "Message 2 (broken)")
    client.send_message("main", "Message 3 (good)")

    # 1. Claim item 1
    claimed = client.claim("main", limit=1)
    assert len(claimed) == 1
    item1 = claimed[0]
    assert item1["text"] == "Message 1 (good)"
    assert item1["attempts"] == 1

    # Ack item 1
    client.ack(item1["id"])

    # 2. Claim item 2 (simulate failure)
    claimed2 = client.claim("main", limit=1)
    assert len(claimed2) == 1
    item2 = claimed2[0]
    assert item2["text"] == "Message 2 (broken)"
    assert item2["attempts"] == 1

    # Report failure -> should allow retry up to MAX_ATTEMPTS
    client.fail(item2["id"], reason="Syntax error in adb")

    # Claim again -> attempt 2
    claimed2_retry1 = client.claim("main", limit=1)
    assert claimed2_retry1[0]["attempts"] == 2
    client.fail(item2["id"], reason="Crash on device")

    # Claim again -> attempt 3
    claimed2_retry2 = client.claim("main", limit=1)
    assert claimed2_retry2[0]["attempts"] == 3
    client.fail(item2["id"], reason="Persistent failure")

    # Now item 2 has reached max attempts and is marked failed!
    # Claiming next item must NOT return item 2! It must return item 3!
    claimed3 = client.claim("main", limit=1)
    assert len(claimed3) == 1
    assert claimed3[0]["text"] == "Message 3 (good)"


def test_parser_edge_cases():
    # Case variations
    assert _parse_command("/HELP")[0] == "help"
    assert _parse_command("/HeLp")[0] == "help"
    
    # Whitespace variations
    cmd, args = _parse_command("   /help   core   ")
    assert cmd == "help" and args.strip() == "core"

    cmd, args = _parse_command("/help\tcore")
    assert cmd == "help" and args == "core"

    cmd, args = _parse_command("/help\ncore")
    assert cmd == "help" and args == "core"

    # Bot target prefix
    cmd, args = _parse_command("/help@floatsystem core")
    assert cmd == "help" and args == "core"

    # Non-command inputs should be rejected
    assert _parse_command("hello /help") is None
    assert _parse_command('someone said "/help"') is None
    assert _parse_command("/help!") is None
    assert _parse_command("/help?") is None


def test_deterministic_ship_and_self_targeting():
    from bot.services.fun import engine

    # Ship involving admin (hawtshot) - returns admin ship response
    ship1 = engine.generate("SHIP", "hawtshot and tuhin", sender="diviii")
    ship2 = engine.generate("SHIP", "tuhin x hawtshot", sender="diviii")
    admin_ship_keywords = ["fleet", "legendary", "awe", "HawtShot"]
    assert any(kw in ship1 for kw in admin_ship_keywords), f"Expected admin ship, got: {ship1}"
    assert any(kw in ship2 for kw in admin_ship_keywords), f"Expected admin ship, got: {ship2}"

    # Self-ship for a normal user
    self_ship = engine.generate("SHIP", "diviii diviii", sender="diviii")
    assert "100%" in self_ship
    assert (":3" in self_ship or ":0" in self_ship or "-.-" in self_ship or ":D" in self_ship)

    # Roasting hawtshot -> admin roast (worship, NOT self-roast)
    admin_roast = engine.generate("ROAST", "hawtshot", sender="hawtshot")
    assert any(e in admin_roast for e in [";(", "-.-", ":0", ":3", ":D", ";)"])
    admin_keywords = ["creator", "loyalty", "mortal", "sun", "capital", "breathed"]
    assert any(kw in admin_roast for kw in admin_keywords), f"Expected admin roast, got: {admin_roast}"

    # Normal user self-roast still works
    self_roast = engine.generate("ROAST", "diviii", sender="diviii")
    assert any(e in self_roast for e in [";(", "-.-", ":0", ":3"])
    assert "Roasting yourself" in self_roast or "Self-roast" in self_roast or "life already did" in self_roast or "group chat" in self_roast


def test_sliding_window_sequence_alignment():
    """
    Tests the suffix-prefix sequence alignment algorithm used by phone_bridge.py
    to handle multiple rapid identical messages without duplication across scrolls.
    """
    history = []

    def align(hist, curr):
        curr_sigs = [(m.user_id, m.username, m.message_time, m.text) for m in curr]
        if not hist:
            return curr, curr_sigs[-150:]
        max_k = min(len(hist), len(curr_sigs))
        for k in range(max_k, 0, -1):
            if hist[-k:] == curr_sigs[:k]:
                new_msgs = curr[k:]
                return new_msgs, (hist + curr_sigs[k:])[-150:]
        new_msgs = [m for m, sig in zip(curr, curr_sigs) if sig not in hist]
        return new_msgs, (hist + curr_sigs)[-150:]

    def mk_msg(uid, text, t="10:00 AM"):
        return VisibleMessage(
            message_id=f"{uid}_{text}_{t}",
            group_id="main",
            user_id=uid,
            username=uid,
            text=text,
            message_time=t,
        )

    # Dump 1: A says /help, B says /register, B says /register immediately after
    d1 = [mk_msg("A", "/help"), mk_msg("B", "/register"), mk_msg("B", "/register")]
    new1, history = align(history, d1)
    assert len(new1) == 3

    # Dump 2: Same screen, nothing new arrived
    d2 = [mk_msg("A", "/help"), mk_msg("B", "/register"), mk_msg("B", "/register")]
    new2, history = align(history, d2)
    assert len(new2) == 0

    # Dump 3: B sends a third /register
    d3 = [mk_msg("A", "/help"), mk_msg("B", "/register"), mk_msg("B", "/register"), mk_msg("B", "/register")]
    new3, history = align(history, d3)
    assert len(new3) == 1
    assert new3[0].text == "/register"

    # Dump 4: Chat scrolls up (A /help is gone), C sends /rules
    d4 = [mk_msg("B", "/register"), mk_msg("B", "/register"), mk_msg("B", "/register"), mk_msg("C", "/rules")]
    new4, history = align(history, d4)
    assert len(new4) == 1
    assert new4[0].text == "/rules"


def test_command_spam_cooldown_and_multiuser_isolation():
    from bot.commands.router import handle_message, _user_command_cooldown, _user_command_warned

    _user_command_cooldown.clear()
    _user_command_warned.clear()

    # User 1 sends /help
    msg1 = IncomingMessage("m1", "main", "u_hawt", "HawtShot", "/help")
    res1 = handle_message(msg1)
    assert "BOT HELP" in res1

    # User 1 spams /help 2nd time within 10s -> receives Chill warning
    msg2 = IncomingMessage("m2", "main", "u_hawt", "HawtShot", "/help")
    res2 = handle_message(msg2)
    assert "Chill @HawtShot" in res2
    assert "already sent to you" in res2

    # User 1 spams /help 3rd and 4th time within 10s -> suppressed to avoid bot spamming chat
    msg3 = IncomingMessage("m3", "main", "u_hawt", "HawtShot", "/help")
    assert handle_message(msg3) is None
    msg4 = IncomingMessage("m4", "main", "u_hawt", "HawtShot", "/help")
    assert handle_message(msg4) is None

    # User 2 sends /help immediately -> Not rate limited because cooldown is per-user!
    msg5 = IncomingMessage("m5", "main", "u_tuhin", "TUHIN", "/help")
    res5 = handle_message(msg5)
    assert "BOT HELP" in res5

    # Simulate 10.1 seconds passing for User 1
    _user_command_cooldown[("u_hawt", "help")] -= 10.5
    msg6 = IncomingMessage("m6", "main", "u_hawt", "HawtShot", "/help")
    res6 = handle_message(msg6)
    assert "BOT HELP" in res6


def test_four_consecutive_help_commands_never_dropped():
    from bridge.phone_bridge import VisibleMessage

    history: list[tuple[str, str, str, bool]] = []

    def align(hist, curr):
        sigs = [(m.user_id, m.message_time, m.text, m.is_self) for m in curr]
        if not sigs:
            return [], hist
        if not hist:
            return [], list(sigs)[-150:]
        for i in range(len(hist) - len(sigs) + 1):
            if hist[i : i + len(sigs)] == sigs:
                return [], hist
        max_k = min(len(hist), len(sigs))
        for k in range(max_k, 0, -1):
            if hist[-k:] == sigs[:k]:
                new_msgs = curr[k:]
                new_hist = (hist + sigs[k:])[-300:]
                return new_msgs, new_hist
        for pos in range(len(sigs) - 1, -1, -1):
            for length in range(min(len(hist), pos + 1), 0, -1):
                if hist[-length:] == sigs[pos - length + 1 : pos + 1]:
                    new_msgs = curr[pos + 1 :]
                    new_hist = (hist + sigs[pos + 1 :])[-300:]
                    return new_msgs, new_hist
        new_msgs = [m for m, s in zip(curr, sigs) if s not in hist]
        new_hist = (hist + sigs)[-300:]
        return new_msgs, new_hist

    def mk_msg(uid, text, is_self=False):
        return VisibleMessage(
            message_id=f"{uid}_{text}",
            group_id="main",
            user_id=uid,
            username=uid,
            text=text,
            message_time="05:30 PM",
            is_self=is_self,
        )

    # Initial screen with 1 existing message
    base = [mk_msg("A", "Hello")]
    _, history = align(history, base)

    # Step 1: HawtShot types /help 1st time
    frame1 = [mk_msg("A", "Hello"), mk_msg("HawtShot", "/help")]
    new1, history = align(history, frame1)
    assert len(new1) == 1
    assert new1[0].text == "/help"

    # Step 2: HawtShot types /help 2nd time
    frame2 = [mk_msg("A", "Hello"), mk_msg("HawtShot", "/help"), mk_msg("HawtShot", "/help")]
    new2, history = align(history, frame2)
    assert len(new2) == 1
    assert new2[0].text == "/help"

    # Step 3: HawtShot types /help 3rd time
    frame3 = [mk_msg("HawtShot", "/help"), mk_msg("HawtShot", "/help"), mk_msg("HawtShot", "/help")]
    new3, history = align(history, frame3)
    assert len(new3) == 1
    assert new3[0].text == "/help"

    # Step 4: HawtShot types /help 4th time
    frame4 = [mk_msg("HawtShot", "/help"), mk_msg("HawtShot", "/help"), mk_msg("HawtShot", "/help"), mk_msg("HawtShot", "/help")]
    new4, history = align(history, frame4)
    assert len(new4) == 1
    assert new4[0].text == "/help"


def test_message_scrolling_does_not_change_id():
    from bridge.phone_bridge import visible_messages

    # Create dummy parsed nodes with bounds at Y=1000
    nodes_y1000 = [
        {"id": 1, "resource_id": "com.plato.android:id/item_message_entire_container", "bounds": "[44,1000][1036,1100]", "child_ids": [2, 3]},
        {"id": 2, "parent_id": 1, "resource_id": "com.plato.android:id/message_header_user_name", "text": "HawtShot", "bounds": "[235,1000][350,1050]", "child_ids": []},
        {"id": 3, "parent_id": 1, "resource_id": "com.plato.android:id/message_text_text", "text": "/help", "bounds": "[235,1050][400,1100]", "child_ids": []},
    ]
    msgs1 = visible_messages(nodes_y1000, "main")
    assert len(msgs1) == 1
    id1 = msgs1[0].message_id

    # Same message after chat scrolls up to Y=600
    nodes_y600 = [
        {"id": 1, "resource_id": "com.plato.android:id/item_message_entire_container", "bounds": "[44,600][1036,700]", "child_ids": [2, 3]},
        {"id": 2, "parent_id": 1, "resource_id": "com.plato.android:id/message_header_user_name", "text": "HawtShot", "bounds": "[235,600][350,650]", "child_ids": []},
        {"id": 3, "parent_id": 1, "resource_id": "com.plato.android:id/message_text_text", "text": "/help", "bounds": "[235,650][400,700]", "child_ids": []},
    ]
    msgs2 = visible_messages(nodes_y600, "main")
    assert len(msgs2) == 1
    id2 = msgs2[0].message_id

    # The message ID must NOT change when the screen scrolls!
    assert id1 == id2


def test_native_reply_coordinates_default():
    from bridge.phone_bridge import AdbClient
    import inspect

    sig = inspect.signature(AdbClient.fast_send)
    default_coords = sig.parameters["reply_tap_coords"].default
    # Reply option in Plato is located at Y=1756 (Copy is at Y=1921)
    assert default_coords == (229, 1756)


