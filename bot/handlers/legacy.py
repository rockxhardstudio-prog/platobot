from bot.config import config
from bot.models.message import IncomingMessage
from bot.services import ratelimit
from bot.services.mvp import (
    audit, get_spam_message, set_spam_message, set_invite, set_user_mapping, valid_invite_url
)
from bot.services.plato import OutboxPlatoClient
from bot.handlers.utils import require_main, require_storage_admin
import re

plato_client = OutboxPlatoClient()

_SPAM_RE = re.compile(r"^\s*:?[ \t]*(\d+)[ \t]*\+[ \t]*(\d+)\s*$")
_SPAMSET_RE = re.compile(r"^\s*(\d+)\s+(.+?)\s*$", re.DOTALL)
_ADD_RE = re.compile(r"^\s*([^:\n][^:\n]{0,79})\s*:\s*(\d+)\s*$")


def _handle_spam(msg: IncomingMessage, args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group
    match = _SPAM_RE.fullmatch(args)
    if not match:
        return "Usage: /spam : ID + number"
    message_id, count = map(int, match.groups())
    if count <= 0 or count > config.max_spam_repetitions:
        return f"Choose a repetition count from 1 to {config.max_spam_repetitions}."
    if not ratelimit.allow(msg.user_id, "spam", config.spam_cooldown_seconds):
        return "Please wait before requesting another spam message."
    stored = get_spam_message(message_id)
    if stored is None:
        return f"No stored spam message exists for ID {message_id}."
    for _ in range(count):
        plato_client.send_message(config.main_group_id, stored)
    audit(msg.user_id, "spam_requested", str(message_id), f"count={count}; group={msg.group_id}")
    return f"Queued message {message_id} {count} time{'s' if count != 1 else ''}."


def _handle_spamset(msg: IncomingMessage, args: str) -> str:
    problem = require_storage_admin(msg)
    if problem:
        return problem
    match = _SPAMSET_RE.fullmatch(args)
    if not match:
        return "Usage: /spamset <numeric ID> <message>"
    message_id, text = int(match.group(1)), match.group(2).strip()
    if message_id <= 0 or not text:
        return "Spam ID must be positive and the message cannot be empty."
    set_spam_message(message_id, text, msg.user_id)
    return f"Saved spam message {message_id}."


def _handle_inviteset(msg: IncomingMessage, args: str) -> str:
    problem = require_storage_admin(msg)
    if problem:
        return problem
    url = args.strip()
    if not valid_invite_url(url):
        return "Please provide a valid http(s) invite URL."
    set_invite(url, msg.user_id)
    return "Invite link saved."


def _handle_add(msg: IncomingMessage, args: str) -> str:
    problem = require_storage_admin(msg)
    if problem:
        return problem
    match = _ADD_RE.fullmatch(args)
    if not match:
        return "Usage: /add username:id"
    username, mapping_id = match.group(1).strip(), int(match.group(2))
    if mapping_id <= 0:
        return "The ID must be a positive number."
    set_user_mapping(mapping_id, username, msg.user_id)
    return f"Saved ID {mapping_id} for {username}."


HANDLERS = {
    "spam": _handle_spam,
    "spamset": _handle_spamset,
    "inviteset": _handle_inviteset,
    "setinvite": _handle_inviteset,
    "sinv": _handle_inviteset,
    "add": _handle_add,
}
