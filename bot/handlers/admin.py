from bot.config import config
from bot.handlers.utils import (
    in_main,
    require_any_group_admin,
    require_storage_admin,
    require_storage_owner,
    require_storage_staff,
)
from bot.models.message import IncomingMessage
from bot.services import community, events, identity, moderation, mvp, tournament
from bot.services.plato import OutboxPlatoClient
from bot.utils.text import chunk_text

plato_client = OutboxPlatoClient()


def _require_staff_or_patched_admin(msg: IncomingMessage) -> str | None:
    if require_storage_admin(msg) is None:
        return None
    return require_storage_staff(msg)


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


def _handle_setinsta(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    val = args.strip()
    if not val:
        return "Usage: /setinsta <url|clear>"
    if val.lower() == "clear":
        community.set_insta(None, msg.user_id)
        mvp.audit(msg.user_id, "insta_cleared", None, "")
        return "Instagram link cleared."
    if not mvp.valid_invite_url(val):
        return "Please provide a valid http(s) Instagram URL."
    community.set_insta(val, msg.user_id)
    mvp.audit(msg.user_id, "insta_set", None, val)
    return "Instagram link updated."


def _handle_setdc(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    val = args.strip()
    if not val:
        return "Usage: /setdc <url|clear>"
    if val.lower() == "clear":
        community.set_dc(None, msg.user_id)
        mvp.audit(msg.user_id, "dc_cleared", None, "")
        return "Discord link cleared."
    if not mvp.valid_invite_url(val):
        return "Please provide a valid http(s) Discord URL."
    community.set_dc(val, msg.user_id)
    mvp.audit(msg.user_id, "dc_set", None, val)
    return "Discord link updated."


def _handle_staffadd(msg: IncomingMessage, args: str) -> str:
    err = require_storage_owner(msg)
    if err:
        return err
    parts = args.strip().split()
    if len(parts) != 2:
        return "Usage: /staffadd <username> <mod|admin>"
    target, role = parts[0].lstrip("@"), parts[1].lower()
    if role not in {"mod", "admin"}:
        return "Role must be 'mod' or 'admin'."
    try:
        key = mvp.set_staff_role(target, role, msg.user_id)
    except ValueError as exc:
        return str(exc)
    return f"Assigned role '{role}' to {key}."


def _handle_staffremove(msg: IncomingMessage, args: str) -> str:
    err = require_storage_owner(msg)
    if err:
        return err
    target = args.strip().lstrip("@")
    if not target:
        return "Usage: /staffremove <username>"
    try:
        removed = mvp.remove_staff_role(target, msg.user_id)
    except PermissionError as exc:
        return str(exc)
    if not removed:
        return f"{target} is not in the staff roster."
    return f"Removed staff role from {target}."


def _handle_stafflist(msg: IncomingMessage, _args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    roster = mvp.list_staff()
    if not roster:
        return "No staff configured."
    lines = ["✦ STAFF ROSTER ✦"]
    for uid, role in roster:
        lines.append(f"  ➤ {uid} [{role.upper()}]")
    return "\n".join(lines)


def _handle_config(msg: IncomingMessage, args: str) -> str:
    parts = args.strip().split(maxsplit=1)
    if not parts:
        err = _require_staff_or_patched_admin(msg)
        if err:
            return err
        cfg = mvp.list_config_values()
        lines = ["✦ BOT CONFIG ✦"]
        for k, v in cfg.items():
            lines.append(f"  ➤ {k}: {v}")
        return "\n".join(lines)

    if len(parts) == 1:
        err = _require_staff_or_patched_admin(msg)
        if err:
            return err
        key = parts[0].lower()
        val = mvp.get_config_value(key)
        return f"✦ {key} = {val}" if val is not None else f"Unknown config key '{key}'."

    err = require_storage_owner(msg)
    if err:
        return err
    key, value = parts[0].lower(), parts[1].strip()
    mvp.set_config_value(key, value, msg.user_id)
    return f"Updated config {key} = {value}"


def _handle_summon(msg: IncomingMessage, args: str) -> str:
    err = require_any_group_admin(msg)
    if err:
        return err
    duration_sec: int | None = None
    tokens = args.strip().split()
    for tok in tokens:
        low = tok.lower()
        if low in {"staff", "staffgc"}:
            continue
        try:
            mins = int(tok)
            if mins < 1 or mins > 60:
                return "Summon duration must be between 1 and 60 minutes."
            duration_sec = mins * 60
        except ValueError:
            return "Usage: /summon [minutes] (or /sm [minutes])"
    seconds = mvp.summon_to_staff(
        msg.user_id,
        duration_seconds=duration_sec,
        target_title_override="-⊹ STAFF ⟡ GROUP ⊹-",
    )
    mins_label = max(1, seconds // 60)
    return f"✦ Summoned to Staff GC for {mins_label} min. Use /return (or /ret) when done."


def _handle_return(msg: IncomingMessage, _args: str) -> str:
    err = require_any_group_admin(msg)
    if err:
        return err
    mvp.return_to_main(msg.user_id)
    return "✔︎ Returning bot focus to Main GC."


def _handle_off(msg: IncomingMessage, _args: str) -> str:
    uid_low = (msg.user_id or "").strip().lower()
    uname_low = (msg.username or "").strip().lower()
    if uid_low != "hawtshot" and uname_low != "hawtshot":
        return "✘ Only HawtShot can use /off."
    mvp.turn_off_gc(msg.user_id)
    return "✔︎ Bot turned off by HawtShot. Leaving group chat now."


def _handle_on(msg: IncomingMessage, _args: str) -> str:
    err = require_any_group_admin(msg)
    if err:
        return err
    mvp.return_to_main(msg.user_id)
    return "✔︎ Bot presence enabled. Focus returned to Main GC."


def _handle_status(msg: IncomingMessage, _args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    state = mvp.get_bridge_state()
    pending = mvp.get_outbox_pending_count()
    target = state["target_group_title"] or state["target_group_id"]
    current = state["current_group_title"] or state["current_group_id"] or "Unknown"
    rem = int(state["summon_remaining_seconds"] or 0)
    timer_str = f"{rem}s" if rem > 0 else "None"
    hb = str(state["last_heartbeat_at"] or "Never")
    if len(hb) >= 19:
        hb = hb[11:19] + " UTC"
    lines = [
        "✦ SYSTEM STATUS ✦",
        f"➤ Target GC: {target}",
        f"➤ Active GC: {current}",
        f"➤ Summon timer: {timer_str}",
        f"➤ Outbox queue: {pending}",
        f"➤ Last heartbeat: {hb}",
    ]
    if state.get("last_error"):
        lines.append(f"✘ Error: {str(state['last_error'])[:60]}")
    return "\n".join(lines)


def _handle_adminhelp(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err

    cat = args.strip().lower()
    if not cat:
        return (
            "✦ ADMIN HELP (Type /ah <section>) ✦\n"
            "➤ content — Info, rules, socials\n"
            "➤ tourney — Elimination brackets\n"
            "➤ giveaway — Giveaways & winners\n"
            "➤ mod — Warns, English, links\n"
            "➤ staff — Staff roles, XP, system"
        )

    if cat == "content":
        return (
            "✦ CONTENT & SOCIALS ✦\n"
            "/setinfo <text>   /setrules <text>\n"
            "/setannounce <text>   /clearannounce\n"
            "/setinsta <url>   /setdc <url>\n"
            "/setinvite <url> (Plato invite link)"
        )
    if cat == "tourney":
        return (
            "✦ TOURNAMENT COMMANDS ✦\n"
            "/createtour (step-by-step wizard)\n"
            "/start (open reg / start round)\n"
            "/pause   /resume   /end   /draft\n"
            "/forcewin <@user>   /dq <@user>\n"
            "/checkafk   /issues   /tourneycreate"
        )
    if cat in {"giveaway", "ga", "winners"}:
        return (
            "✦ GIVEAWAYS & WINNERS ✦\n"
            "/createga (step-by-step wizard)\n"
            "/start (launch wave)   /draft\n"
            "/pause • /resume • /end\n"
            "/addwinner <@user> [tab]\n"
            "/delwinner <num/user> • /winners"
        )
    if cat == "events":
        return "📅 EVENTS:\n/eventadd <name>|<date>|<desc>\n/eventdel <name>"
    if cat == "mod":
        return (
            "🛡 MODERATION:\n"
            "/warn <@user> <reason> • /unwarn <@user>\n"
            "/warns <@user> • /clearwarn <@user>\n"
            "/noticelist (5-warn list)\n"
            "/english <on|off> (English-only filter)\n"
            "/allowlink <site.com> • /blocklink <site>\n"
            "/links • /summary [today|yesterday]"
        )
    if cat in {"staff", "system"}:
        return (
            "👥 STAFF & CONTROLS:\n"
            "/addstaff <@user> <mod|admin>\n"
            "/removestaff <@user> • /stafflist\n"
            "/giveexp <@user> <xp> • /takeexp <@user> <xp>\n"
            "/summon [mins] • /return • /on • /off\n"
            "/status • /draft"
        )
    if cat == "legacy":
        return "LEGACY:\n/spamset <id> <text>\n/setinvite <url>\n/add <user>:<id>"

    return f"Unknown section '{cat}'. Type /adminhelp to see sections."


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

    if sess["command"] == "tour_wizard":
        from bot.services.session import end_session, update_session
        step = sess["step"]
        ans = msg.text.strip()
        data = sess.get("data", {})

        if step == "title":
            update_session(msg.user_id, "game", {"title": ans})
            return "🎮 Game? (e.g. Ocho, Pool, Bingo)"
        if step == "game":
            update_session(msg.user_id, "slots", {"game": ans})
            return "👥 Total participant slots? (e.g. 16, 8, 4)"
        if step == "slots":
            try:
                slots_num = int(ans)
            except ValueError:
                slots_num = 16
            update_session(msg.user_id, "rules", {"slots": slots_num})
            return "📜 Tournament Rules? (e.g. 5m AFK walkover, fair play)"
        if step == "rules":
            update_session(msg.user_id, "r1_rules", {"rules": ans})
            return "⚔️ Round 1 Rules? (or type 'same')"
        if step == "r1_rules":
            r1 = data.get("rules", "Standard rules") if ans.lower() == "same" else ans
            update_session(msg.user_id, "prize", {"r1_rules": r1})
            return "🎁 Prize / Description? (or type 'none')"
        if step == "prize":
            prize = None if ans.lower() in ("none", "no") else ans
            slots = int(data.get("slots", 16))
            title = data.get("title", f"{data.get('game', 'Game')} Tourney")
            game = data.get("game", "Plato Game")
            rules = data.get("rules", "Standard rules")

            info = tournament.quick_create_tournament(
                slots=slots,
                game=game,
                name=title,
                actor_id=msg.user_id,
                rules_text=rules,
            )
            tournament.update_active_tournament_field("prize_info", prize)
            tournament.set_active_tournament_status("draft")
            end_session(msg.user_id)
            return (
                f"✅ Tournament '{title}' created as DRAFT!\n"
                f"🎮 Game: {game} | 👥 Slots: {slots} ({info['total_rounds']} Rounds)\n"
                f"📜 Rules: {rules}\n"
                "💡 Staff controls:\n"
                "• /draft — View draft details\n"
                "• /start — Open registration in Main GC"
            )

    if sess["command"] == "ga_wizard":
        from bot.services.session import end_session, update_session
        step = sess["step"]
        ans = msg.text.strip()
        data = sess.get("data", {})

        if step == "game":
            update_session(msg.user_id, "winners", {"game": ans})
            return "🏆 Total Winners? (e.g. 10)"
        if step == "winners":
            try:
                w_num = int(ans)
            except ValueError:
                w_num = 10
            update_session(msg.user_id, "online", {"winners": w_num})
            return "👥 Approximate members online? (e.g. 40 or 45 - used for wave capacity)"
        if step == "online":
            try:
                on_num = int(ans)
            except ValueError:
                on_num = 40
            update_session(msg.user_id, "info", {"online": on_num})
            return "ℹ️ Giveaway Info / Timing? (e.g. Starting right now!)"
        if step == "info":
            update_session(msg.user_id, "rules", {"info": ans})
            return "📜 Giveaway Rules? (e.g. 1 win per player)"
        if step == "rules":
            game = data.get("game", "Bingo")
            total_w = int(data.get("winners", 10))
            online = int(data.get("online", 40))
            info_text = data.get("info", "Join tabs to win!")
            rules_text = ans

            ga_meta, ann = tournament.create_giveaway(
                target_winners=total_w,
                game=game,
                online_count=online,
                info_text=info_text,
                rules_text=rules_text,
                actor_id=msg.user_id,
            )
            from bot.database.db import get_conn
            conn = get_conn()
            conn.execute("UPDATE giveaways SET status = 'draft' WHERE id = ?", (ga_meta["id"],))
            conn.commit()
            end_session(msg.user_id)
            return (
                f"✅ Giveaway draft ready!\n"
                f"🎮 Game: {game} | 🏆 Total Winners: {total_w}\n"
                f"👥 Online: {online} (Wave #1: {ga_meta['batch1_tabs']} tabs)\n"
                f"📜 Rules: {rules_text}\n"
                "💡 Staff controls:\n"
                "• /draft — View draft details\n"
                "• /start — Announce Wave #1 in Main GC"
            )

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
    if in_main(msg):
        return "This command is staff-only and belongs in the Staff GC."
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    parts = tournament.get_participants()
    if not parts:
        return "No participants found for the active tournament."
    lines = [f"📋 Participants ({len(parts)}):"]
    for p in parts:
        uid = p["user_id"] if "user_id" in p.keys() else p["username"]
        lines.append(f"• {p['username']} [ID: {uid}] [{p['status']}]")
    return "\n".join(lines)


def _broadcast_to_main(msg: IncomingMessage, messages: list[str] | str) -> None:
    if not config.main_group_id or msg.group_id == config.main_group_id:
        return
    msg_list = [messages] if isinstance(messages, str) else messages
    for text in msg_list:
        if not text:
            continue
        for chunk in chunk_text(text, limit=256):
            plato_client.send_message(config.main_group_id, chunk)


def _handle_createtourney(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    raw = args.strip()
    if not raw:
        from bot.services.session import start_session
        start_session(msg.user_id, "tour_wizard", "title")
        return "🏆 Tournament Title? (e.g. Nova Ocho Cup)"
    pipe_parts = [p.strip() for p in raw.split("|")]
    first_tokens = pipe_parts[0].split(maxsplit=1)
    if not first_tokens:
        return "Usage: /createtourney <slots> <game> | <rules>"
    try:
        slots = int(first_tokens[0])
    except ValueError:
        return "First argument must be participant slots (e.g., 16, 8, 4)."
    game = first_tokens[1].strip() if len(first_tokens) > 1 else "TBD"
    rules = pipe_parts[1] if len(pipe_parts) > 1 and pipe_parts[1] else "Standard rules (5m AFK limit)"
    title = pipe_parts[2] if len(pipe_parts) > 2 and pipe_parts[2] else f"{game} Tournament"
    info = tournament.quick_create_tournament(
        slots=slots,
        game=game,
        name=title,
        actor_id=msg.user_id,
        rules_text=rules,
    )
    ann = (
        f"🏆 {info['name'].upper()} OPEN FOR REGISTRATION!\n"
        f"🎮 Game: {info['game']}\n"
        f"👥 Slots: {info['max_slots']} ({info['total_rounds']} Elimination Rounds)\n"
        f"📜 Rules: {rules}\n"
        f"✅ Type /register in Main GC to join!"
    )
    _broadcast_to_main(msg, ann)
    return ann


def _handle_starttourney(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    game: str | None = None
    rules: str | None = None
    raw = args.strip()
    if raw:
        if "|" in raw:
            parts = [p.strip() for p in raw.split("|", 1)]
            game = parts[0] or None
            rules = parts[1] or None
        else:
            game = raw
    ok, text_out = tournament.start_tournament_or_next_round(
        actor_id=msg.user_id,
        new_game=game,
        new_rules=rules,
    )
    if ok:
        _broadcast_to_main(msg, text_out)
    return text_out


def _handle_roundrules(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    raw = args.strip()
    if not raw:
        return "Usage: /roundrules <game> | <rules>"
    if "|" in raw:
        parts = [p.strip() for p in raw.split("|", 1)]
        game, rules = parts[0], parts[1]
    else:
        game, rules = raw, "Standard rules (5m AFK limit)"
    res = tournament.set_round_rules(game=game, rules=rules, actor_id=msg.user_id)
    _broadcast_to_main(msg, res)
    return res


def _handle_forcewin(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    target = args.strip().split()[0].lstrip("@") if args.strip() else ""
    if not target:
        return "Usage: /forcewin <@user>"
    ok, text_out = tournament.record_match_win(
        caller_id=msg.user_id,
        caller_name=target,
        is_staff_override=True,
        target_winner=target,
        win_reason="staff_forcewin",
    )
    if ok:
        _broadcast_to_main(msg, text_out)
    return text_out


def _handle_dq(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    target = args.strip().split()[0].lstrip("@") if args.strip() else ""
    if not target:
        return "Usage: /dq <@user>"
    text_out = tournament.disqualify_player(target, actor_id=msg.user_id)
    _broadcast_to_main(msg, text_out)
    return text_out


def _handle_checkafk(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    timeout_mins = 5.0
    force_all = False
    if args.strip():
        tok = args.strip().split()[0].lower()
        if tok in {"force", "all", "0"}:
            force_all = True
            timeout_mins = 0.0
        else:
            try:
                timeout_mins = max(0.0, float(tok))
            except ValueError:
                return "Usage: /checkafk [timeout_minutes|force]"
    res = tournament.check_and_resolve_afk(timeout_minutes=timeout_mins, force_all_pending=force_all)
    if not res:
        return "✅ No matches exceeded the AFK timeout."
    _broadcast_to_main(msg, res)
    return res


def _handle_issues(msg: IncomingMessage, _args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    return tournament.get_open_issues_text()


def _handle_createga(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    raw = args.strip()
    if not raw:
        from bot.services.session import start_session
        start_session(msg.user_id, "ga_wizard", "game")
        return "🎮 Giveaway Game? (e.g. Bingo, Ocho, Pool)"
    pipe_parts = [p.strip() for p in raw.split("|")]
    tokens = pipe_parts[0].split()
    if len(tokens) < 3:
        return (
            "Usage: /createga <winners_count> <game> <online_count> [| <rules>]\n"
            "Example: /createga 10 Bingo 40 | 1 win per player"
        )
    try:
        total_winners = int(tokens[0])
        online_count = int(tokens[-1])
    except ValueError:
        return "Winners count and online count must be numbers (e.g., /createga 10 Bingo 40)."
    game = " ".join(tokens[1:-1]).strip() or "Bingo"
    rules = pipe_parts[1] if len(pipe_parts) > 1 and pipe_parts[1] else "Follow host instructions"
    info = pipe_parts[2] if len(pipe_parts) > 2 and pipe_parts[2] else f"{total_winners} Winners Giveaway"
    _ga_meta, announcement = tournament.create_giveaway(
        target_winners=total_winners,
        game=game,
        online_count=online_count,
        info_text=info,
        rules_text=rules,
        actor_id=msg.user_id,
    )
    _broadcast_to_main(msg, announcement)
    return announcement


def _handle_draft(msg: IncomingMessage, _args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    return tournament.get_draft_summary()


def _handle_start(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err

    tourney = tournament.get_active_tournament()
    ga = tournament.get_active_giveaway()

    if tourney:
        if tourney["status"] == "draft":
            tournament.update_active_tournament_field("status", "open")
            rules = tourney["rules_text"] or "Standard rules"
            ann = (
                f"🏆 {tourney['name'].upper()} REGISTRATION NOW OPEN!\n"
                f"🎮 Game: {tourney['game']}\n"
                f"👥 Slots: {tourney['max_slots']}\n"
                f"📜 Rules: {rules}\n"
                "✅ Type /register to join!"
            )
            _broadcast_to_main(msg, ann)
            return ann
        # If open or ongoing, run starttourney/nextround
        return _handle_starttourney(msg, args)

    if ga:
        if ga["status"] == "draft":
            from bot.database.db import get_conn
            conn = get_conn()
            conn.execute("UPDATE giveaways SET status = 'active' WHERE id = ?", (ga["id"],))
            conn.commit()
            ann = (
                f"🎁 {ga['title'].upper()} STARTED!\n"
                f"ℹ️ Info: {ga['info_text']}\n"
                f"📜 Rules: {ga['rules_text']}\n"
                f"👥 Online: {ga['online_count']} (Seat Cap: {ga['seats_per_tab']}/tab)\n"
                f"🎮 WAVE #{ga['current_batch']}: Creating {ga['tabs_in_current_batch']} {ga['game']} tab(s) now!"
            )
            _broadcast_to_main(msg, ann)
            return ann

    return "No active draft or pending tournament/giveaway to start. Use /createtour or /createga first."


def _handle_pause(msg: IncomingMessage, _args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    ok, text = tournament.pause_event(msg.user_id)
    if ok:
        _broadcast_to_main(msg, text)
    return text


def _handle_resume(msg: IncomingMessage, _args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    ok, text = tournament.resume_event(msg.user_id)
    if ok:
        _broadcast_to_main(msg, text)
    return text


def _handle_end(msg: IncomingMessage, _args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    ok, text = tournament.end_active_event(msg.user_id)
    if ok:
        _broadcast_to_main(msg, text)
    return text


def _handle_endga(msg: IncomingMessage, _args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    if tournament.end_giveaway():
        return "✅ Active giveaway ended."
    return "No active giveaway to end."


def _handle_settrules(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    val = args.strip()
    if not val:
        return "Usage: /settrules <rules text|clear>"
    if val.lower() == "clear":
        community.set_tourney_rules(None, msg.user_id)
        return "Tourney / giveaway rules cleared."
    community.set_tourney_rules(val, msg.user_id)
    tournament.update_active_tournament_field("rules_text", val)
    return "Tourney / giveaway rules updated."


def _handle_addwinner(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    parts = args.strip().split(maxsplit=1)
    if not parts:
        return "Usage: /addwinner <@user> [tab/game label]"
    target = parts[0].lstrip("@")
    tab_label = parts[1].strip() if len(parts) > 1 else None

    active_ga = tournament.get_active_giveaway()
    if active_ga and not tab_label:
        ok, ga_text = tournament.record_giveaway_winner(target, msg.user_id)
        if ok:
            _broadcast_to_main(msg, ga_text)
        return ga_text

    entry, all_winners = tournament.add_winner(target, tab_label, msg.user_id)
    progressive_names = ", ".join(w["username"] for w in all_winners)
    if config.main_group_id:
        main_msg = tournament.format_winners_list(
            all_winners,
            header=f"🎉 WINNER ADDED: @{entry['username']} ({entry['tab_label']})\n🏆 Winners so far: {progressive_names}",
        )
        for chunk in chunk_text(main_msg, limit=256):
            plato_client.send_message(config.main_group_id, chunk)

    return (
        f"✅ Added winner @{entry['username']} [ID: {entry['user_id']}] for {entry['tab_label']}.\n"
        f"🏆 Winners so far: {progressive_names}\n"
        f"📢 Updated Winners List ({len(all_winners)} total) queued to Main GC."
    )


def _handle_delwinner(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    ident = args.strip()
    if not ident:
        return "Usage: /dw <number_or_username>"
    if tournament.remove_winner(ident):
        return f"Removed winner '{ident}'."
    return f"Winner '{ident}' not found."


def _handle_clearwinners(msg: IncomingMessage, _args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    count = tournament.clear_winners()
    return f"Cleared {count} winner(s) from the winners list."


def _handle_warn(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    parts = args.strip().split(maxsplit=1)
    if len(parts) != 2:
        return "Usage: /warn <username> <reason>"

    target, reason = parts[0].lstrip("@"), parts[1]
    count = moderation.add_warning(target.lower(), target, reason, msg.user_id)

    response = (
        f"Warned {target} for: {reason} ({count}/5)\n"
        f"➥ Queued: Will tag & reply to @{target} in Main GC when online."
    )
    if count >= 5:
        response += f"\n🗲 This user has reached {count} warnings and is on the Staff Notice List."
    elif count >= 3:
        response += f"\n🗲 This user has reached {count} warnings. Admin attention recommended."
    return response


def _handle_unwarn(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    parts = args.strip().split()
    if not parts:
        return "Usage: /unwarn <username> [warning_id]"
    target = parts[0].lstrip("@")
    warn_id: int | None = None
    if len(parts) >= 2:
        try:
            warn_id = int(parts[1].lstrip("#"))
        except ValueError:
            return "Warning ID must be a number."
    removed, remaining = moderation.remove_single_warning(target, warn_id, msg.user_id)
    if not removed:
        return f"No matching warning found for {target}."
    return f"Removed 1 warning from {target}. Active warnings: {remaining}/5."


def _handle_warns(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    target = args.strip().lstrip("@")
    if not target:
        return "Usage: /warns <username>"

    warns = moderation.get_warnings(target)
    if not warns:
        return f"{target} has no warnings."
    lines = [f"Warnings for {target} ({len(warns)}/5):"]
    for w in warns:
        wid = w["id"] if "id" in w.keys() else "?"
        cat = (w["category"] if "category" in w.keys() and w["category"] else "manual").upper()
        lines.append(f"• #{wid} [{cat}] {w['created_at'][:10]}: {w['reason']}")
    return "\n".join(lines)


def _handle_clearwarn(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    target = args.strip().lstrip("@")
    if not target:
        return "Usage: /clearwarn <username>"
    count = moderation.clear_warnings(target)
    return f"Cleared {count} warnings for {target}."


def _handle_noticelist(msg: IncomingMessage, _args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    notices = moderation.get_notice_list(include_resolved=False)
    if not notices:
        return "✅ No members are currently on the 5-Warning Notice List."
    lines = ["🚨 5-WARNING NOTICE LIST"]
    for n in notices:
        lines.append(f"• {n['username']} ({n['warning_count']} warns) — {n['reasons_summary']}")
    return "\n".join(lines)


def _handle_allowdomain(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    dom = args.strip()
    if not dom:
        return "Usage: /allowdomain <domain>"
    try:
        clean = moderation.add_allowed_domain(dom, msg.user_id)
    except ValueError as exc:
        return str(exc)
    return f"Allowed link domain: {clean}"


def _handle_removedomain(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    dom = args.strip()
    if not dom:
        return "Usage: /removedomain <domain>"
    if moderation.remove_allowed_domain(dom, msg.user_id):
        return f"Removed allowed domain: {moderation.normalize_domain(dom)}"
    return f"Domain '{dom}' was not in the allowlist."


def _handle_domains(msg: IncomingMessage, _args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    doms = moderation.list_allowed_domains()
    lines = ["🔗 ALLOWED LINK DOMAINS"]
    for d in doms:
        lines.append(f"• {d}")
    return "\n".join(lines)


def _handle_setlang(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    mode = args.strip().lower()
    if mode not in {"on", "off", "true", "false"}:
        return "Usage: /setlang <on|off>"
    enabled = mode in {"on", "true"}
    mvp.set_config_value("english_only", "true" if enabled else "false", msg.user_id)
    state_str = "ON (Strict English-only)" if enabled else "OFF"
    return f"Language enforcement is now {state_str}."


def _handle_greetings(msg: IncomingMessage, args: str) -> str:
    err = _require_staff_or_patched_admin(msg)
    if err:
        return err
    mode = args.strip().lower()
    if mode not in {"on", "off", "true", "false"}:
        return "Usage: /greetings <on|off>"
    enabled = mode in {"on", "true"}
    mvp.set_config_value("auto_response", "true" if enabled else "false", msg.user_id)
    state_str = "ON" if enabled else "OFF"
    return f"Auto-response greetings and wishes are now {state_str}."


def _handle_xpgrant(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    parts = args.strip().split()
    if len(parts) != 2:
        return "Usage: /xpgrant <username> <amount>"
    target = parts[0].lstrip("@")
    try:
        amount = int(parts[1])
        if amount <= 0:
            return "XP amount must be a positive number."
    except ValueError:
        return "XP amount must be a positive number."
    prof = identity.adjust_xp(target, amount, msg.user_id, reason="admin_grant")
    return (
        f"Granted +{amount} XP to {prof['username']}. "
        f"Total: {prof['total_xp']} XP (Lv.{prof['level']} {prof['rank_title']})."
    )


def _handle_xprevoke(msg: IncomingMessage, args: str) -> str:
    err = require_storage_admin(msg)
    if err:
        return err
    parts = args.strip().split()
    if len(parts) != 2:
        return "Usage: /xprevoke <username> <amount>"
    target = parts[0].lstrip("@")
    try:
        amount = int(parts[1])
        if amount <= 0:
            return "XP amount must be a positive number."
    except ValueError:
        return "XP amount must be a positive number."
    prof = identity.adjust_xp(target, -amount, msg.user_id, reason="admin_revoke")
    return (
        f"Revoked -{amount} XP from {prof['username']}. "
        f"Total: {prof['total_xp']} XP (Lv.{prof['level']} {prof['rank_title']})."
    )


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
    "ah": _handle_adminhelp,
    "setinfo": _handle_setinfo,
    "sinfo": _handle_setinfo,
    "setrules": _handle_setrules,
    "srules": _handle_setrules,
    "settrules": _handle_settrules,
    "strules": _handle_settrules,
    "setannounce": _handle_setannounce,
    "sann": _handle_setannounce,
    "clearannounce": _handle_clearannounce,
    "cann": _handle_clearannounce,
    "setinsta": _handle_setinsta,
    "sinsta": _handle_setinsta,
    "setdc": _handle_setdc,
    "sdc": _handle_setdc,
    "staffadd": _handle_staffadd,
    "addstaff": _handle_staffadd,
    "sadd": _handle_staffadd,
    "staffremove": _handle_staffremove,
    "removestaff": _handle_staffremove,
    "srem": _handle_staffremove,
    "stafflist": _handle_stafflist,
    "slist": _handle_stafflist,
    "config": _handle_config,
    "cfg": _handle_config,
    "summon": _handle_summon,
    "sm": _handle_summon,
    "return": _handle_return,
    "ret": _handle_return,
    "back": _handle_return,
    "on": _handle_on,
    "off": _handle_off,
    "status": _handle_status,
    "st": _handle_status,
    "draft": _handle_draft,
    "start": _handle_start,
    "pause": _handle_pause,
    "hold": _handle_pause,
    "resume": _handle_resume,
    "end": _handle_end,
    "createtour": _handle_createtourney,
    "createtourney": _handle_createtourney,
    "tc": _handle_createtourney,
    "tourneycreate": _handle_tourneycreate,
    "tcreate": _handle_tourneycreate,
    "starttourney": _handle_starttourney,
    "tstart": _handle_starttourney,
    "nextround": _handle_starttourney,
    "roundrules": _handle_roundrules,
    "forcewin": _handle_forcewin,
    "dq": _handle_dq,
    "disqualify": _handle_dq,
    "checkafk": _handle_checkafk,
    "issues": _handle_issues,
    "createga": _handle_createga,
    "ga": _handle_createga,
    "gacreate": _handle_createga,
    "endga": _handle_endga,
    "gaend": _handle_endga,
    "tourneyset": _handle_tourneyset,
    "tset": _handle_tourneyset,
    "tourneyopen": _handle_tourneyopen,
    "topen": _handle_tourneyopen,
    "tourneyclose": _handle_tourneyclose,
    "tclose": _handle_tourneyclose,
    "tourneyclear": _handle_tourneyclear,
    "tclear": _handle_tourneyclear,
    "participants": _handle_participants,
    "plist": _handle_participants,
    "addwinner": _handle_addwinner,
    "winadd": _handle_addwinner,
    "aw": _handle_addwinner,
    "delwinner": _handle_delwinner,
    "windel": _handle_delwinner,
    "dw": _handle_delwinner,
    "clearwinners": _handle_clearwinners,
    "winclear": _handle_clearwinners,
    "cw": _handle_clearwinners,
    "eventadd": _handle_eventadd,
    "addEvent": _handle_eventadd,
    "eadd": _handle_eventadd,
    "eventdel": _handle_eventdel,
    "edel": _handle_eventdel,
    "warn": _handle_warn,
    "w": _handle_warn,
    "unwarn": _handle_unwarn,
    "uw": _handle_unwarn,
    "warns": _handle_warns,
    "ws": _handle_warns,
    "clearwarn": _handle_clearwarn,
    "cwarn": _handle_clearwarn,
    "noticelist": _handle_noticelist,
    "nlist": _handle_noticelist,
    "allowdomain": _handle_allowdomain,
    "allowlink": _handle_allowdomain,
    "addlink": _handle_allowdomain,
    "removedomain": _handle_removedomain,
    "blocklink": _handle_removedomain,
    "remlink": _handle_removedomain,
    "domains": _handle_domains,
    "links": _handle_domains,
    "setlang": _handle_setlang,
    "english": _handle_setlang,
    "lang": _handle_setlang,
    "greetings": _handle_greetings,
    "autoresponse": _handle_greetings,
    "xpgrant": _handle_xpgrant,
    "giveexp": _handle_xpgrant,
    "givexp": _handle_xpgrant,
    "xpg": _handle_xpgrant,
    "xprevoke": _handle_xprevoke,
    "takeexp": _handle_xprevoke,
    "takexp": _handle_xprevoke,
    "xpr": _handle_xprevoke,
}
