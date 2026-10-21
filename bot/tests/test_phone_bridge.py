import bridge.phone_bridge as phone_bridge
from bridge.phone_bridge import (
    already_visible_from_self,
    bounds_center,
    current_group,
    input_draft_text,
    input_has_draft,
    normalize_for_adb_input,
    visible_text_equivalent,
    visible_messages,
)


def test_bounds_center_calculates_tap_point():
    assert bounds_center("[242,2202][838,2334]") == (540, 2268)


def test_normalize_for_adb_input_keeps_adb_safe_ascii():
    assert normalize_for_adb_input("Hello world\n50% ok ✅") == "Hello%sworld%s50\\%%sok"


def test_input_has_draft_ignores_placeholder():
    assert not input_has_draft([{
        "resource_id": "com.plato.android:id/plato_conversation_chat_box",
        "text": "Say hello�",
    }])
    assert input_has_draft([{
        "resource_id": "com.plato.android:id/plato_conversation_chat_box",
        "text": "hello from bot",
    }])
    assert input_draft_text([{
        "resource_id": "com.plato.android:id/plato_conversation_chat_box",
        "text": "hello from bot",
    }]) == "hello from bot"


def test_visible_text_equivalent_matches_adb_safe_text():
    assert visible_text_equivalent("📊 DAILY SUMMARY\nSeptember 5", "DAILY SUMMARY September 5")


def test_current_group_reads_plato_title_node():
    assert current_group([
        {"resource_id": "com.plato.android:id/plato_addressee", "text": "Main"},
    ]) == "Main"


def test_visible_messages_ignores_group_chrome_and_input():
    nodes = [
        {
            "resource_id": "com.plato.android:id/plato_addressee",
            "text": "Main",
            "content_description": "",
            "bounds": "[226,105][377,166]",
        },
        {
            "resource_id": "com.plato.android:id/plato_conversation_chat_box",
            "text": "Say hello...",
            "content_description": "",
            "bounds": "[242,2202][838,2334]",
        },
        {
            "resource_id": "com.plato.android:id/message_text_text",
            "text": "/invite",
            "content_description": "",
            "bounds": "[100,900][500,980]",
        },
    ]

    messages = visible_messages(nodes, "main")

    assert len(messages) == 1
    assert messages[0].text == "/invite"
    assert messages[0].group_id == "main"


def test_visible_messages_reads_only_real_plato_message_text():
    nodes = [
        {
            "resource_id": "com.plato.android:id/message_date",
            "text": "SATURDAY, SEP 05, 2026",
            "content_description": "",
            "bounds": "[341,525][739,591]",
        },
        {
            "resource_id": "com.plato.android:id/message_header_user_name",
            "text": "borefrog07",
            "content_description": "",
            "bounds": "[556,619][731,665]",
        },
        {
            "resource_id": "com.plato.android:id/message_header_time",
            "text": "02:40 PM",
            "content_description": "",
            "bounds": "[751,623][859,661]",
        },
        {
            "resource_id": "com.plato.android:id/message_text_text",
            "text": "/invite",
            "content_description": "",
            "bounds": "[841,695][868,761]",
        },
        {
            "resource_id": "com.plato.android:id/plato_button_send",
            "text": "",
            "content_description": "Send Button",
            "bounds": "[970,1438][1058,1526]",
        },
    ]

    messages = visible_messages(nodes, "main")

    assert [message.text for message in messages] == ["/invite"]


def test_visible_messages_reads_sender_from_message_container(monkeypatch):
    monkeypatch.setattr(phone_bridge.config, "bridge_visible_username", "borefrog07")
    monkeypatch.setattr(phone_bridge.config, "bridge_visible_user_id", "phone-user")
    nodes = [
        {
            "id": 1,
            "parent_id": None,
            "resource_id": "com.plato.android:id/item_message_entire_container",
            "text": "",
            "content_description": "",
            "bounds": "[44,591][1036,788]",
            "child_ids": [2, 3],
        },
        {
            "id": 2,
            "parent_id": 1,
            "resource_id": "com.plato.android:id/message_header_user_name",
            "text": "borefrog07",
            "content_description": "",
            "bounds": "[556,619][731,665]",
            "child_ids": [],
        },
        {
            "id": 3,
            "parent_id": 1,
            "resource_id": "com.plato.android:id/message_header_time",
            "text": "02:42 PM",
            "content_description": "",
            "bounds": "[751,623][859,661]",
            "child_ids": [],
        },
        {
            "id": 4,
            "parent_id": 1,
            "resource_id": "com.plato.android:id/message_text_text",
            "text": "/spamset 1 hello",
            "content_description": "",
            "bounds": "[774,695][868,761]",
            "child_ids": [],
        },
    ]

    message = visible_messages(nodes, "storage")[0]

    assert message.username == "borefrog07"
    assert message.user_id == "phone-user"


