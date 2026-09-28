from bot.handlers.core import HANDLERS as CORE_HANDLERS
from bot.handlers.community import HANDLERS as COMMUNITY_HANDLERS
from bot.handlers.fun import HANDLERS as FUN_HANDLERS
from bot.handlers.admin import HANDLERS as ADMIN_HANDLERS
from bot.handlers.legacy import HANDLERS as LEGACY_HANDLERS

HANDLERS = {
    **CORE_HANDLERS,
    **COMMUNITY_HANDLERS,
    **FUN_HANDLERS,
    **ADMIN_HANDLERS,
    **LEGACY_HANDLERS,
}
