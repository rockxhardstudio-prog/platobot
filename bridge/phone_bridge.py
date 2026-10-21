from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.config import config
from bridge.diagnostics.bluestacks_probe import parse_ui_xml

CHAT_INPUT_ID = "com.plato.android:id/plato_conversation_chat_box"
SEND_BUTTON_ID = "com.plato.android:id/plato_button_send"
GROUP_TITLE_ID = "com.plato.android:id/plato_addressee"
GROUP_SUBTITLE_ID = "com.plato.android:id/last_active_status"
CHAT_CONTAINER_ID = "com.plato.android:id/group_conversation_container"
CHAT_BOX_CONTAINER_ID = "com.plato.android:id/plato_container_conversation_chat_box"
MESSAGE_CONTAINER_ID = "com.plato.android:id/item_message_entire_container"
MESSAGE_HEADER_USERNAME_ID = "com.plato.android:id/message_header_user_name"
MESSAGE_HEADER_TIME_ID = "com.plato.android:id/message_header_time"

IGNORED_TEXT_IDS = {
    GROUP_TITLE_ID,
    GROUP_SUBTITLE_ID,
    "com.plato.android:id/pinned_message_text",
    "com.plato.android:id/empty_state_title",
    "com.plato.android:id/empty_state_subtitle",
}

MESSAGE_TEXT_IDS = {
    "com.plato.android:id/message_text_text",
}


@dataclass(frozen=True)
class VisibleMessage:
    message_id: str
    group_id: str
    user_id: str
    username: str
    text: str
    message_time: str = ""
    bounds: str = ""
    is_self: bool = False


def bounds_center(bounds: str) -> tuple[int, int]:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not match:
        raise ValueError(f"Unsupported bounds: {bounds}")
    left, top, right, bottom = map(int, match.groups())
    return (left + right) // 2, (top + bottom) // 2


def normalize_for_adb_input(text: str) -> str:
    from bot.utils.scifi import scifi_transliterate_to_ascii
    value = scifi_transliterate_to_ascii(text)
    value = value.encode("ascii", errors="ignore").decode("ascii")
    value = " ".join(value.splitlines()).strip()
    value = value.replace("\\", "")
    value = value.replace("%", "\\%").replace(" ", "%s")
    for char in ['"', "'", "&", "|", "<", ">", "$", "`"]:
        value = value.replace(char, "")
    value = value.replace(";", "\\;").replace("(", "\\(").replace(")", "\\)")
    return value[:900]