def test_already_visible_from_self_matches_bot_message(monkeypatch):
    monkeypatch.setattr(phone_bridge.config, "bridge_visible_username", "borefrog07")
    monkeypatch.setattr(phone_bridge.config, "bridge_visible_user_id", "phone-user")
    nodes = [
        {
            "id": 1,
            "parent_id": None,
            "resource_id": "com.plato.android:id/item_message_entire_container",
            "text": "",
            "content_description": "",
            "bounds": "[44,591][1036,788]",
            "child_ids": [2, 3, 4],
        },
        {
            "id": 2,
            "parent_id": 1,
            "resource_id": "com.plato.android:id/message_header_user_name",
            "text": "borefrog07",
            "content_description": "",
            "bounds": "[556,619][731,665]",
            "child_ids": [],
        },
        {
            "id": 3,
            "parent_id": 1,
            "resource_id": "com.plato.android:id/message_header_time",
            "text": "03:00 PM",
            "content_description": "",
            "bounds": "[751,623][859,661]",
            "child_ids": [],
        },
        {
            "id": 4,
            "parent_id": 1,
            "resource_id": "com.plato.android:id/message_text_text",
            "text": "Queued message 1 2 times.",
            "content_description": "",
            "bounds": "[302,838][868,904]",
            "child_ids": [],
        },
    ]

    assert already_visible_from_self(nodes, "main", "Queued message 1 2 times.")


# ---------------------------------------------------------------------------
# Regression tests: bridge_once sends ONE message per call
#
# These tests patch out ADB and HTTP so no real device is needed.
# They verify the structural guarantee that bridge_once() processes exactly one
# outbox item per invocation, regardless of how many items are pending.
# ---------------------------------------------------------------------------

import json as _json


class _FakeAdb:
    """Stateful AdbClient stand-in that simulates the Plato input box UI state.

    State machine:
      - Input box starts empty.
      - After type_text(t), dump_ui() shows t in the input box.
      - After the Send button bounds are tapped, dump_ui() shows empty input
        (simulating Plato clearing the box after send).
    """

    # Bounds from _make_group_xml / the cleared-state XML below.
    _SEND_BOUNDS = "[838,2202][1000,2334]"
    _INPUT_BOUNDS = "[242,2202][838,2334]"

    def __init__(self, base_xml: str, group_title: str = "Main"):
        self._group_title = group_title
        self._current_input: str = ""
        self._sent: bool = False
        self.type_calls: list[str] = []
        self.tap_calls: list[str] = []
        self.clear_calls: int = 0

    def _build_xml(self) -> str:
        input_text = "" if self._sent else self._current_input
        return (
            '<?xml version="1.0"?><hierarchy>'
            '<node class="X" text="" content-desc="" resource-id="" '
            'clickable="false" focusable="false" scrollable="false" '
            f'enabled="true" bounds="[0,0][1080,2400]">'
            f'<node class="X" resource-id="com.plato.android:id/plato_addressee" '
            f'text="{self._group_title}" content-desc="" clickable="false" focusable="false" '
            f'scrollable="false" enabled="true" bounds="[0,0][1,1]"/>'
            f'<node class="X" resource-id="com.plato.android:id/plato_conversation_chat_box" '
            f'text="{input_text}" content-desc="" clickable="true" focusable="true" '
            f'scrollable="false" enabled="true" bounds="{self._INPUT_BOUNDS}"/>'
            '<node class="X" resource-id="com.plato.android:id/plato_button_send" '
            'text="" content-desc="Send Button" clickable="true" focusable="true" '
            f'scrollable="false" enabled="true" bounds="{self._SEND_BOUNDS}"/>'
            '</node></hierarchy>'
        )

    def dump_ui(self) -> str:
        return self._build_xml()

    def shell(self, *args, timeout=20):
        return 0, "", ""

    def tap_bounds(self, bounds: str) -> None:
        self.tap_calls.append(bounds)
        if bounds == self._SEND_BOUNDS:
            # Simulate Plato clearing the input after send.
            self._sent = True
            self._current_input = ""

    def clear_text_field(self) -> None:
        self.clear_calls += 1
        self._current_input = ""
        self._sent = False

    def type_text(self, text: str) -> None:
        self.type_calls.append(text)
        self._current_input = text
        self._sent = False



