from bot.config import config
from bot.models.message import IncomingMessage
from bot.services import identity, mvp, tournament
from bot.services.mvp import activity_summary, get_invite
from bot.services.community import get_info, get_announcement, get_socials
from bot.handlers.utils import in_main, in_storage, require_main, require_storage_staff
from bot.utils.scifi import (
    LINE_DIVIDER,
    to_small_caps,
    render_progress_bar,
    ICON_SPARKLE,
    ICON_STAR,
    ICON_ARROW,
    ICON_BRANCH,
    ICON_LIGHTNING,
    ICON_CROWN,
)


COMMAND_HELP = {
    "info": "/info - View community and server blueprint.",
    "invite": "/invite - Get the official group access link.",
    "socials": "/socials - View official Instagram, Discord, and networks.",
    "summary": "/summary (/sum) - Staff-only daily activity recon (Staff GC).",
    "announce": "/announce - View current server transmissions.",
    "events": "/events - List upcoming community operations.",
    "rules": "/rules - View group directives and protocols.",
    "profile": "/profile (/p) [@user] - Member matrix, level, rank & status.",
    "rank": "/rank (/r) [@user] - XP progress bar and server rank tier.",
    "leaderboard": "/leaderboard (/lb or /top) - Top 5 chat rankings.",
    "tourney": "/tourneyinfo (/t) - Active arena tournament status.",
    "tourneyinfo": "/tourneyinfo (/t) - Active arena tournament status.",
    "trules": "/trules - Match arena and giveaway regulations.",
    "winners": "/winners (/wl) - Hall of Champions records.",
    "register": "/register (/reg) - Secure an arena slot.",
    "unregister": "/unregister (/unreg) - Relinquish tournament slot.",
    "mymatch": "/mymatch - View active round opponent and status.",
    "matches": "/matches - Current round match matrix.",
    "iwon": "/iwon (/won) - Transmit match victory confirmation.",
    "reportissue": "/reportissue <reason> (/afk) - Flag AFK or match stall.",
    "roast": "/roast @user - Tactical burn simulation.",
    "flirt": "/flirt @user - Neural charm protocol.",
    "bully": "/bully @user - Playful banter protocol.",
    "ship": "/ship @u1 @u2 - Neural compatibility calculation.",
    "rate": "/rate @user - Metric score evaluation (1-10).",
}


