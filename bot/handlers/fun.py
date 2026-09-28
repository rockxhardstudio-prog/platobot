from bot.models.message import IncomingMessage
from bot.handlers.utils import require_main
from bot.services.fun import engine

def _extract_target(args: str, require_two: bool = False) -> str | None:
    parts = [p.strip() for p in args.split() if p.strip()]
    if require_two and len(parts) >= 2:
        return " ".join(parts)
    if not require_two and len(parts) >= 1:
        return " ".join(parts)
    return None

def _handle_roast(msg: IncomingMessage, args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group: return wrong_group
    target = _extract_target(args)
    if not target: return "Usage: /roast @user"
    return engine.generate("ROAST", target, sender=msg.username)

def _handle_flirt(msg: IncomingMessage, args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group: return wrong_group
    target = _extract_target(args)
    if not target: return "Usage: /flirt @user"
    return engine.generate("FLIRT", target, sender=msg.username)

def _handle_ship(msg: IncomingMessage, args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group: return wrong_group
    target = _extract_target(args)
    if not target: return "Usage: /ship @user1 @user2"
    return engine.generate("SHIP", target, sender=msg.username)

def _handle_rate(msg: IncomingMessage, args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group: return wrong_group
    target = _extract_target(args) or "me"
    return engine.generate("RATE", target, sender=msg.username)

def _handle_bully(msg: IncomingMessage, args: str) -> str:
    wrong_group = require_main(msg)
    if wrong_group: return wrong_group
    target = _extract_target(args)
    if not target: return "Usage: /bully @user"
    return engine.generate("BULLY", target, sender=msg.username)

def _make_sticker_handler(action: str):
    def _handler(msg: IncomingMessage, args: str) -> str:
        wrong_group = require_main(msg)
        if wrong_group: return wrong_group
        target = _extract_target(args)
        if not target: return f"Usage: /{action} @user"
        return f"[STICKER:{action.upper()}] {msg.username} {action}s {target}!"
    return _handler

HANDLERS = {
    "roast": _handle_roast,
    "flirt": _handle_flirt,
    "ship": _handle_ship,
    "rate": _handle_rate,
    "bully": _handle_bully,
    "slap": _make_sticker_handler("slap"),
    "kiss": _make_sticker_handler("kiss"),
    "wink": _make_sticker_handler("wink"),
    "hug": _make_sticker_handler("hug"),
    "pat": _make_sticker_handler("pat"),
    "bonk": _make_sticker_handler("bonk"),
    "disgust": _make_sticker_handler("disgust"),
    "rip": _make_sticker_handler("rip"),
    "clap": _make_sticker_handler("clap"),
    "laugh": _make_sticker_handler("laugh"),
    "cry": _make_sticker_handler("cry"),
}