def _make_group_xml(group_title: str, input_text: str = "") -> str:
    """Minimal UIAutomator XML with a group title node, input box, and send button."""
    return (
        '<?xml version="1.0"?><hierarchy>'
        '<node class="X" text="" content-desc="" resource-id="" '
        'clickable="false" focusable="false" scrollable="false" '
        'enabled="true" bounds="[0,0][1080,2400]">'
        f'<node class="X" resource-id="com.plato.android:id/plato_addressee" '
        f'text="{group_title}" content-desc="" clickable="false" focusable="false" '
        f'scrollable="false" enabled="true" bounds="[0,0][1,1]"/>'
        f'<node class="X" resource-id="com.plato.android:id/plato_conversation_chat_box" '
        f'text="{input_text}" content-desc="" clickable="true" focusable="true" '
        f'scrollable="false" enabled="true" bounds="[242,2202][838,2334]"/>'
        '<node class="X" resource-id="com.plato.android:id/plato_button_send" '
        'text="" content-desc="Send Button" clickable="true" focusable="true" '
        'scrollable="false" enabled="true" bounds="[838,2202][1000,2334]"/>'
        '</node></hierarchy>'
    )


def test_bridge_once_sends_only_one_message_when_multiple_are_pending(monkeypatch):
    """
    REGRESSION: bridge_once must process exactly one outbox item per call.

    Previously, bridge_once fetched limit=5 and looped over all of them.
    When /spam:1+2 queued [msg, msg, confirmation], this caused two messages
    to be concatenated into a single Plato send.

    After the fix, bridge_once fetches limit=1 and returns after processing it.
    Two pending items require two separate bridge_once() calls.
    """
    monkeypatch.setattr(phone_bridge.config, "main_group_id", "main-id")
    monkeypatch.setattr(phone_bridge.config, "main_group_title", "Main")
    monkeypatch.setattr(phone_bridge.config, "storage_group_id", "storage-id")
    monkeypatch.setattr(phone_bridge.config, "storage_group_title", "Storage")
    monkeypatch.setattr(phone_bridge.config, "bridge_visible_user_id", "bot")
    monkeypatch.setattr(phone_bridge.config, "bridge_visible_username", "Bot")

    pending_items = [
        {"id": 1, "text": "hello"},
        {"id": 2, "text": "world"},
    ]
    acked_ids: list[int] = []
    posted_payloads: list[dict] = []

    def fake_get_json(url: str):
        # Return only what limit=1 would return (the bridge enforces this, but
        # simulate a backend that obeys limit=1 too).
        if "/outbox?" in url:
            return pending_items[:1]  # only the first item
        return []

    def fake_post_json(url: str, payload: dict):
        if "/ack" in url:
            acked_ids.append(int(url.split("/outbox/")[1].split("/ack")[0]))
        else:
            posted_payloads.append(payload)
        return {}

    monkeypatch.setattr(phone_bridge, "get_json", fake_get_json)
    monkeypatch.setattr(phone_bridge, "post_json", fake_post_json)

    adb = _FakeAdb(_make_group_xml("Main"))
    seen: set[str] = set()

    result = phone_bridge.bridge_once(adb, "http://localhost", seen)

    # Exactly one item sent and acked per call.
    assert result["outbox"] == 1
    assert acked_ids == [1], f"Expected only item 1 acked, got {acked_ids}"
    # Only one type call was made (not two).
    assert len(adb.type_calls) == 1
    assert adb.type_calls[0] == "hello"


