from typing import Any

_sessions: dict[str, dict[str, Any]] = {}


def get_session(user_id: str) -> dict[str, Any] | None:
    return _sessions.get(user_id)


def start_session(user_id: str, command: str, initial_step: str) -> None:
    _sessions[user_id] = {
        "command": command,
        "step": initial_step,
        "data": {},
    }


def update_session(user_id: str, new_step: str | None, data_updates: dict[str, Any] | None = None) -> None:
    if user_id in _sessions:
        if new_step is None:
            end_session(user_id)
        else:
            _sessions[user_id]["step"] = new_step
            if data_updates:
                _sessions[user_id]["data"].update(data_updates)


def end_session(user_id: str) -> None:
    _sessions.pop(user_id, None)
