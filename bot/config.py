import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    candidates = [
        Path(".env"),
        Path(__file__).resolve().parents[1] / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    for env_file in candidates:
        if env_file.is_file():
            for raw_line in env_file.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
            break


def _parse_ids(raw: str) -> set[str]:
    return {value.strip() for value in raw.split(",") if value.strip()}


_load_dotenv()


@dataclass
class Config:
    db_path: str = os.getenv("BOT_DB_PATH", "bot.db")
    bot_plato_user_id: str = os.getenv("BOT_PLATO_USER_ID", "")
    main_group_id: str = os.getenv("MAIN_GROUP_ID", "")
    storage_group_id: str = os.getenv("STORAGE_GROUP_ID", "")
    main_group_title: str = os.getenv("MAIN_GROUP_TITLE", "Main")
    storage_group_title: str = os.getenv("STORAGE_GROUP_TITLE", "Storage")
    bridge_adb_path: str = os.getenv(
        "PLATO_ADB_PATH",
        str(Path(__file__).resolve().parents[2] / "platform-tools" / "adb.exe"),
    )
    bridge_device_serial: str = os.getenv("PLATO_DEVICE_SERIAL", "")
    bridge_visible_user_id: str = os.getenv("PLATO_VISIBLE_USER_ID", "phone-user")
    bridge_visible_username: str = os.getenv("PLATO_VISIBLE_USERNAME", "Phone User")
    bridge_backend_url: str = os.getenv("PLATO_BACKEND_URL", "http://127.0.0.1:8000")
    admin_ids: set[str] = field(default_factory=lambda: _parse_ids(os.getenv("ADMIN_IDS", "")))
    max_spam_repetitions: int = int(os.getenv("MAX_SPAM_REPETITIONS", "20"))
    spam_cooldown_seconds: float = float(os.getenv("SPAM_COOLDOWN_SECONDS", "10"))
    bot_timezone: str = os.getenv("BOT_TIMEZONE", "Asia/Kolkata")


config = Config()