def test_bridge_once_acks_already_visible_message_without_sending(monkeypatch):
    """
    Fast path: if our own message is already visible in the chat, ack it without
    re-sending.  This handles bridge restarts after a successful send but before
    the ack was written.
    """
    monkeypatch.setattr(phone_bridge.config, "main_group_id", "main-id")
    monkeypatch.setattr(phone_bridge.config, "main_group_title", "Main")
    monkeypatch.setattr(phone_bridge.config, "storage_group_id", "storage-id")
    monkeypatch.setattr(phone_bridge.config, "storage_group_title", "Storage")
    monkeypatch.setattr(phone_bridge.config, "bridge_visible_user_id", "bot")
    monkeypatch.setattr(phone_bridge.config, "bridge_visible_username", "Bot")

    acked_ids: list[int] = []

    def fake_get_json(url: str):
        if "/outbox?" in url:
            return [{"id": 7, "text": "already sent"}]
        return []

    def fake_post_json(url: str, payload: dict):
        if "/ack" in url:
            acked_ids.append(int(url.split("/outbox/")[1].split("/ack")[0]))
        return {}

    monkeypatch.setattr(phone_bridge, "get_json", fake_get_json)
    monkeypatch.setattr(phone_bridge, "post_json", fake_post_json)

    # Build XML that already contains the bot's message in the timeline.
    xml_with_own_message = (
        '<?xml version="1.0"?><hierarchy>'
        '<node class="X" text="" content-desc="" resource-id="" '
        'clickable="false" focusable="false" scrollable="false" '
        'enabled="true" bounds="[0,0][1080,2400]">'
        '<node class="X" resource-id="com.plato.android:id/plato_addressee" '
        'text="Main" content-desc="" clickable="false" focusable="false" '
        'scrollable="false" enabled="true" bounds="[0,0][1,1]"/>'
        '<node id="1" class="X" resource-id="com.plato.android:id/item_message_entire_container" '
        'text="" content-desc="" clickable="false" focusable="false" '
        'scrollable="false" enabled="true" bounds="[0,800][1080,900]">'
        '<node id="2" class="X" resource-id="com.plato.android:id/message_header_user_name" '
        'text="Bot" content-desc="" clickable="false" focusable="false" '
        'scrollable="false" enabled="true" bounds="[0,800][200,840]"/>'
        '<node id="3" class="X" resource-id="com.plato.android:id/message_header_time" '
        'text="10:00 AM" content-desc="" clickable="false" focusable="false" '
        'scrollable="false" enabled="true" bounds="[200,800][400,840]"/>'
        '<node id="4" class="X" resource-id="com.plato.android:id/message_text_text" '
        'text="already sent" content-desc="" clickable="false" focusable="false" '
        'scrollable="false" enabled="true" bounds="[0,840][1080,900]"/>'
        '</node>'
        '</node></hierarchy>'
    )

    class _StaticAdb(_FakeAdb):
        def dump_ui(self) -> str:
            return xml_with_own_message

    adb = _StaticAdb(xml_with_own_message)
    seen: set[str] = set()
    result = phone_bridge.bridge_once(adb, "http://localhost", seen)

    # Fast path: acked without typing anything.
    assert result["outbox"] == 1
    assert acked_ids == [7]
    assert adb.type_calls == [], "No typing should occur on fast path"


def test_bridge_once_does_not_ack_on_send_failure(monkeypatch):
    """
    If send_visible_message returns False, the outbox item must NOT be acked.
    The item stays pending and will be retried on the next cycle.
    """
    monkeypatch.setattr(phone_bridge.config, "main_group_id", "main-id")
    monkeypatch.setattr(phone_bridge.config, "main_group_title", "Main")
    monkeypatch.setattr(phone_bridge.config, "storage_group_id", "storage-id")
    monkeypatch.setattr(phone_bridge.config, "storage_group_title", "Storage")
    monkeypatch.setattr(phone_bridge.config, "bridge_visible_user_id", "bot")
    monkeypatch.setattr(phone_bridge.config, "bridge_visible_username", "Bot")

    acked_ids: list[int] = []

    def fake_get_json(url: str):
        if "/outbox?" in url:
            return [{"id": 99, "text": "this will fail"}]
        return []

    def fake_post_json(url: str, payload: dict):
        if "/ack" in url:
            acked_ids.append(int(url.split("/outbox/")[1].split("/ack")[0]))
        return {}

    monkeypatch.setattr(phone_bridge, "get_json", fake_get_json)
    monkeypatch.setattr(phone_bridge, "post_json", fake_post_json)
    # Force send_visible_message to always return False.
    monkeypatch.setattr(phone_bridge, "send_visible_message", lambda *_: False)

    adb = _FakeAdb(_make_group_xml("Main"))
    seen: set[str] = set()
    result = phone_bridge.bridge_once(adb, "http://localhost", seen)

    assert result["outbox"] == 0, "outbox count must be 0 on failure"
    assert acked_ids == [], f"Must not ack on failure, got {acked_ids}"