class AdbClient:
    def __init__(self, adb_path: str, serial: str | None = None):
        self.adb_path = adb_path
        self.serial = serial or None
        self._has_adb_keyboard: bool = False

    def check_adb_keyboard(self) -> bool:
        return self._has_adb_keyboard

    def detect_adb_keyboard(self) -> bool:
        try:
            code, stdout, _ = self.shell("pm path com.android.adbkeyboard", timeout=5)
            self._has_adb_keyboard = bool(code == 0 and "package:" in stdout)
        except Exception:
            self._has_adb_keyboard = False
        return self._has_adb_keyboard

    def run(self, *arguments: str, timeout: int = 20) -> tuple[int, str, str]:
        command = [self.adb_path]
        if self.serial:
            command.extend(["-s", self.serial])
        command.extend(arguments)
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return completed.returncode, completed.stdout.strip(), completed.stderr.strip()

    def shell(self, *arguments: str, timeout: int = 20) -> tuple[int, str, str]:
        return self.run("shell", *arguments, timeout=timeout)

    def dump_ui(self) -> str:
        code, stdout, _ = self.shell(
            "rm -f /sdcard/plato-bridge-window.xml && uiautomator dump --compressed /sdcard/plato-bridge-window.xml >/dev/null 2>&1 && cat /sdcard/plato-bridge-window.xml",
            timeout=15,
        )
        if code == 0 and stdout.lstrip().startswith("<?xml"):
            return stdout
        self.shell(
            "input keyevent 224 >/dev/null 2>&1 || true; settings delete secure enabled_accessibility_services >/dev/null 2>&1 || true; rm -f /sdcard/plato-bridge-window.xml && uiautomator dump /sdcard/plato-bridge-window.xml",
            timeout=15,
        )
        code, stdout, stderr = self.run("exec-out", "cat", "/sdcard/plato-bridge-window.xml", timeout=15)
        if code != 0 or not stdout.lstrip().startswith("<?xml"):
            raise RuntimeError(f"Could not read UI dump: {stderr or stdout}")
        return stdout

    def tap_bounds(self, bounds: str) -> None:
        x, y = bounds_center(bounds)
        self.shell("input", "tap", str(x), str(y))

    def clear_text_field(self) -> None:
        del_keys = " ".join(["67"] * 60)
        self.shell(f"input keyevent 123 {del_keys}", timeout=8)

    def type_text(self, text: str) -> None:
        safe_text = normalize_for_adb_input(text)
        if not safe_text:
            return
        self.shell("input", "text", safe_text, timeout=30)

    def fast_send(
        self,
        input_bounds: str,
        send_bounds: str,
        text: str,
        reply_bounds: str | None = None,
        reply_tap_coords: tuple[int, int] = (229, 1572),
        send_y_open: int | None = None,
        has_draft: bool = False,
    ) -> bool:
        safe_text = normalize_for_adb_input(text)
        if not safe_text:
            return False

        ix, iy = bounds_center(input_bounds)
        sx, sy = bounds_center(send_bounds)
        target_send_y = send_y_open if send_y_open is not None else getattr(config, "bridge_send_y_open", 1171)
        rep_x, rep_y = reply_tap_coords

        cmds = []
        used_reply = False
        if reply_bounds:
            try:
                rx, ry = bounds_center(reply_bounds)
                if 450 <= ry <= 2180:
                    cmds.append(
                        f"(input swipe {rx} {ry} {rx} {ry} 450 && sleep 0.15 && input tap {rep_x} {rep_y} && sleep 0.08 || true)"
                    )
                    used_reply = True
            except Exception:
                pass

        if not used_reply:
            cmds.append(f"input tap {ix} {iy}")

        if has_draft:
            del_keys = " ".join(["67"] * 60)
            cmds.append(f"input keyevent 123 {del_keys}")

        if self.check_adb_keyboard():
            import base64
            b64_msg = base64.b64encode(text.encode("utf-8")).decode("ascii")
            cmds.append(f"am broadcast -a ADB_INPUT_B64 --es msg '{b64_msg}'")
        else:
            raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
            if len(raw_lines) > 1:
                line_cmds = []
                for l in raw_lines:
                    nl = normalize_for_adb_input(l)
                    if nl:
                        line_cmds.append(f"input text {nl}")
                if line_cmds:
                    cmds.append(" && sleep 0.12 && input keyevent 66 && sleep 0.12 && ".join(line_cmds))
                else:
                    cmds.append(f"input text {safe_text}")
            else:
                cmds.append(f"input text {safe_text}")
        cmds.append(f"input tap {sx} {target_send_y}")

        full_cmd = " && ".join(cmds)
        code, stdout, stderr = self.shell(full_cmd, timeout=20)
        return code == 0


def _node_text(node: dict[str, object]) -> str:
    return str(node.get("text") or node.get("content_description") or "").strip()


def current_group(nodes: list[dict[str, object]]) -> str | None:
    for node in nodes:
        if node.get("resource_id") == GROUP_TITLE_ID:
            title = _node_text(node)
            return title or None
    return None


def _normalize_group_title(text: str | None) -> str:
    if not text:
        return ""
    s = (
        text.replace("\u039b", "a")
        .replace("\u03bb", "a")
        .replace("\u039e", "e")
        .replace("\u03be", "e")
        .replace("0", "o")
    )
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _titles_match(actual: str | None, expected: str | None) -> bool:
    if not actual or not expected:
        return False
    if actual.strip().lower() == expected.strip().lower():
        return True
    na = _normalize_group_title(actual)
    ne = _normalize_group_title(expected)
    if not na or not ne:
        return False
    if na == ne:
        return True
    if ("novablaze" in na or na == "order") and ("novablaze" in ne or ne == "order"):
        return True
    if ("staff" in na and "staff" in ne) or (ne in {"staff", "staffgroup"} and "staff" in na):
        return True
    return False


