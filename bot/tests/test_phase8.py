import pytest
from bot.database.db import init_db
from bot.models.message import IncomingMessage
from bot.services import ai, community
from bot.commands import router


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_build_rag_system_prompt():
    community.set_info("Top tier Plato gaming guild.", "admin")
    community.set_rules("Respect all members, no toxic banter.", "admin")
    prompt = ai.build_rag_system_prompt()
    assert "FloatSystem" in prompt
    assert "Top tier Plato gaming guild." in prompt
    assert "Respect all members" in prompt


def test_ai_graceful_error_handling(monkeypatch):
    # If API key is missing or expired, it returns an intelligent offline fallback without crashing
    from bot.config import config
    monkeypatch.setattr(config, "openai_api_key", "")
    res = ai.generate_ai_response("u1", "Alex", "What are the rules?")
    assert "Rules" in res or "rules" in res.lower()


def test_ai_handler_and_bot_mention(monkeypatch):
    # Mock OpenAI client response to test pipeline end-to-end
    class MockCompletion:
        class Choice:
            class Message:
                content = "The server rules are: respect all players and have fun!"
            message = Message()
        choices = [Choice()]

    class MockClient:
        class Chat:
            class Completions:
                def create(self, **kwargs):
                    return MockCompletion()
            completions = Completions()
        chat = Chat()
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("openai.OpenAI", MockClient)
    from bot.config import config
    monkeypatch.setattr(config, "openai_api_key", "test_mock_key")

    res = ai.generate_ai_response("u1", "PlayerOne", "How do I play Ocho?")
    assert "respect all players" in res

    # Test via router /ai command
    msg_cmd = IncomingMessage(
        message_id="ai_1",
        group_id="main",
        user_id="u1",
        username="PlayerOne",
        text="/ai what are the rules?",
        is_self=False,
        timestamp="2026-10-20T10:00:00Z",
    )
    cmd_out = router.handle_message(msg_cmd)
    assert "respect all players" in cmd_out

    # Test via natural bot mention @zeno
    msg_mention = IncomingMessage(
        message_id="ai_2",
        group_id="main",
        user_id="u1",
        username="PlayerOne",
        text="@zeno can you explain the rules?",
        is_self=False,
        timestamp="2026-10-20T10:00:00Z",
    )
    mention_out = router.handle_message(msg_mention)
    assert "respect all players" in mention_out
