import time

_last_call: dict[tuple[str, str], float] = {}


def allow(user_id: str, command: str, window_seconds: float) -> bool:
    key = (user_id, command)
    now = time.time()
    last = _last_call.get(key, 0.0)
    if now - last < window_seconds:
        return False
    _last_call[key] = now
    return True
