import re
import time
from datetime import datetime, timezone

from bot.config import config
from bot.database.db import get_conn
from bot.handlers import HANDLERS
from bot.handlers.admin import handle_interactive_session
from bot.models.message import IncomingMessage
from bot.services import dedup, identity, moderation, mvp, session, tournament
from bot.services.plato import OutboxPlatoClient
from bot.utils.text import chunk_text

plato_client = OutboxPlatoClient()

_user_command_cooldown: dict[tuple[str, str], float] = {}
_user_command_warned: dict[tuple[str, str], bool] = {}

PUBLIC_COOLDOWN_COMMANDS = {
    "help", "info", "rules", "socials", "profile", "rank", "leaderboard",
    "ship", "roast", "flirt", "bully", "tourney", "tourneyinfo", "trules",
    "winners", "core", "fun", "rate",
}

ALIASES = {
    "h": "help",
    "t": "tourneyinfo",
    "reg": "register",
    "unreg": "unregister",
    "lb": "leaderboard",
    "top": "leaderboard",
    "p": "profile",
    "r": "rank",
    "wl": "winners",
    "sum": "summary",
    "ah": "adminhelp",
    "sm": "summon",
    "ret": "return",
    "st": "status",
    "cfg": "config",
    "tc": "createtourney",
    "createtour": "createtourney",
    "ga": "createga",
}


def _upsert_user(msg: IncomingMessage) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO users (user_id, username) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username",
        (msg.user_id, msg.username),
    )
    is_perm_owner = msg.user_id.strip().lower() in mvp.PERMANENT_OWNERS
    in_prod_staff_gc = (
        bool(config.storage_group_id)
        and msg.group_id == config.storage_group_id
        and config.admin_ids != {"admin"}
        and msg.user_id.strip().lower() != "unknown"
    )
    default_role = "owner" if is_perm_owner else ("mod" if in_prod_staff_gc else "user")
    conn.execute("INSERT OR IGNORE INTO permissions (user_id, role) VALUES (?, ?)", (msg.user_id, default_role))
    if is_perm_owner:
        conn.execute("UPDATE permissions SET role='owner' WHERE LOWER(user_id)=LOWER(?)", (msg.user_id,))
    elif in_prod_staff_gc:
        conn.execute(
            "UPDATE permissions SET role='mod' WHERE LOWER(user_id)=LOWER(?) AND role='user'",
            (msg.user_id,),
        )
    conn.commit()


def _is_banned(user_id: str) -> bool:
    row = get_conn().execute("SELECT role FROM permissions WHERE user_id=?", (user_id,)).fetchone()
    return bool(row and row["role"] == "banned")


