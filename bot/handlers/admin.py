from bot.handlers.utils import require_storage_admin
from bot.models.message import IncomingMessage
from bot.services import community, events, moderation, tournament


def _handle_setinfo(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    if not args.strip():
        return "Usage: /setinfo <text>"
    community.set_info(args.strip(), msg.user_id)
    return "Community info updated."


def _handle_setrules(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    if not args.strip():
        return "Usage: /setrules <text>"
    community.set_rules(args.strip(), msg.user_id)
    return "Community rules updated."


def _handle_setannounce(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    if not args.strip():
        return "Usage: /setannounce <text>"
    community.set_announcement(args.strip(), msg.user_id)
    return "Announcement updated."


def _handle_clearannounce(msg: IncomingMessage, _args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    community.set_announcement(None, msg.user_id)
    return "Announcement cleared."


def _handle_adminhelp(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err

    cat = args.strip().lower()
    if not cat:
        return "🛠 ADMIN HELP\n/adminhelp content\n/adminhelp tourney\n/adminhelp events\n/adminhelp mod\n/adminhelp legacy\n/adminhelp <command>"

    if cat == "content":
        return "CONTENT:\n/setinfo <text>\n/setrules <text>\n/setannounce <text>\n/clearannounce"
    if cat == "tourney":
        return "TOURNEY:\n/tourneycreate (interactive)\n/tourneyset <field> <value>\n/tourneyopen\n/tourneyclose\n/tourneyclear\n/participants"
    if cat == "events":
        return "EVENTS:\n/eventadd <name>|<date>|<desc>\n/eventdel <name>"
    if cat == "mod":
        return "MOD:\n/warn <user> <reason>\n/warns <user>\n/clearwarn <user>"
    if cat == "legacy":
        return "LEGACY:\n/spamset <id> <text>\n/inviteset <url>\n/add <user>:<id>"

    return f"Use /adminhelp to see categories. Command: /{cat}"


def _handle_tourneycreate(msg: IncomingMessage, _args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    from bot.services.session import start_session
    start_session(msg.user_id, "tourneycreate", "title")
    return "Tournament title?"


def handle_interactive_session(msg: IncomingMessage, sess: dict) -> str | None:
    if sess["command"] == "tourneycreate":
        from bot.services.session import end_session, update_session
        step = sess["step"]
        ans = msg.text.strip()

        if step == "title":
            update_session(msg.user_id, "game", {"title": ans})
            return "Game?"
        if step == "game":
            update_session(msg.user_id, "date", {"game": ans})
            return "Date?"
        if step == "date":
            update_session(msg.user_id, "time", {"date": ans})
            return "Time?"
        if step == "time":
            update_session(msg.user_id, "reg_time", {"time": ans})
            return "Registration time?"
        if step == "reg_time":
            update_session(msg.user_id, "desc", {"reg_time": ans})
            return "Description?"
        if step == "desc":
            update_session(msg.user_id, "rules", {"desc": ans})
            return "Rules?"
        if step == "rules":
            update_session(msg.user_id, "slots", {"rules": ans})
            return "Slots?"
        if step == "slots":
            update_session(msg.user_id, "prize", {"slots": ans})
            return "Prize?"
        if step == "prize":
            update_session(msg.user_id, "host_mode", {"prize": ans})
            return "Host mode? (auto/manual)"
        if step == "host_mode":
            data = sess["data"]
            data["host_mode"] = ans

            tournament.create_tournament(data["title"], msg.user_id)
            tournament.update_active_tournament_field("game", data["game"])
            tournament.update_active_tournament_field("event_date", data["date"])
            tournament.update_active_tournament_field("event_time", data["time"])
            tournament.update_active_tournament_field("registration_time", data["reg_time"])
            tournament.update_active_tournament_field("description_text", data["desc"])
            tournament.update_active_tournament_field("rules_text", data["rules"])
            try:
                tournament.update_active_tournament_field("max_slots", int(data["slots"]))
            except ValueError:
                pass
            tournament.update_active_tournament_field("prize_info", data["prize"])
            tournament.update_active_tournament_field("host_mode", data["host_mode"])

            end_session(msg.user_id)
            return f"Tournament '{data['title']}' created as draft. Use /tourneyopen to open registration."

    return None


def _handle_tourneyset(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    parts = args.strip().split(maxsplit=1)
    if len(parts) != 2:
        return "Usage: /tourneyset <field> <value>"

    field = parts[0].lower()
    value = parts[1].strip()

    field_map = {
        "game": "game",
        "date": "event_date",
        "time": "event_time",
        "regtime": "registration_time",
        "format": "format",
        "slots": "max_slots",
        "prize": "prize_info",
        "desc": "description_text",
        "rules": "rules_text",
        "hostmode": "host_mode",
        "host": "host",
    }

    if field not in field_map:
        return f"Unknown field '{field}'. Allowed: {', '.join(field_map.keys())}"

    db_field = field_map[field]
    if db_field == "max_slots":
        try:
            value = int(value)
        except ValueError:
            return "Slots must be a number."

    if tournament.update_active_tournament_field(db_field, value):
        return f"Updated {field}."
    return "Failed to update. Is there an active tournament?"


def _handle_tourneyopen(msg: IncomingMessage, _args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    if tournament.set_active_tournament_status("open"):
        return "Tournament registration is now OPEN."
    return "Failed. Is there an active tournament?"


def _handle_tourneyclose(msg: IncomingMessage, _args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    if tournament.set_active_tournament_status("closed"):
        return "Tournament registration is now CLOSED."
    return "Failed. Is there an active tournament?"


def _handle_participants(msg: IncomingMessage, _args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    parts = tournament.get_participants()
    if not parts:
        return "No participants found for the active tournament."
    lines = ["Participants:"]
    for p in parts:
        lines.append(f"• {p['username']} [{p['status']}]")
    return "\n".join(lines)


def _handle_warn(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    parts = args.strip().split(maxsplit=1)
    if len(parts) != 2:
        return "Usage: /warn <username> <reason>"

    target, reason = parts[0], parts[1]
    count = moderation.add_warning(target.lower(), target, reason, msg.user_id)

    response = f"Warned {target} for: {reason}"
    if count >= 3:
        response += f"\n⚠️ This user has reached {count} warnings. Admin attention recommended."
    return response


def _handle_warns(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    target = args.strip()
    if not target:
        return "Usage: /warns <username>"

    warns = moderation.get_warnings(target)
    if not warns:
        return f"{target} has no warnings."
    lines = [f"Warnings for {target}:"]
    for w in warns:
        lines.append(f"• {w['created_at'][:10]}: {w['reason']}")
    return "\n".join(lines)


def _handle_clearwarn(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    target = args.strip()
    if not target:
        return "Usage: /clearwarn <username>"
    count = moderation.clear_warnings(target)
    return f"Cleared {count} warnings for {target}."


def _handle_tourneyclear(msg: IncomingMessage, _args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    if tournament.clear_active_tournament():
        return "Active tournament archived."
    return "No active tournament to clear."


def _handle_eventadd(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    parts = [p.strip() for p in args.split("|")]
    if len(parts) != 3:
        return "Usage: /eventadd <name> | <date> | <description>"
    events.add_event(parts[0], parts[1], parts[2], msg.user_id)
    return f"Event '{parts[0]}' added."


def _handle_eventdel(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    name = args.strip()
    if not name:
        return "Usage: /eventdel <name>"
    if events.delete_event(name):
        return f"Event '{name}' deleted."
    return f"Event '{name}' not found."


HANDLERS = {
    "adminhelp": _handle_adminhelp,
    "setinfo": _handle_setinfo,
    "setrules": _handle_setrules,
    "setannounce": _handle_setannounce,
    "clearannounce": _handle_clearannounce,
    "tourneycreate": _handle_tourneycreate,
    "tourneyset": _handle_tourneyset,
    "tourneyopen": _handle_tourneyopen,
    "tourneyclose": _handle_tourneyclose,
    "tourneyclear": _handle_tourneyclear,
    "participants": _handle_participants,
    "eventadd": _handle_eventadd,
    "eventdel": _handle_eventdel,
    "warn": _handle_warn,
    "warns": _handle_warns,
    "clearwarn": _handle_clearwarn,
}
