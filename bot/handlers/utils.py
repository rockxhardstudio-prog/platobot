from bot.config import config
from bot.models.message import IncomingMessage
from bot.services.mvp import is_admin

def in_main(msg: IncomingMessage) -> bool:
    return bool(config.main_group_id) and msg.group_id == config.main_group_id

def in_storage(msg: IncomingMessage) -> bool:
    return bool(config.storage_group_id) and msg.group_id == config.storage_group_id

def require_main(msg: IncomingMessage) -> str | None:
    return None if in_main(msg) else "This command is available only in the Main Group."

def require_storage_admin(msg: IncomingMessage) -> str | None:
    if not in_storage(msg):
        return "This configuration command is available only in the Storage Group."
    if not is_admin(msg.user_id):
        return "Only a bot admin can change Storage Group settings."
    return None
