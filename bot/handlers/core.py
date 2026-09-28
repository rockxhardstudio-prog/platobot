from bot.config import config
from bot.models.message import IncomingMessage
from bot.services.mvp import activity_summary, get_invite
from bot.services.community import get_info, get_announcement
from bot.handlers.utils import require_main


COMMAND_HELP = {
    "info": "/info - View community and server information.",
    "invite": "/invite - Get the official group invite link.",
    "summary": "/summary - View today's active members and chat stats.",
    "announce": "/announce - View current server announcements.",
    "events": "/events - List upcoming community events.",
    "rules": "/rules - View community rules.",
    "tourney": "/tourney - View details and status of active tournament.",
    "register": "/register - Register for the active tournament (FCFS).",
    "unregister": "/unregister - Leave the active tournament.",
    "participants": "/participants - View registered participants and waitlist.",
    "roast": "/roast @user - Send a playful roast to a user.",
    "flirt": "/flirt @user - Send a flirtatious pickup line to a user.",
    "bully": "/bully @user - Playfully tease a user.",
    "ship": "/ship @u1 @u2 - Calculate compatibility between two users.",
    "rate": "/rate @user - Rate a user from 1 to 10.",
}


def _handle_help(msg: IncomingMessage, args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group
    
    cat = args.strip().lower()
    if not cat:
        return "🤖 BOT HELP\n/help core\n/help community\n/help tourney\n/help fun"
        
    if cat == "core":
        return "CORE COMMANDS:\n/info\n/invite\n/summary\n/announce"
    if cat == "community":
        return "COMMUNITY COMMANDS:\n/events\n/rules"
    if cat == "tourney":
        return "TOURNEY COMMANDS:\n/tourney\n/register\n/unregister\n/participants"
    if cat == "fun":
        return "FUN COMMANDS:\n/roast @user\n/flirt @user\n/bully @user\n/ship @u1 @u2\n/rate @user"
        
    clean_cat = cat.lstrip("/")
    if clean_cat in COMMAND_HELP:
        return f"📖 {COMMAND_HELP[clean_cat]}"
        
    return "Unknown category or command. Type /help to see all categories."

def _handle_info(msg: IncomingMessage, _args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group
    info = get_info()
    return info if info else "No community info has been set yet."

def _handle_invite(msg: IncomingMessage, _args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group
    return get_invite() or "No invite link has been configured yet."

def _handle_summary(msg: IncomingMessage, _args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group
    total, active, ranked, date_label = activity_summary(config.main_group_id)
    lines = ["📊 DAILY SUMMARY", date_label, "", f"👥 Active members: {active}", f"💬 Total messages: {total}"]
    if ranked:
        lines.extend(["", "Most active:"])
        lines.extend(f"{index}. {username} — {count} messages" for index, (username, count) in enumerate(ranked[:5], 1))
    return "\n".join(lines)

def _handle_announce(msg: IncomingMessage, _args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group
    ann = get_announcement()
    return f"📢 {ann}" if ann else "No active announcements."

HANDLERS = {
    "help": _handle_help,
    "info": _handle_info,
    "invite": _handle_invite,
    "summary": _handle_summary,
    "announce": _handle_announce,
}
