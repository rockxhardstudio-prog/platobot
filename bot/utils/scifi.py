"""Sci-Fi UI Formatter and Aesthetic Engine for Plato Bot.

Provides clean, structured, sci-fi formatted responses using Unicode styling,
progress bars, and custom iconography without emojis.
"""

# Custom Icons specified by User:
# ➤ ↺ ✿ ❀ ❥ ❤ ✦ ★ ♫ » ➥ ✔︎ ✘ ⤬ 🗲 ⫘⫘⫘⫘⫘⫘ 🜲 ▰▰▰▱
ICON_ARROW = "➤"
ICON_RELOAD = "↺"
ICON_FLOWER = "✿"
ICON_SPARKLE = "✦"
ICON_STAR = "★"
ICON_CHEVRON = "»"
ICON_BRANCH = "➥"
ICON_CHECK = "✔︎"
ICON_CROSS = "✘"
ICON_VS = "⤬"
ICON_LIGHTNING = "🗲"
ICON_RAIL = "⫘"
ICON_CROWN = "🜲"
ICON_FILLED = "▰"
ICON_EMPTY = "▱"

LINE_DIVIDER = "⫘⫘⫘⫘⫘⫘⫘⫘⫘⫘⫘⫘⫘"

# Small caps conversion map
_NORMAL_ALPHA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_SMALL_CAPS = "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ"
_TO_SMALL_CAPS = str.maketrans(_NORMAL_ALPHA, _SMALL_CAPS)
_FROM_SMALL_CAPS = str.maketrans(_SMALL_CAPS, _NORMAL_ALPHA)


def to_small_caps(text: str) -> str:
    """Transform standard letters into stylish, readable small caps."""
    return text.translate(_TO_SMALL_CAPS)


def from_small_caps(text: str) -> str:
    """Convert small caps back to standard ASCII uppercase."""
    return text.translate(_FROM_SMALL_CAPS)


def render_progress_bar(current: int, total: int, width: int = 8, filled_char: str = ICON_FILLED, empty_char: str = ICON_EMPTY) -> str:
    """Render a sleek sci-fi progress bar: e.g. ▰▰▰▰▱▱▱▱."""
    if total <= 0:
        return empty_char * width
    ratio = max(0.0, min(1.0, float(current) / float(total)))
    filled_count = int(round(ratio * width))
    empty_count = max(0, width - filled_count)
    return f"{filled_char * filled_count}{empty_char * empty_count}"


def scifi_header(title: str, subtitle: str | None = None) -> str:
    """Generate a clean sci-fi bordered header block."""
    caps_title = to_small_caps(title.strip())
    lines = [LINE_DIVIDER, f"{ICON_SPARKLE} {caps_title} {ICON_SPARKLE}"]
    if subtitle:
        lines.append(f"{ICON_BRANCH} {subtitle.strip()}")
    lines.append(LINE_DIVIDER)
    return "\n".join(lines)


def scifi_field(label: str, value: object, indent: bool = False) -> str:
    """Format a single key-value field line."""
    prefix = f"  {ICON_BRANCH} " if indent else f"{ICON_ARROW} "
    return f"{prefix}{to_small_caps(label)} :: {value}"


def scifi_bullet(text: str) -> str:
    """Format an action or list item."""
    return f"{ICON_ARROW} {text}"


def scifi_sub_bullet(text: str) -> str:
    """Format a sub-item or description."""
    return f"  {ICON_BRANCH} {text}"


def scifi_notice(title: str, reason: str, level: int = 1, max_level: int = 5) -> str:
    """Format a warning or system alert."""
    bar = render_progress_bar(level, max_level, width=5)
    return "\n".join([
        f"{ICON_LIGHTNING} {to_small_caps(title)}",
        f"{ICON_BRANCH} Reason: {reason}",
        f"{ICON_BRANCH} Level: {bar} [{level}/{max_level}]",
    ])


def scifi_transliterate_to_ascii(text: str) -> str:
    """Safe fallback for ADB shell typing when non-ASCII keyboard is unavailable."""
    res = text
    # Transliterate icons
    res = res.replace("⫘", "=")
    res = res.replace(ICON_FILLED, "#")
    res = res.replace(ICON_EMPTY, "-")
    res = res.replace(ICON_SPARKLE, "*")
    res = res.replace(ICON_STAR, "*")
    res = res.replace(ICON_ARROW, ">")
    res = res.replace(ICON_BRANCH, ">")
    res = res.replace(ICON_CHEVRON, ">")
    res = res.replace(ICON_CHECK, "[OK]")
    res = res.replace(ICON_CROSS, "[X]")
    res = res.replace(ICON_VS, "vs")
    res = res.replace(ICON_LIGHTNING, "[!]")
    res = res.replace(ICON_CROWN, "[WIN]")
    res = res.replace(ICON_RELOAD, "[R]")
    res = res.replace(ICON_FLOWER, "*")
    res = res.replace("❀", "*").replace("❥", "<3").replace("❤", "<3").replace("♫", "[~]")
    # Transliterate small caps to ASCII uppercase
    res = from_small_caps(res)
    return res
