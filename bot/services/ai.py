import logging
from typing import Optional

from bot.config import config
from bot.services import community, identity, mvp, tournament

logger = logging.getLogger("ai_service")


def build_rag_system_prompt() -> str:
    """Builds ground-truth RAG context dynamically from the database."""
    try:
        info = community.get_info() or "Gaming community on Plato."
        rules = community.get_rules() or "Standard fair-play and respect rules."
        trules = community.get_tourney_rules() or "5-minute AFK limit, no cheating."
        socials = community.get_socials()
        insta = socials.get("insta") or "Not set"
        dc = socials.get("dc") or "Not set"
        invite = mvp.get_invite() or "Ask staff for Plato invite"

        tourney = tournament.get_active_tournament()
        tourney_desc = "No active tournament."
        if tourney:
            tourney_desc = f"{tourney['name']} (Game: {tourney['game'] or 'TBD'}, Status: {tourney['status']})"

        ga = tournament.get_active_giveaway()
        ga_desc = "No active giveaway."
        if ga:
            ga_desc = f"{ga['title']} (Game: {ga['game']}, Target Winners: {ga['target_winners']}, Wave: #{ga['current_batch']})"

        top_rows = identity.get_leaderboard(limit=3)
        top_str = ", ".join(f"#{i+1} {r['username']} ({r['total_xp']} XP)" for i, r in enumerate(top_rows)) or "None yet"
    except Exception:
        info, rules, trules = "Gaming community on Plato.", "Standard fair play.", "5m AFK limit."
        insta, dc, invite = "Not set", "Not set", "Ask staff"
        tourney_desc, ga_desc, top_str = "None", "None", "None"

    return f"""You are FloatSystem (Zeno), the smart, witty, and helpful AI assistant for the Plato group "-» NOVΛ ⟡ BLΛZΞ «-".
Keep responses concise, natural, and under 240 characters so they fit mobile chat bubbles.

LIVE SERVER KNOWLEDGE:
• Group Name: -» NOVΛ ⟡ BLΛZΞ «-
• Community Info: {info}
• Server Rules: {rules}
• Tourney/GA Rules: {trules}
• Instagram: {insta} | Discord: {dc} | Invite: {invite}
• Active Tournament: {tourney_desc}
• Active Giveaway: {ga_desc}
• Top Leaders: {top_str}
• Key Commands: /help, /info, /rules, /socials, /leaderboard, /rank, /tourneyinfo, /register, /mymatch, /matches, /iwon, /winners

Respond directly and concisely in conversational English."""


def _smart_offline_fallback(user_id: str, username: str, user_prompt: str) -> str:
    """Intelligent offline fallback when OpenAI API is unreachable or key is expired.
    Ensures the bot ALWAYS responds smartly and NEVER shows technical errors in chat."""
    low = (user_prompt or "").strip().lower()
    user_tag = f"@{username}" if username and username != "unknown" else "bro"

    # 1. Rules
    if any(k in low for k in ("rule", "allowed", "guideline", "illegal", "toxic")):
        rules = community.get_rules() or "Standard fair-play and respect rules."
        return f"📜 Server Rules: {rules} (Type /rules for details, or /trules for tourney rules)"

    # 2. Tournaments
    if any(k in low for k in ("tourney", "tournament", "bracket", "match", "playing", "champion")):
        tourney = tournament.get_active_tournament()
        if tourney:
            return f"🏆 Active Tournament: {tourney['name']} ({tourney['game'] or 'Game'}) [{tourney['status'].upper()}]. Type /tourneyinfo or /matches!"
        return "🏆 No tournament active right now. Type /events to see upcoming events!"

    # 3. Giveaways
    if any(k in low for k in ("giveaway", "ga", "bingo", "waves", "seats")):
        ga = tournament.get_active_giveaway()
        if ga:
            return f"🎁 Active Giveaway: {ga['title']} (Wave #{ga['current_batch']}). Type /winners to view winners list!"
        return "🎁 No active giveaway running right now. Keep an eye on chat for staff announcements!"

    # 4. XP, Level & Rank
    if any(k in low for k in ("rank", "level", "xp", "leaderboard", "score", "top")):
        return f"★ {user_tag} Check your rank with /rank (/r) or see server top 5 with /leaderboard (/lb)!"

    # 5. Socials & Invites
    if any(k in low for k in ("insta", "instagram", "discord", "social", "invite", "link")):
        return "✦ Type /socials to view our official Instagram and Discord, or /invite for group link!"

    # 6. Bot identity & help
    if any(k in low for k in ("who are you", "what can you do", "help", "commands")):
        return f"✦ I am FloatSystem (Zeno), the Nova Blaze neural bot! Transmit /help to view command modules."

    # 7. Friendly witty fallback
    import random
    banter_responses = [
        f"✦ Hey {user_tag}! FloatSystem is online. Transmit /help to see command modules.",
        f"✦ Neural grid active in Nova Blaze! Check /leaderboard for top active chatters.",
        f"✦ All systems operational! For specific protocols, try /info, /rules, or /tourneyinfo.",
        f"✦ Online and monitoring the grid! Ready for the next game?",
    ]
    return random.choice(banter_responses)


def generate_ai_response(user_id: str, username: str, user_prompt: str) -> str:
    from bot.config import config
    if not config.openai_api_key:
        return _smart_offline_fallback(user_id, username, user_prompt)

    try:
        from openai import OpenAI, AuthenticationError, RateLimitError, OpenAIError

        client = OpenAI(api_key=config.openai_api_key, timeout=8.0)
        sys_prompt = build_rag_system_prompt()

        user_tag = f"@{username}" if username and username != "unknown" else "User"
        resp = client.chat.completions.create(
            model=config.openai_model or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"{user_tag} asks: {user_prompt}"},
            ],
            max_tokens=90,
            temperature=0.7,
        )
        content = resp.choices[0].message.content
        return content.strip() if content else _smart_offline_fallback(user_id, username, user_prompt)
    except AuthenticationError as e:
        logger.warning(f"OpenAI Authentication Error (key expired or invalid): {e}. Using smart offline fallback.")
        return _smart_offline_fallback(user_id, username, user_prompt)
    except RateLimitError as e:
        logger.warning(f"OpenAI Rate Limit Error: {e}. Using smart offline fallback.")
        return _smart_offline_fallback(user_id, username, user_prompt)
    except OpenAIError as e:
        logger.warning(f"OpenAI API Error: {e}. Using smart offline fallback.")
        return _smart_offline_fallback(user_id, username, user_prompt)
    except Exception as e:
        logger.error(f"Unexpected AI Error: {e}. Using smart offline fallback.")
        return _smart_offline_fallback(user_id, username, user_prompt)
