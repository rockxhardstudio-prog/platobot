from dataclasses import dataclass


@dataclass
class IncomingMessage:
    message_id: str
    group_id: str
    user_id: str
    username: str
    text: str
    is_self: bool = False
    timestamp: str | None = None