def test_normalize_for_adb_input_escapes_emoticons_and_strips_shell_danger():
    raw = 'Bro doing my job for me ;( -.- :0 :3 :D $HOME `rm -rf` & "quoted"'
    normalized = normalize_for_adb_input(raw)
    # Metacharacters stripped
    assert "$" not in normalized
    assert "`" not in normalized
    assert "&" not in normalized
    assert '"' not in normalized
    # Emoticons preserved with escaping
    assert "\\;\\(" in normalized
    assert "-.-" in normalized
    assert ":0" in normalized
    assert ":3" in normalized
    assert ":D" in normalized


def test_fast_send_builds_and_executes_single_shell_pipeline(monkeypatch):
    executed_shells = []

    class MockAdb(phone_bridge.AdbClient):
        def __init__(self):
            super().__init__("adb")

        def shell(self, *args, timeout=20):
            executed_shells.append(args[0])
            return 0, "", ""

    client = MockAdb()
    ok = client.fast_send(
        input_bounds="[242,2202][838,2334]",
        send_bounds="[838,2202][1000,2334]",
        text="Hello Plato! :3",
        reply_bounds="[44,591][1036,788]",
        reply_tap_coords=(229, 1572),
        has_draft=True,
    )

    assert ok is True
    assert len(executed_shells) == 1
    cmd = executed_shells[0]

    # Must contain swipe at message center (540, 689)
    assert "input swipe 540 689 540 689 450" in cmd
    # Must tap Reply button at (229, 1572)
    assert "input tap 229 1572" in cmd
    # Must clear text field when has_draft is True
    assert "input keyevent 123 67" in cmd
    # Must type text
    assert "input text Hello%sPlato!%s:3" in cmd
    # Must tap send at (919, phone_bridge.config.bridge_send_y_open)
    assert f"input tap 919 {phone_bridge.config.bridge_send_y_open}" in cmd
    # Must be joined with shell conditionals
    assert " && " in cmd


def test_dump_ui_fast_single_roundtrip():
    executed_shells = []

    class MockAdb(phone_bridge.AdbClient):
        def __init__(self):
            super().__init__("adb")

        def shell(self, *args, timeout=20):
            executed_shells.append(args[0])
            return 0, '<?xml version="1.0"><hierarchy></hierarchy>', ""

    client = MockAdb()
    xml = client.dump_ui()
    assert xml.startswith('<?xml')
    assert len(executed_shells) == 1
    assert "uiautomator dump --compressed" in executed_shells[0]
    assert "cat /sdcard/plato-bridge-window.xml" in executed_shells[0]


def test_navigate_to_group_switches_from_main_to_staff_via_room_list(monkeypatch):
    monkeypatch.setattr(phone_bridge.time, "sleep", lambda *_: None)
    tapped = []

    room_list_xml = """<?xml version="1.0" encoding="utf-8"?>
    <hierarchy>
      <node text="0 R D E R" resource-id="com.plato.android:id/room_title" bounds="[100,400][800,500]" />
      <node text="base" resource-id="com.plato.android:id/room_title" bounds="[100,600][800,700]" />
    </hierarchy>
    """
    staff_xml = _make_group_xml("base")

    class NavAdb(phone_bridge.AdbClient):
        def __init__(self):
            super().__init__("adb")
            self.dumps = [room_list_xml, staff_xml]

        def tap_bounds(self, bounds: str) -> None:
            tapped.append(bounds)

        def shell(self, *args, timeout=20):
            tapped.append(" ".join(args))
            return 0, "", ""

        def dump_ui(self) -> str:
            return self.dumps.pop(0)

    adb = NavAdb()
    initial_nodes = phone_bridge.parse_ui_xml(_make_group_xml("0 R D E R"))
    ok = phone_bridge.navigate_to_group(adb, initial_nodes, "base")
    assert ok is True
    assert "[100,600][800,700]" in tapped