def group_id_for_title(title: str | None) -> str | None:
    if not title:
        return None
    nt = _normalize_group_title(title)
    if (
        title == config.main_group_title
        or nt == _normalize_group_title(config.main_group_title)
        or "novablaze" in nt
        or nt == "order"
    ):
        return config.main_group_id
    if (
        title == config.storage_group_title
        or nt == _normalize_group_title(config.storage_group_title)
        or "staff" in nt
    ):
        return config.storage_group_id
    return None


def _find_room_bounds(nodes: list[dict[str, object]], target_title: str) -> str | None:
    target_norm = _normalize_group_title(target_title)
    # 1. Exact or normalized direct match on group_title / room_title nodes first
    for pass_num in (1, 2):
        for node in nodes:
            rid = str(node.get("resource_id") or "")
            if pass_num == 1 and rid not in {
                "com.plato.android:id/plato_group_title",
                "com.plato.android:id/room_title",
                "",
            }:
                continue
            if rid == GROUP_TITLE_ID:
                continue
            txt = _node_text(node)
            bounds = str(node.get("bounds") or "")
            if not txt or not bounds:
                continue
            if txt == target_title or txt.lower() == target_title.strip().lower():
                return bounds
            nt = _normalize_group_title(txt)
            if nt and nt == target_norm:
                return bounds
            if ("novablaze" in target_norm or target_norm == "order") and ("novablaze" in nt or nt == "order"):
                return bounds
            if "staff" in target_norm and "staff" in nt:
                return bounds

    # 2. Fallback: if target is storage/staff, match STAFF GROUP
    if target_norm in {"staff", "staffgroup"} or "staff" in target_norm:
        for node in nodes:
            txt = _node_text(node)
            bounds = str(node.get("bounds") or "")
            nt = _normalize_group_title(txt)
            if bounds and "staff" in nt:
                return bounds
    return None


def navigate_to_group(adb: AdbClient, nodes: list[dict[str, object]], target_title: str) -> bool:
    if not target_title:
        return False
    cur = current_group(nodes)
    if cur == target_title or (
        cur is not None
        and _normalize_group_title(cur) == _normalize_group_title(target_title)
    ) or (
        cur is not None
        and "staff" in _normalize_group_title(target_title)
        and "staff" in _normalize_group_title(cur)
    ):
        return True

    if cur is not None:
        back_node = find_node(nodes, "com.plato.android:id/plato_button_back")
        if back_node and back_node.get("bounds"):
            adb.tap_bounds(str(back_node["bounds"]))
        else:
            adb.shell("input keyevent 4")
        time.sleep(0.55)
        try:
            nodes = parse_ui_xml(adb.dump_ui())
        except Exception:
            return False

    candidate = _find_room_bounds(nodes, target_title)
    if not candidate:
        # Check if we need to tap the GROUPS tab in Plato People screen
        for node in nodes:
            if (
                node.get("resource_id") == "com.plato.android:id/notification_tab_title"
                and _node_text(node).upper() == "GROUPS"
                and node.get("bounds")
            ):
                adb.tap_bounds(str(node["bounds"]))
                time.sleep(0.45)
                try:
                    nodes = parse_ui_xml(adb.dump_ui())
                    candidate = _find_room_bounds(nodes, target_title)
                except Exception:
                    pass
                break

    if not candidate:
        # Never leave Plato stranded on the room list: re-open previous or Main GC
        fallback = _find_room_bounds(nodes, cur or config.main_group_title or "0 R D E R")
        if fallback:
            adb.tap_bounds(fallback)
        return False

    adb.tap_bounds(candidate)
    time.sleep(0.55)
    try:
        verify_nodes = parse_ui_xml(adb.dump_ui())
        new_cur = current_group(verify_nodes)
        return _titles_match(new_cur, target_title)
    except Exception:
        return False


def _bounds_top(bounds: str) -> int:
    match = re.match(r"\[\d+,(\d+)\]", bounds)
    return int(match.group(1)) if match else 0


def _bounds_left(bounds: str) -> int:
    match = re.match(r"\[(\d+),", bounds)
    return int(match.group(1)) if match else 0


def _bounds_right(bounds: str) -> int:
    match = re.search(r"\]\[(\d+),\d+\]", bounds)
    return int(match.group(1)) if match else 0


def _node_index(nodes: list[dict[str, object]]) -> dict[int, dict[str, object]]:
    return {int(node["id"]): node for node in nodes if "id" in node}