def _normalized_timestamp(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return datetime.now(timezone.utc).isoformat()


def _log_message(msg: IncomingMessage) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO messages (message_id, group_id, user_id, username, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (msg.message_id, msg.group_id, msg.user_id, msg.username, msg.text, _normalized_timestamp(msg.timestamp)),
    )
    conn.commit()


def _log_command(msg: IncomingMessage, command: str, args: str, result: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO command_log (user_id, group_id, command, args, result) VALUES (?, ?, ?, ?, ?)",
        (msg.user_id, msg.group_id, command, args, result),
    )
    conn.commit()


def _in_main(msg: IncomingMessage) -> bool:
    return bool(config.main_group_id) and msg.group_id == config.main_group_id


def _parse_command(text: str) -> tuple[str, str] | None:
    stripped = text.strip()
    match = re.match(r"^/([A-Za-z0-9_]+)(?:@([A-Za-z0-9_]+))?(?:[ \t\r\n]+(.*)|(:.*)|$)", stripped, re.DOTALL)
    if not match:
        return None
    cmd = match.group(1).lower()
    bot_target = match.group(2)
    if bot_target:
        bot_names = {
            "floatsystem",
            (config.bridge_visible_username or "").lower(),
            (config.bridge_visible_user_id or "").lower(),
            (config.bot_plato_user_id or "").lower(),
        }
        bot_names = {b for b in bot_names if b}
        if bot_target.lower() not in bot_names:
            return None
    args = (match.group(3) if match.group(3) is not None else match.group(4)) or ""
    return (cmd, args)


def handle_message(msg: IncomingMessage) -> str | None:
    if msg.is_self or (config.bot_plato_user_id and msg.user_id == config.bot_plato_user_id):
        return None
    if dedup.already_processed(msg.message_id):
        return None
    dedup.mark_processed(msg.message_id)
    _upsert_user(msg)
    if _is_banned(msg.user_id):
        return None
    lvl_msg: str | None = None
    queued_warn_msg: str | None = None
    if _in_main(msg):
        _log_message(msg)
        tournament.touch_player_activity(msg.user_id, msg.username)
        queued_warn_msg = moderation.pop_pending_warnings(msg.user_id, msg.username)
        if queued_warn_msg:
            for chunk in chunk_text(queued_warn_msg, limit=256):
                plato_client.send_message(msg.group_id, chunk)
        sentinel_reply = moderation.check_message(msg)
        if sentinel_reply:
            for chunk in chunk_text(sentinel_reply, limit=256):
                plato_client.send_message(msg.group_id, chunk)
            return sentinel_reply
        xp_res = identity.process_message_xp(msg)
        if xp_res and xp_res.get("leveled_up"):
            lvl_msg = (
                f"✦ PROMOTION // @{xp_res['username']} ✦\n"
                f"➥ You leveled up to Level {xp_res['new_level']} [{xp_res['new_rank']}]!\n"
                f"➥ ▰▰▰▰▰▰▰▰ Matrix synchronized."
            )
            plato_client.send_message(msg.group_id, lvl_msg)

    sess = session.get_session(msg.user_id)
    if sess:
        response = handle_interactive_session(msg, sess)
        if response:
            for chunk in chunk_text(response, limit=256):
                plato_client.send_message(msg.group_id, chunk)
        return response

    parsed = _parse_command(msg.text)
    if not parsed:
        raw_text = (msg.text or "").strip()
        low_text = raw_text.lower()
        bot_names = {
            "zeno",
            "floatsystem",
            (config.bridge_visible_username or "").lower(),
            (config.bridge_visible_user_id or "").lower(),
            (config.bot_plato_user_id or "").lower(),
        }
        bot_names = {b for b in bot_names if b}

        is_ai_mention = any(f"@{b}" in low_text for b in bot_names) or any(
            re.match(rf"^{b}\b[,:\s]+", low_text) for b in bot_names
        )

        if is_ai_mention:
            clean_prompt = raw_text
            for b in bot_names:
                clean_prompt = re.sub(rf"@?{re.escape(b)}[,:\s]*", "", clean_prompt, flags=re.IGNORECASE).strip()
            if not clean_prompt:
                clean_prompt = "Hello!"
            from bot.services import ai
            ai_reply = ai.generate_ai_response(msg.user_id, msg.username, clean_prompt)
            if ai_reply:
                for chunk in chunk_text(ai_reply, limit=256):
                    plato_client.send_message(msg.group_id, chunk)
                _log_command(msg, "ai", clean_prompt, ai_reply)
                return ai_reply

        auto_enabled = config.auto_response_enabled or mvp.get_config_value("auto_response") == "true"
        if auto_enabled:
            from bot.services import autoresponse
            auto_reply = autoresponse.check_auto_response(msg.user_id, msg.username, msg.group_id, raw_text)
            if auto_reply:
                for chunk in chunk_text(auto_reply, limit=256):
                    plato_client.send_message(msg.group_id, chunk)
                _log_command(msg, "autoresponse", raw_text, auto_reply)
                return auto_reply

        return queued_warn_msg or lvl_msg

    command, args = parsed
    command = ALIASES.get(command, command)

    handler = HANDLERS.get(command)
    if handler is None:
        now = time.time()
        inv_key = (msg.user_id, "_invalid_cmd")
        if now - _user_command_cooldown.get(inv_key, 0.0) < 5.0:
            return None
        _user_command_cooldown[inv_key] = now
        if msg.group_id == config.storage_group_id:
            inv_reply = f"✘ Invalid command '/{command}'. Use /ah (admin help) or /help (/h) to see commands."
        else:
            inv_reply = f"✘ Invalid command '/{command}'. Use /help or /h to see available commands."
        plato_client.send_message(msg.group_id, inv_reply)
        _log_command(msg, command, args.strip(), inv_reply)
        return inv_reply

    now = time.time()
    user_key = (msg.user_id, command)
    last_time = _user_command_cooldown.get(user_key, 0.0)
    if command in PUBLIC_COOLDOWN_COMMANDS and (now - last_time < 10.0):
        if not _user_command_warned.get(user_key, False):
            _user_command_warned[user_key] = True
            user_mention = f"@{msg.username}" if msg.username and msg.username != "unknown" else "bro"
            spam_reply = f"Chill {user_mention}, response was already sent to you! Please check above -.-"
            plato_client.send_message(msg.group_id, spam_reply)
            _log_command(msg, command, args.strip(), spam_reply)
            return spam_reply
        return None

    _user_command_cooldown[user_key] = now
    _user_command_warned[user_key] = False

    response = handler(msg, args)
    _log_command(msg, command, args.strip(), response)

    if response:
        for chunk in chunk_text(response, limit=256):
            plato_client.send_message(msg.group_id, chunk)

    return response
