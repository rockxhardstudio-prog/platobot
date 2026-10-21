from bot.handlers.utils import in_main, in_storage, require_main
from bot.models.message import IncomingMessage
from bot.services import events, tournament
from bot.services.community import get_rules, get_tourney_rules
from bot.utils.scifi import (
    LINE_DIVIDER,
    to_small_caps,
    render_progress_bar,
    ICON_SPARKLE,
    ICON_STAR,
    ICON_ARROW,
    ICON_BRANCH,
    ICON_CROWN,
)


def _handle_tourney(msg: IncomingMessage, _args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group

    tourney = tournament.get_active_tournament()
    if not tourney:
        return "No tournament is currently active."

    t_dict = dict(tourney)
    parts = []
    if t_dict.get("id"):
        parts = tournament.get_participants()
    slots_val = t_dict.get("max_slots")
    slots_str = str(slots_val) if slots_val is not None else "Unlimited"
    slot_bar_line = ""
    if slots_val:
        bar = render_progress_bar(len(parts), int(slots_val), width=8)
        slot_bar_line = f"Slots: {bar} [{len(parts)}/{slots_str}]"
    else:
        slot_bar_line = f"Slots: {slots_str}"

    lines = [
        f"✦ {to_small_caps('ARENA')} // {t_dict.get('name', 'Tournament')} [{str(t_dict.get('status', '')).upper()}] ✦",
        f"Game: {t_dict.get('game') or 'TBD'}",
        f"Date: {t_dict.get('event_date') or 'TBD'} {t_dict.get('event_time') or ''}".strip(),
        f"Reg: {t_dict.get('registration_time') or 'TBD'}",
        slot_bar_line,
    ]
    if t_dict.get("prize_info"):
        lines.append(f"Prize: {t_dict['prize_info']}")

    lines.append("(Use /rules or ask an admin for description)")
    return "\n".join(lines)


def _handle_events(msg: IncomingMessage, _args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group

    upcoming = events.get_upcoming_events()
    if not upcoming:
        return "No upcoming events scheduled."

    lines = ["✦ Upcoming Operations ✦"]
    for e in upcoming:
        lines.append(f"➤ {e['name']} ({e['event_date'] or 'TBD'})")
        if e.get("description"):
            lines.append(f"  ➥ {e['description']}")

    return "\n".join(lines)


def _handle_rules(msg: IncomingMessage, _args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group

    rules = get_rules()
    if not rules:
        return "No community rules have been set yet."
    return rules


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


def _handle_trules(msg: IncomingMessage, _args: str) -> str:
    if not (in_main(msg) or in_storage(msg)):
        return require_main(msg) or ""
    tr = get_tourney_rules()
    if not tr:
        return "No tournament or giveaway rules have been set yet."
    return f"📜 TOURNEY / GIVEAWAY RULES\n{tr}"


def _handle_winners(msg: IncomingMessage, _args: str) -> str:
    if not (in_main(msg) or in_storage(msg)):
        return require_main(msg) or ""
    winners = tournament.get_winners()
    return tournament.format_winners_list(winners, header="🜲 WINNERS LIST")


def _handle_iwon(msg: IncomingMessage, _args: str) -> str:
    if not (in_main(msg) or in_storage(msg)):
        return require_main(msg) or ""
    _ok, text = tournament.record_match_win(msg.user_id, msg.username)
    return text


def _handle_matches(msg: IncomingMessage, _args: str) -> str:
    if not (in_main(msg) or in_storage(msg)):
        return require_main(msg) or ""
    return tournament.get_current_matches_text()


def _handle_mymatch(msg: IncomingMessage, _args: str) -> str:
    if not (in_main(msg) or in_storage(msg)):
        return require_main(msg) or ""
    return tournament.get_my_match_text(msg.user_id, msg.username)


def _handle_reportissue(msg: IncomingMessage, args: str) -> str:
    if not (in_main(msg) or in_storage(msg)):
        return require_main(msg) or ""
    reason = args.strip() or "My opponent is AFK / not responding"
    return tournament.report_match_issue(msg.user_id, msg.username, reason)


HANDLERS = {
    "tourney": _handle_tourney,
    "tourneyinfo": _handle_tourney,
    "trules": _handle_trules,
    "tourneyrules": _handle_trules,
    "garules": _handle_trules,
    "winners": _handle_winners,
    "winlist": _handle_winners,
    "wl": _handle_winners,
    "iwon": _handle_iwon,
    "won": _handle_iwon,
    "matches": _handle_matches,
    "matchups": _handle_matches,
    "bracket": _handle_matches,
    "mymatch": _handle_mymatch,
    "match": _handle_mymatch,
    "reportissue": _handle_reportissue,
    "report": _handle_reportissue,
    "afk": _handle_reportissue,
    "events": _handle_events,
    "rules": _handle_rules,
    "register": _handle_register,
    "unregister": _handle_unregister,
}