def _ancestor_with_resource_id(
    node: dict[str, object],
    nodes_by_id: dict[int, dict[str, object]],
    resource_id: str,
) -> dict[str, object] | None:
    parent_id = node.get("parent_id")
    while parent_id is not None:
        parent = nodes_by_id.get(int(parent_id))
        if not parent:
            return None
        if parent.get("resource_id") == resource_id:
            return parent
        parent_id = parent.get("parent_id")
    return None


def _descendant_node(
    node: dict[str, object],
    nodes_by_id: dict[int, dict[str, object]],
    resource_id: str,
) -> dict[str, object] | None:
    pending = list(node.get("child_ids") or [])
    while pending:
        child = nodes_by_id.get(int(pending.pop(0)))
        if not child:
            continue
        if child.get("resource_id") == resource_id:
            return child
        pending.extend(child.get("child_ids") or [])
    return None


def _descendant_text(
    node: dict[str, object],
    nodes_by_id: dict[int, dict[str, object]],
    resource_id: str,
) -> str | None:
    target = _descendant_node(node, nodes_by_id, resource_id)
    return _node_text(target) if target else None


def _find_message_container(
    node: dict[str, object],
    nodes_by_id: dict[int, dict[str, object]],
) -> dict[str, object] | None:
    container = _ancestor_with_resource_id(node, nodes_by_id, MESSAGE_CONTAINER_ID)
    if container:
        return container
    curr = node
    while curr.get("parent_id") is not None:
        parent = nodes_by_id.get(int(curr["parent_id"]))
        if not parent:
            break
        if parent.get("resource_id") in {
            "com.plato.android:id/conversation_recycler_view",
            CHAT_CONTAINER_ID,
        }:
            return curr
        curr = parent
    return None


def visible_messages(
    nodes: list[dict[str, object]],
    group_id: str,
    previous_known_other_author: str = "",
) -> list[VisibleMessage]:
    messages: list[VisibleMessage] = []
    nodes_by_id = _node_index(nodes)
    last_known_other_username = previous_known_other_author or ""
    last_known_time = ""
    occurrence_counts: dict[tuple[str, str, str], int] = {}

    self_names = {
        (config.bridge_visible_username or "").lower(),
        (config.bridge_visible_user_id or "").lower(),
        "floatsystem",
    }
    for hnode in sorted(
        (n for n in nodes if n.get("resource_id") == MESSAGE_HEADER_USERNAME_ID and n.get("bounds")),
        key=lambda n: _bounds_top(str(n.get("bounds") or "")),
    ):
        htop = _bounds_top(str(hnode.get("bounds") or ""))
        htext = _node_text(hnode)
        if htop < 475 and htext and htext.lower() not in self_names:
            last_known_other_username = htext

    text_nodes = [
        node for node in nodes
        if str(node.get("resource_id") or "") in MESSAGE_TEXT_IDS
        and str(node.get("text") or "").strip()
        and str(node.get("resource_id") or "") not in IGNORED_TEXT_IDS
        and str(node.get("resource_id") or "") != CHAT_INPUT_ID
        and str(node.get("bounds") or "")
    ]
    text_nodes.sort(key=lambda n: _bounds_top(str(n.get("bounds") or "")))

    for node in text_nodes:
        text = str(node.get("text") or "").strip()
        bounds = str(node.get("bounds") or "")
        top = _bounds_top(bounds)
        if top < 475 or top > 2180:
            continue
        if text in {"CHAT", "GAMES"} or text.startswith("ONLINE"):
            continue

        container = _find_message_container(node, nodes_by_id)
        avatar = _descendant_node(container, nodes_by_id, "com.plato.android:id/message_text_framed_picture") if container else None
        av_bounds = str(avatar.get("bounds") or "") if avatar else ""
        av_left = _bounds_left(av_bounds) if av_bounds else -1

        username = _descendant_text(container, nodes_by_id, MESSAGE_HEADER_USERNAME_ID) if container else None
        message_time = _descendant_text(container, nodes_by_id, MESSAGE_HEADER_TIME_ID) if container else None

        is_self = False
        if av_left >= 700:
            is_self = True
        elif username and (username.lower() in {
            (config.bridge_visible_username or "").lower(),
            (config.bridge_visible_user_id or "").lower(),
            "floatsystem",
        }):
            is_self = True
        elif not username and av_left < 0 and _bounds_right(bounds) == 868 and _bounds_left(bounds) != 241:
            is_self = True

        if is_self:
            effective_username = config.bridge_visible_username or "floatsystem"
            user_id = config.bridge_visible_user_id or "floatsystem"
            message_time = message_time or ""
        else:
            if username:
                last_known_other_username = username
                if message_time:
                    last_known_time = message_time
            effective_username = username or last_known_other_username or "unknown"
            user_id = effective_username
            message_time = message_time or last_known_time or ""

        reply_bounds = bounds or (str(container.get("bounds")) if container and container.get("bounds") else "")

        occ_key = (user_id, message_time, text)
        occ = occurrence_counts.get(occ_key, 0) + 1
        occurrence_counts[occ_key] = occ

        stable = f"{group_id}|{user_id}|{message_time}|{text}|{occ}"
        message_id = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]
        messages.append(
            VisibleMessage(
                message_id=message_id,
                group_id=group_id,
                user_id=user_id,
                username=effective_username,
                text=text,
                message_time=message_time or "",
                bounds=reply_bounds,
                is_self=is_self,
            )
        )
    return messages


