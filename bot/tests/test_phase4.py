import pytest
from bot.models.message import IncomingMessage
from bot.services import autoresponse
from bot.commands import router


@pytest.fixture
def msg_factory():
    def _create(text, uid="u_p4", uname="Alex"):
        return IncomingMessage(
            message_id="msg_test",
            group_id="main",
            user_id=uid,
            username=uname,
            text=text,
            is_self=False,
            timestamp="2026-10-20T10:00:00Z",
        )
    return _create


def test_standalone_greetings_vs_sentences(msg_factory):
    # Standalone should trigger
    autoresponse._user_cooldowns.clear()
    autoresponse._channel_last_response.clear()
    reply = autoresponse.check_auto_response("u1", "Alex", "main", "hello")
    assert reply is not None and "Alex" in reply

    # Mid-sentence should NOT trigger
    assert autoresponse.check_auto_response("u2", "Bob", "main", "this is high quality gameplay") is None
    assert autoresponse.check_auto_response("u3", "Charlie", "main", "they went by plane") is None
    assert autoresponse.check_auto_response("u4", "Dave", "main", "saying goodbye is difficult") is None


def test_personal_and_universal_birthday_wishes(msg_factory):
    autoresponse._user_cooldowns.clear()
    autoresponse._channel_last_response.clear()

    # Personal wish targets mentioned user
    p_reply = autoresponse.check_auto_response("u1", "Alice", "main", "Happy birthday @Alex!")
    assert p_reply is not None and "@Alex" in p_reply and ("🎂" in p_reply or "★" in p_reply)

    # Universal wish targets room
    autoresponse._channel_last_response.clear()
    u_reply = autoresponse.check_auto_response("u2", "Bob", "main", "hbd everyone")
    assert u_reply is not None and "Happy Birthday" in u_reply


def test_timezone_aware_wishes(msg_factory, monkeypatch):
    autoresponse._user_cooldowns.clear()
    autoresponse._channel_last_response.clear()

    # Test morning hour (e.g. 9 AM)
    monkeypatch.setattr(autoresponse, "_get_local_hour", lambda: 9)
    m_reply = autoresponse.check_auto_response("u1", "Sam", "main", "gm all")
    assert m_reply is not None and "Good morning" in m_reply

    # Test night hour (e.g. 23 PM)
    autoresponse._user_cooldowns.clear()
    autoresponse._channel_last_response.clear()
    monkeypatch.setattr(autoresponse, "_get_local_hour", lambda: 23)
    n_reply = autoresponse.check_auto_response("u2", "Sam", "main", "gn guys")
    assert n_reply is not None and "Good night" in n_reply


def test_greeting_cooldown(msg_factory):
    autoresponse._user_cooldowns.clear()
    autoresponse._channel_last_response.clear()

    r1 = autoresponse.check_auto_response("u_cd", "Player", "main", "hey")
    assert r1 is not None

    # Immediate second greeting from same user is blocked by cooldown
    r2 = autoresponse.check_auto_response("u_cd", "Player", "main", "hey")
    assert r2 is None
