import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from bot.config import config
from bot.utils.scifi import to_small_caps, ICON_SPARKLE, ICON_STAR, ICON_BRANCH

# Cooldown tracking: (user_id, intent) -> timestamp, and channel_last_response
_user_cooldowns: dict[tuple[str, str], float] = {}
_channel_last_response: dict[str, float] = {}

USER_COOLDOWN_SECONDS = 60.0
CHANNEL_COOLDOWN_SECONDS = 10.0


def _get_local_hour() -> int:
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(config.bot_timezone or "Asia/Kolkata")
        return datetime.now(tz).hour
    except Exception:
        # Fallback to IST (UTC + 5:30)
        utc_now = datetime.now(timezone.utc)
        ist_now = utc_now + timedelta(hours=5, minutes=30)
        return ist_now.hour


def _is_cooldown_active(user_id: str, group_id: str, intent: str) -> bool:
    now = time.time()
    user_key = (user_id, intent)
    if now - _user_cooldowns.get(user_key, 0.0) < USER_COOLDOWN_SECONDS:
        return True
    if now - _channel_last_response.get(group_id, 0.0) < CHANNEL_COOLDOWN_SECONDS:
        return True
    return False


def _record_response(user_id: str, group_id: str, intent: str) -> None:
    now = time.time()
    _user_cooldowns[(user_id, intent)] = now
    _channel_last_response[group_id] = now


def check_auto_response(user_id: str, username: str, group_id: str, text: str) -> Optional[str]:
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return None

    low = raw.lower()
    user_tag = f"@{username}" if username and username != "unknown" else "friend"
    hour = _get_local_hour()

    # 1. Birthday wishes
    bday_personal_match = re.search(r"\b(?:happy\s*b(?:irth)?day|hbd)\s+@?([A-Za-z0-9_]{3,30})\b", raw, re.IGNORECASE)
    if bday_personal_match:
        target = bday_personal_match.group(1)
        if target.lower() in {"everyone", "all", "me", "to"}:
            if not _is_cooldown_active(user_id, group_id, "bday_all"):
                _record_response(user_id, group_id, "bday_all")
                return f"✦ Happy Birthday from Nova Blaze matrix! Have a stellar day!"
        else:
            if not _is_cooldown_active(user_id, group_id, f"bday_{target.lower()}"):
                _record_response(user_id, group_id, f"bday_{target.lower()}")
                return f"★ Happy Birthday @{target}! Nova Blaze matrix salutes you today."

    # Universal birthday: "happy birthday everyone", "hbd all"
    if re.fullmatch(r"^(?:happy\s*b(?:irth)?day|hbd)\b(?:\s+(?:everyone|all|guys|fam))?[!.]*$", low):
        if not _is_cooldown_active(user_id, group_id, "bday_all"):
            _record_response(user_id, group_id, "bday_all")
            return "✦ Happy Birthday to whoever is celebrating today in Nova Blaze!"

    # 2. Timezone-aware greetings (Asia/Kolkata)
    # Morning: 05:00 - 11:59
    if re.fullmatch(r"^(?:gm|good\s*morning)\b(?:\s+(?:all|everyone|guys|gang|fam|zeno|bot|chat))?[!.]*$", low):
        if _is_cooldown_active(user_id, group_id, "gm"):
            return None
        _record_response(user_id, group_id, "gm")
        if 5 <= hour < 12:
            return f"✦ Good morning {user_tag}! Systems online, have a productive day ahead."
        elif 12 <= hour < 17:
            return f"✦ Good afternoon {user_tag}! A bit past morning, but hope your day is sharp."
        else:
            return f"✦ Greetings {user_tag}! Evening grid active here, hope your day is great."

    # Afternoon: 12:00 - 16:59
    if re.fullmatch(r"^(?:good\s*afternoon)\b(?:\s+(?:all|everyone|guys|gang|fam|zeno|bot|chat))?[!.]*$", low):
        if _is_cooldown_active(user_id, group_id, "ga"):
            return None
        _record_response(user_id, group_id, "ga")
        if 12 <= hour < 17:
            return f"✦ Good afternoon {user_tag}! How is the day progressing?"
        else:
            return f"✦ Greetings {user_tag}! Hope your day is going well."

    # Evening: 17:00 - 20:59
    if re.fullmatch(r"^(?:good\s*evening)\b(?:\s+(?:all|everyone|guys|gang|fam|zeno|bot|chat))?[!.]*$", low):
        if _is_cooldown_active(user_id, group_id, "ge"):
            return None
        _record_response(user_id, group_id, "ge")
        if 17 <= hour < 21:
            return f"✦ Good evening {user_tag}! Arena matches active, ready to play?"
        else:
            return f"✦ Good evening {user_tag}!"

    # Night / Good Night: 21:00 - 04:59
    if re.fullmatch(r"^(?:gn|good\s*night|nighty?\s*night)\b(?:\s+(?:all|everyone|guys|gang|fam|zeno|bot|chat))?[!.]*$", low):
        if _is_cooldown_active(user_id, group_id, "gn"):
            return None
        _record_response(user_id, group_id, "gn")
        return f"✦ Good night {user_tag}! Rest well and recharge systems."

    # 3. Standalone Greetings & Hellos
    if re.fullmatch(r"^(?:hi|hello|hey|yo|sup|hola)\b(?:\s+(?:all|everyone|guys|gang|fam|zeno|bot|chat|there))?[!.]*$", low):
        if _is_cooldown_active(user_id, group_id, "hello"):
            return None
        _record_response(user_id, group_id, "hello")
        if 5 <= hour < 12:
            return f"✦ Greetings {user_tag}! Welcome to Nova Blaze."
        elif 12 <= hour < 17:
            return f"✦ Hello {user_tag}! Hope your afternoon is going strong."
        elif 17 <= hour < 22:
            return f"✦ Hey {user_tag}! Welcome back to Nova Blaze."
        else:
            return f"✦ Hey {user_tag}! Late night grid is active."

    # 4. Standalone Farewells
    if re.fullmatch(r"^(?:bye|goodbye|cya|see\s*ya|catch\s*ya)\b(?:\s+(?:all|everyone|guys|gang|fam|zeno|bot|chat))?[!.]*$", low):
        if _is_cooldown_active(user_id, group_id, "bye"):
            return None
        _record_response(user_id, group_id, "bye")
        return f"✦ Take care {user_tag}! See you next session in Nova Blaze."

    return None