def find_node(nodes: list[dict[str, object]], resource_id: str) -> dict[str, object] | None:
    return next((node for node in nodes if node.get("resource_id") == resource_id), None)


def input_has_draft(nodes: list[dict[str, object]]) -> bool:
    return bool(input_draft_text(nodes))


def input_draft_text(nodes: list[dict[str, object]]) -> str:
    input_node = find_node(nodes, CHAT_INPUT_ID)
    if not input_node:
        return ""
    text = str(input_node.get("text") or "").strip()
    return text if text and not text.startswith("Say hello") else ""


def visible_text_equivalent(left: str, right: str) -> bool:
    def _clean(s: str) -> str:
        s = s.encode("ascii", errors="ignore").decode("ascii")
        s = " ".join(s.split()).strip().lower()
        for char in ['"', "'", "\\", "%", "&", "|", "<", ">", "(", ")", ";", ":", "-", "!", "."]:
            s = s.replace(char, "")
        return " ".join(s.split())
    return _clean(left) == _clean(right)


def already_visible_from_self(nodes: list[dict[str, object]], group_id: str, text: str) -> bool:
    for message in visible_messages(nodes, group_id):
        if message.user_id == config.bridge_visible_user_id and visible_text_equivalent(message.text, text):
            return True
    return False


def post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def get_json(url: str) -> list[dict[str, object]]:
    with urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8") or "[]")


def send_visible_message(adb: AdbClient, nodes: list[dict[str, object]], text: str) -> bool:
    input_node = find_node(nodes, CHAT_INPUT_ID)
    send_node = find_node(nodes, SEND_BUTTON_ID)
    if not input_node or not send_node:
        return False

    if hasattr(adb, "fast_send"):
        return adb.fast_send(
            str(input_node["bounds"]),
            str(send_node["bounds"]),
            text,
            has_draft=input_has_draft(nodes),
        )

    adb.tap_bounds(str(input_node["bounds"]))
    time.sleep(0.05)
    adb.clear_text_field()
    time.sleep(0.05)
    adb.type_text(text)
    time.sleep(0.05)
    adb.tap_bounds(str(send_node["bounds"]))
    time.sleep(0.05)
    return True


