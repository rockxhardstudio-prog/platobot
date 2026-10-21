from bot.config import config
from bot.models.message import IncomingMessage
from bot.services.mvp import is_admin, is_owner, is_staff


def in_main(msg: IncomingMessage) -> bool:
    return bool(config.main_group_id) and msg.group_id == config.main_group_id


def in_storage(msg: IncomingMessage) -> bool:
    return bool(config.storage_group_id) and msg.group_id == config.storage_group_id


def require_main(msg: IncomingMessage) -> str | None:
    return None if in_main(msg) else "This command is available only in the Main Group."


def require_storage_staff(msg: IncomingMessage) -> str | None:
    if not in_storage(msg):
        return "This command is staff-only and belongs in the Staff GC."
    if not is_staff(msg.user_id):
        return "Only authorized staff (mod/admin/owner) can use this command."
    return None


def require_storage_admin(msg: IncomingMessage) -> str | None:
    if not in_storage(msg):
        return "This configuration command is available only in the Storage Group."
    if not is_admin(msg.user_id):
        return "Only a bot admin can change Storage Group settings."
    return None


def require_storage_owner(msg: IncomingMessage) -> str | None:
    if not in_storage(msg):
        return "This command is available only in the Staff GC."
    if not is_owner(msg.user_id):
        return "Only a bot owner can use this command."
    return None


def require_any_group_admin(msg: IncomingMessage) -> str | None:
    if not (in_main(msg) or in_storage(msg)):
        return "This command is available only in configured bot groups."
    if in_storage(msg) and (is_staff(msg.user_id) or msg.user_id == "unknown"):
        return None
    if not is_staff(msg.user_id):
        return "Only a bot staff member (mod/admin/owner) can summon or return the bot."
    return None
