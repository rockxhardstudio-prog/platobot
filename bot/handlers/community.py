from bot.handlers.utils import require_main
from bot.models.message import IncomingMessage
from bot.services import events, tournament
from bot.services.community import get_rules


def _handle_tourney(msg: IncomingMessage, _args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group

    tourney = tournament.get_active_tournament()
    if not tourney:
        return "No tournament is currently active."

    lines = [
        f"🏆 {tourney['name']} [{tourney['status'].upper()}]",
        f"Game: {tourney['game'] or 'TBD'}",
        f"Date: {tourney['event_date'] or 'TBD'} {tourney['event_time'] or ''}".strip(),
        f"Reg: {tourney['registration_time'] or 'TBD'}",
        f"Slots: {tourney['max_slots'] or 'Unlimited'}",
    ]
    if tourney["prize_info"]:
        lines.append(f"Prize: {tourney['prize_info']}")

    lines.append("(Use /rules or ask an admin for description)")
    return "\n".join(lines)


def _handle_events(msg: IncomingMessage, _args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group

    upcoming = events.get_upcoming_events()
    if not upcoming:
        return "No upcoming events scheduled."

    lines = ["📅 Upcoming Events:"]
    for e in upcoming:
        lines.append(f"• {e['name']} ({e['event_date'] or 'TBD'})")
        if e["description"]:
            lines.append(f"  {e['description']}")

    return "\n".join(lines)


def _handle_rules(msg: IncomingMessage, _args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group

    rules = get_rules()
    return rules if rules else "No community rules have been set yet."


def _handle_register(msg: IncomingMessage, args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group

    if args.strip():
        return "Usage: just /register (your Plato identity is used automatically)."

    return tournament.register_user(msg.user_id, msg.username, None)


def _handle_unregister(msg: IncomingMessage, _args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group

    try:
        return tournament.unregister_user(msg.user_id, msg.username)
    except TypeError:
        return tournament.unregister_user(msg.user_id)


HANDLERS = {
    "tourney": _handle_tourney,
    "events": _handle_events,
    "rules": _handle_rules,
    "register": _handle_register,
    "unregister": _handle_unregister,
}