def bridge_once(adb: AdbClient, backend_url: str, seen: set[str]) -> dict[str, object]:
    nodes = parse_ui_xml(adb.dump_ui())
    title = current_group(nodes)
    group_id = group_id_for_title(title)
    result: dict[str, object] = {"title": title, "group_id": group_id, "inbox": 0, "outbox": 0}
    if not group_id:
        return result

    for message in visible_messages(nodes, group_id):
        if message.message_id in seen:
            continue
        seen.add(message.message_id)
        payload = {
            "message_id": message.message_id,
            "group_id": message.group_id,
            "user_id": message.user_id,
            "username": message.username,
            "text": message.text,
            "is_self": message.is_self,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        post_json(f"{backend_url.rstrip('/')}/inbox", payload)
        result["inbox"] = int(result["inbox"]) + 1

    outbox = get_json(f"{backend_url.rstrip('/')}/outbox?group_id={group_id}&claim=true&limit=1")
    if not outbox:
        return result

    item = outbox[0]
    text = str(item["text"])

    if already_visible_from_self(nodes, group_id, text):
        post_json(f"{backend_url.rstrip('/')}/outbox/{item['id']}/ack", {})
        result["outbox"] = 1
        return result

    if send_visible_message(adb, nodes, text):
        post_json(f"{backend_url.rstrip('/')}/outbox/{item['id']}/ack", {})
        result["outbox"] = 1
    else:
        post_json(f"{backend_url.rstrip('/')}/outbox/{item['id']}/fail", {"reason": "send_visible_message failed"})

    return result


def run_concurrent_bridge(
    adb: AdbClient,
    backend_url: str,
    seen: set[str],
    interval: float = 0.02,
) -> None:
    stop_event = threading.Event()
    wake_sender = threading.Event()
    is_sending = threading.Event()
    shared_state: dict[str, object] = {
        "group_id": None,
        "title": None,
        "input_bounds": None,
        "send_bounds": None,
        "last_reply_bounds": None,
        "last_other_author": "",
        "has_draft": False,
        "nodes": [],
    }
    state_lock = threading.Lock()
    chat_history: list[tuple[str, str, str, bool]] = []
    last_heartbeat_ts = 0.0

    def align_and_extract_new(current_msgs: list[VisibleMessage]) -> list[VisibleMessage]:
        nonlocal chat_history
        current_signatures = [
            (m.user_id, m.message_time, m.text, m.is_self) for m in current_msgs
        ]
        if not current_signatures:
            return []

        if not chat_history:
            chat_history = list(current_signatures)[-150:]
            return []

        for i in range(len(chat_history) - len(current_signatures) + 1):
            if chat_history[i : i + len(current_signatures)] == current_signatures:
                return []

        max_k = min(len(chat_history), len(current_signatures))
        for k in range(max_k, 0, -1):
            if chat_history[-k:] == current_signatures[:k]:
                new_msgs = current_msgs[k:]
                chat_history.extend(current_signatures[k:])
                if len(chat_history) > 300:
                    chat_history[:] = chat_history[-300:]
                return new_msgs

        for pos in range(len(current_signatures) - 1, -1, -1):
            for length in range(min(len(chat_history), pos + 1), 0, -1):
                if chat_history[-length:] == current_signatures[pos - length + 1 : pos + 1]:
                    new_msgs = current_msgs[pos + 1 :]
                    chat_history.extend(current_signatures[pos + 1 :])
                    if len(chat_history) > 300:
                        chat_history[:] = chat_history[-300:]
                    return new_msgs

        new_msgs = []
        for m, sig in zip(current_msgs, current_signatures):
            already_in_hist = any(h[0] == sig[0] and h[2] == sig[2] for h in chat_history)
            if not already_in_hist:
                new_msgs.append(m)
        chat_history.extend(current_signatures)
        if len(chat_history) > 300:
            chat_history[:] = chat_history[-300:]
        return new_msgs

    def reader_loop():
        nonlocal chat_history, last_heartbeat_ts
        while not stop_event.is_set():
            if is_sending.is_set():
                time.sleep(0.02)
                continue
            try:
                xml_dump = adb.dump_ui()
                nodes = parse_ui_xml(xml_dump)
                title = current_group(nodes)
                group_id = group_id_for_title(title)

                input_node = find_node(nodes, CHAT_INPUT_ID)
                send_node = find_node(nodes, SEND_BUTTON_ID)
                draft_present = input_has_draft(nodes)

                with state_lock:
                    prev_group_id = shared_state["group_id"]
                    if prev_group_id and group_id and prev_group_id != group_id:
                        chat_history.clear()
                        shared_state["last_reply_bounds"] = None
                    shared_state["group_id"] = group_id
                    shared_state["title"] = title
                    shared_state["nodes"] = nodes
                    shared_state["has_draft"] = draft_present
                    if input_node:
                        shared_state["input_bounds"] = str(input_node["bounds"])
                    if send_node:
                        shared_state["send_bounds"] = str(send_node["bounds"])

                ingested = 0
                if group_id:
                    with state_lock:
                        prev_author = str(shared_state.get("last_other_author") or "")
                    all_vis = visible_messages(nodes, group_id, previous_known_other_author=prev_author)
                    for vm in all_vis:
                        if not vm.is_self and vm.user_id and vm.user_id != "unknown":
                            prev_author = vm.user_id
                    with state_lock:
                        shared_state["last_other_author"] = prev_author
                    new_msgs = align_and_extract_new(all_vis)
                    for message in new_msgs:
                        if message.message_id in seen:
                            continue
                        seen.add(message.message_id)
                        if not message.is_self and message.bounds:
                            with state_lock:
                                shared_state["last_reply_bounds"] = message.bounds
                        payload = {
                            "message_id": message.message_id,
                            "group_id": message.group_id,
                            "user_id": message.user_id,
                            "username": message.username,
                            "text": message.text,
                            "is_self": message.is_self,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        post_json(f"{backend_url.rstrip('/')}/inbox", payload)
                        ingested += 1
                    if ingested > 0:
                        wake_sender.set()

                now_ts = time.time()
                on_room_list = (title is None) and (
                    find_node(nodes, "com.plato.android:id/groups_recycler_view") is not None
                    or find_node(nodes, "com.plato.android:id/plato_home_people_pager") is not None
                )
                if ingested > 0 or on_room_list or (now_ts - last_heartbeat_ts >= 1.5):
                    last_heartbeat_ts = now_ts
                    try:
                        bstate = post_json(
                            f"{backend_url.rstrip('/')}/bridge-state/heartbeat",
                            {"current_group_id": group_id, "current_group_title": title},
                        )
                        target_gid = str(bstate.get("target_group_id") or "main")
                        target_title = str(bstate.get("target_group_title") or config.main_group_title or "-» NOVΛ ⟡ BLΛZΞ «-")
                        nav_pending = bool(bstate.get("navigation_pending"))

                        if target_gid == "off":
                            if nav_pending and title is not None:
                                pending_here = get_json(
                                    f"{backend_url.rstrip('/')}/outbox?group_id={group_id}&claim=false&limit=1"
                                ) if group_id else []
                                if not pending_here:
                                    is_sending.set()
                                    try:
                                        back_node = find_node(nodes, "com.plato.android:id/plato_button_back")
                                        if back_node and back_node.get("bounds"):
                                            adb.tap_bounds(str(back_node["bounds"]))
                                        else:
                                            adb.shell("input keyevent 4")
                                        with state_lock:
                                            chat_history.clear()
                                            shared_state["last_reply_bounds"] = None
                                        post_json(
                                            f"{backend_url.rstrip('/')}/bridge-state/heartbeat",
                                            {
                                                "current_group_id": None,
                                                "current_group_title": None,
                                                "ack_navigation": True,
                                            },
                                        )
                                    finally:
                                        is_sending.clear()
                            elif nav_pending and title is None:
                                post_json(
                                    f"{backend_url.rstrip('/')}/bridge-state/heartbeat",
                                    {
                                        "current_group_id": None,
                                        "current_group_title": None,
                                        "ack_navigation": True,
                                    },
                                )
                            elif not nav_pending and title is not None:
                                # User manually entered a GC on the phone! Never kick user out; resume focus.
                                resumed_gid = group_id or "main"
                                post_json(
                                    f"{backend_url.rstrip('/')}/bridge-state/resume",
                                    {"group_id": resumed_gid, "group_title": title},
                                )
                                post_json(
                                    f"{backend_url.rstrip('/')}/bridge-state/heartbeat",
                                    {
                                        "current_group_id": resumed_gid,
                                        "current_group_title": title,
                                        "ack_navigation": True,
                                    },
                                )
                        elif (nav_pending and not _titles_match(title, target_title)) or on_room_list:
                            pending_here = get_json(
                                f"{backend_url.rstrip('/')}/outbox?group_id={group_id}&claim=false&limit=1"
                            ) if group_id else []
                            if not pending_here:
                                is_sending.set()
                                try:
                                    navigate_to_group(adb, nodes, target_title)
                                    with state_lock:
                                        chat_history.clear()
                                        shared_state["last_reply_bounds"] = None
                                    post_json(
                                        f"{backend_url.rstrip('/')}/bridge-state/heartbeat",
                                        {
                                            "current_group_id": group_id,
                                            "current_group_title": title,
                                            "ack_navigation": True,
                                        },
                                    )
                                finally:
                                    is_sending.clear()
                        elif nav_pending and _titles_match(title, target_title):
                            post_json(
                                f"{backend_url.rstrip('/')}/bridge-state/heartbeat",
                                {
                                    "current_group_id": group_id,
                                    "current_group_title": title,
                                    "ack_navigation": True,
                                },
                            )
                    except Exception:
                        pass

            except Exception as error:
                print(f"[bridge reader error] {error}", file=sys.stderr, flush=True)

            time.sleep(max(interval, 0.02))

    def sender_loop():
        nonlocal chat_history
        while not stop_event.is_set():
            try:
                with state_lock:
                    group_id = shared_state["group_id"]
                    input_bounds = shared_state["input_bounds"]
                    send_bounds = shared_state["send_bounds"]
                    reply_bounds = shared_state.get("last_reply_bounds")
                    has_draft = bool(shared_state.get("has_draft"))
                    nodes = list(shared_state["nodes"])

                if not group_id:
                    wake_sender.wait(timeout=0.1)
                    wake_sender.clear()
                    continue

                outbox = get_json(f"{backend_url.rstrip('/')}/outbox?group_id={group_id}&claim=true&limit=1")
                if not outbox:
                    wake_sender.wait(timeout=0.1)
                    wake_sender.clear()
                    continue

                item = outbox[0]
                text = str(item["text"])

                is_sending.set()
                success = False
                try:
                    if input_bounds and send_bounds:
                        success = adb.fast_send(
                            input_bounds=str(input_bounds),
                            send_bounds=str(send_bounds),
                            text=text,
                            reply_bounds=str(reply_bounds) if reply_bounds else None,
                            has_draft=has_draft,
                        )
                        if reply_bounds:
                            with state_lock:
                                shared_state["last_reply_bounds"] = None
                        if has_draft:
                            with state_lock:
                                shared_state["has_draft"] = False
                    elif nodes:
                        success = send_visible_message(adb, nodes, text)
                except Exception as send_err:
                    print(f"[bridge send exception] {send_err}", file=sys.stderr, flush=True)
                    success = False
                finally:
                    is_sending.clear()

                if success:
                    post_json(f"{backend_url.rstrip('/')}/outbox/{item['id']}/ack", {})
                    bot_user = config.bridge_visible_user_id or "floatsystem"
                    with state_lock:
                        chat_history.append((bot_user, "", text, True))
                        if len(chat_history) > 300:
                            chat_history[:] = chat_history[-300:]
                    wake_sender.set()
                else:
                    post_json(f"{backend_url.rstrip('/')}/outbox/{item['id']}/fail", {"reason": "send failed"})
                    time.sleep(0.3)

            except Exception as error:
                print(f"[bridge sender error] {error}", file=sys.stderr, flush=True)
                time.sleep(0.3)

    reader_t = threading.Thread(target=reader_loop, daemon=True, name="BridgeReader")
    sender_t = threading.Thread(target=sender_loop, daemon=True, name="BridgeSender")

    reader_t.start()
    sender_t.start()

    print(json.dumps({"status": "running_concurrent", "device": adb.serial, "backend": backend_url}), flush=True)

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        stop_event.set()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Plato USB phone bridge")
    parser.add_argument("--adb", default=config.bridge_adb_path)
    parser.add_argument("--serial", default=config.bridge_device_serial or None)
    parser.add_argument("--backend", default=config.bridge_backend_url)
    parser.add_argument("--once", action="store_true", help="Run one read/send pass and exit")
    parser.add_argument("--interval", type=float, default=0.1)
    args = parser.parse_args()

    if not Path(args.adb).is_file():
        print(f"ADB not found: {args.adb}", file=sys.stderr)
        return 2
    if not config.main_group_id or not config.storage_group_id:
        print("Set MAIN_GROUP_ID and STORAGE_GROUP_ID before running the bridge.", file=sys.stderr)
        return 2

    adb = AdbClient(args.adb, args.serial)
    adb.detect_adb_keyboard()
    seen: set[str] = set()

    if args.once:
        status = bridge_once(adb, args.backend, seen)
        print(json.dumps(status), flush=True)
        return 0

    run_concurrent_bridge(adb, args.backend, seen, interval=args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