def _handle_help(msg: IncomingMessage, args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group

    cat = args.strip().lower()
    if not cat:
        return (
            "✦ BOT HELP (Shortcuts in brackets) ✦\n"
            "➤ /help core (/h core)\n"
            "➤ /help tourney (/h tourney)\n"
            "➤ /help fun (/h fun)"
        )

    if cat == "core":
        return (
            "✦ CORE COMMANDS ✦\n"
            "➤ /info • /rules • /invite\n"
            "➤ /socials • /announce • /events\n"
            "➤ /profile (/p) • /rank (/r)\n"
            "➤ /leaderboard (/lb or /top)"
        )
    if cat == "tourney":
        return (
            "✦ TOURNEY & GIVEAWAYS ✦\n"
            "➤ /tourneyinfo (/t) • /trules • /winners\n"
            "➤ /register • /unregister\n"
            "➤ /mymatch • /matches (bracket)\n"
            "➤ /iwon (/won) — Claim match win\n"
            "➤ /reportissue <msg> (/afk) — Report AFK"
        )
    if cat == "fun":
        return (
            "✦ FUN COMMANDS ✦\n"
            "➤ /roast @user • /flirt @user\n"
            "➤ /bully @user • /ship @u1 @u2\n"
            "➤ /rate @user"
        )

    clean_cat = cat.lstrip("/")
    if clean_cat in COMMAND_HELP:
        return f"✦ COMMAND PROTOCOL ✦\n➥ {COMMAND_HELP[clean_cat]}"

    return "Unknown category. Use /help core, /help tourney, or /help fun."


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
    inv = get_invite()
    return inv if inv else "No invite link has been configured yet."


def _handle_socials(msg: IncomingMessage, _args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group
    socials = get_socials()
    invite = get_invite()
    insta = socials.get("insta")
    dc = socials.get("dc")
    if not insta and not dc and not invite:
        return "No social links have been configured yet."
    lines = [
        LINE_DIVIDER,
        f"✦ {to_small_caps('OFFICIAL SOCIALS // NETWORKS')} ✦",
        LINE_DIVIDER,
        f"➤ Instagram: {insta or 'Not set yet'}",
        f"➤ Discord: {dc or 'Not set yet'}",
    ]
    if invite:
        lines.append(f"➤ Plato Invite: {invite}")
    return "\n".join(lines)


def _handle_profile(msg: IncomingMessage, args: str) -> str:
    if not (in_main(msg) or in_storage(msg)):
        return require_main(msg) or ""
    target = args.strip().split()[0].lstrip("@") if args.strip() else msg.username
    prof = identity.get_profile(target)
    rank_str = f"#{prof['rank_position']}" if int(prof["rank_position"] or 0) > 0 else "Unranked"

    curr_xp = int(prof["total_xp"] or 0)
    next_xp = int(prof["next_level_xp"] or 100)
    xp_bar = render_progress_bar(curr_xp, next_xp, width=8)

    warns = int(prof["warnings_count"] or 0)
    warn_bar = render_progress_bar(warns, 5, width=5)

    lines = [
        LINE_DIVIDER,
        f"✦ {to_small_caps('IDENTITY')} // {prof['username']} [{str(prof['role']).upper()}] ✦",
        LINE_DIVIDER,
        f"★ {to_small_caps('Rank')}     :: {prof['rank_title']} ({rank_str})",
        f"🗲 Level: {prof['level']} ({curr_xp}/{next_xp} XP)",
        f"➥ {to_small_caps('Progress')} :: {xp_bar}",
        f"➤ {to_small_caps('Messages')} :: {prof['eligible_messages']} eligible",
        f"➤ {to_small_caps('Warnings')} :: {warn_bar} [{warns}/5]",
    ]
    return "\n".join(lines)


def _handle_rank(msg: IncomingMessage, args: str) -> str:
    if not (in_main(msg) or in_storage(msg)):
        return require_main(msg) or ""
    target = args.strip().split()[0].lstrip("@") if args.strip() else msg.username
    prof = identity.get_profile(target)
    rank_str = f"#{prof['rank_position']}" if int(prof["rank_position"] or 0) > 0 else "Unranked"
    curr_xp = int(prof["total_xp"] or 0)
    next_xp = int(prof["next_level_xp"] or 100)
    xp_bar = render_progress_bar(curr_xp, next_xp, width=8)
    return (
        f"★ {prof['username']} — {prof['rank_title']} (Lv.{prof['level']} | "
        f"{curr_xp}/{next_xp} XP | Server Rank: {rank_str})\n"
        f"➥ Progress: {xp_bar}"
    )


def _handle_leaderboard(msg: IncomingMessage, _args: str) -> str:
    if not (in_main(msg) or in_storage(msg)):
        return require_main(msg) or ""
    top = identity.get_leaderboard(limit=5)
    if not top:
        return "✦ No XP rankings yet. Start chatting in the Main GC!"
    lines = [
        LINE_DIVIDER,
        f"✦ XP LEADERBOARD // TOP 5 ✦",
        LINE_DIVIDER,
    ]
    for idx, row in enumerate(top, 1):
        lines.append(
            f"{idx}. {row['username']} — Lv.{row['level']} {row['rank_title']} ({row['total_xp']} XP)"
        )
    return "\n".join(lines)


def _handle_summary(msg: IncomingMessage, args: str) -> str:
    if in_main(msg):
        return "This command is staff-only and belongs in the Staff GC."
    err = require_storage_staff(msg)
    if err:
        return err

    period = (args or "").strip().lower() or "today"
    if period not in {"today", "yesterday"}:
        return "Usage: /summary [today|yesterday]"

    from bot.services import moderation

    total, active, ranked, date_label = activity_summary(config.main_group_id, period=period)
    mod_stats = moderation.warnings_summary_for_period(period=period)
    xp_stats = identity.xp_summary_for_period(period=period)
    warn_total = int(mod_stats.get("total", 0))
    notices = list(mod_stats.get("notices") or [])
    xp_awarded = int(xp_stats.get("total_xp_awarded", 0))
    level_ups = list(xp_stats.get("level_ups") or [])

    active_tourney = tournament.get_active_tournament()
    tourney_parts = tournament.get_participants() if active_tourney else []
    bstate = mvp.get_bridge_state()

    lines = [
        LINE_DIVIDER,
        f"✦ DAILY SUMMARY // {period.upper()} ✦",
        f"➥ {date_label}",
        LINE_DIVIDER,
        f"Active members: {active}",
        f"Total messages: {total}",
        f"XP awarded: {xp_awarded} ({len(level_ups)} level-ups)",
        f"Warnings issued: {warn_total}",
    ]
    if ranked:
        lines.append(f"Most active:")
        for index, (username, count) in enumerate(ranked[:5], 1):
            lines.append(f"{index}. {username} — {count} messages")
    if level_ups:
        lu_str = ", ".join(f"{u} (Lv.{lvl})" for u, lvl, _ in level_ups[:4])
        lines.append(f"Level-ups: {lu_str}")
    if notices:
        flagged = ", ".join(f"{n['username']} ({n['warning_count']})" for n in notices[:5])
        lines.append(f"5-Warn Notice: {flagged}")
    if active_tourney:
        lines.append(
            f"Tourney: {active_tourney['name']} [{active_tourney['status'].upper()}] ({len(tourney_parts)} reg)"
        )
    if bstate.get("last_error"):
        lines.append(f"Bridge Error: {str(bstate['last_error'])[:45]}")
    return "\n".join(lines)


def _handle_announce(msg: IncomingMessage, _args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group:
        return wrong_group
    ann = get_announcement()
    return f"📢 {ann}" if ann else "No active announcements."


def _handle_ai(msg: IncomingMessage, args: str) -> str:
    prompt = args.strip()
    if not prompt:
        return "Usage: /ai <prompt> (or mention @zeno)"
    from bot.services import ai
    return ai.generate_ai_response(msg.user_id, msg.username, prompt)


HANDLERS = {
    "help": _handle_help,
    "info": _handle_info,
    "invite": _handle_invite,
    "socials": _handle_socials,
    "profile": _handle_profile,
    "p": _handle_profile,
    "rank": _handle_rank,
    "r": _handle_rank,
    "leaderboard": _handle_leaderboard,
    "summary": _handle_summary,
    "sum": _handle_summary,
    "announce": _handle_announce,
    "ai": _handle_ai,
    "ask": _handle_ai,
}
