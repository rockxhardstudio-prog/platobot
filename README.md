# Plato Group Bot — Five-command MVP

This project uses a dedicated Plato account on a real Android phone connected
over USB debugging. The backend never calls an undocumented Plato API or
inspects network traffic.

```
Plato UI -> USB phone bridge -> POST /inbox -> FastAPI/router -> SQLite/outbox
Plato UI <- USB phone bridge <- GET /outbox <- FastAPI/outbox
```

## Commands

The bot has two configured groups. Set their exact IDs with environment variables.

### Main Group

- `/spam : ID + number` — queues the stored message `number` times. Spacing variants such as `/spam:1+2` and `/spam 1 + 2` are accepted.
- `/invite` — returns the current configured invite link.
- `/summary` — reports today's Main Group messages, active members, and ranking in the configured timezone.
- `/online` — currently responds honestly that real presence is unavailable until the Android bridge can read Plato's member-list UI.

### Storage Group (admin only)

- `/spamset <numeric ID> <message>` — creates or updates a stored spam message.
- `/inviteset <https URL>` — stores the current invite link.
- `/add username:id` — creates or updates the persistent numeric ID → username mapping.

Examples:

```
/spamset 1 hello everyone
/inviteset https://example.com/invite
/add Yuvraj:1
```

## Required configuration

Create a `.env` file or set these values in your host environment:

```env
BOT_DB_PATH=bot.db
MAIN_GROUP_ID=your-main-group-id
STORAGE_GROUP_ID=your-storage-group-id
MAIN_GROUP_TITLE=Main
STORAGE_GROUP_TITLE=Storage
ADMIN_IDS=your-plato-user-id,another-admin-id
BOT_PLATO_USER_ID=dedicated-bot-account-id
PLATO_ADB_PATH=C:\Users\yuvrajnag\Desktop\plato-bot\platform-tools\adb.exe
PLATO_DEVICE_SERIAL=your-phone-adb-serial
PLATO_VISIBLE_USER_ID=phone-user
PLATO_VISIBLE_USERNAME=Phone User
PLATO_BACKEND_URL=http://127.0.0.1:8000
MAX_SPAM_REPETITIONS=20
SPAM_COOLDOWN_SECONDS=10
BOT_TIMEZONE=Asia/Kolkata
```

`ADMIN_IDS` is required before the Storage Group setup commands can be used.

## Database

SQLite persists users, permissions, deduplicated inbound messages, outbox records,
command and audit logs, stored spam messages, the current invite link, and the ID map.
Older database files are migrated to include command results.

Only non-bot Main Group messages are stored for activity reporting. Timestamps are
normalized to UTC and evaluated against the local calendar day in `BOT_TIMEZONE`.

## Running the backend

```powershell
cd C:\Users\yuvrajnag\Desktop\plato-bot\plato-bot
python -m pip install -r requirements.txt
uvicorn bot.main:app --reload --port 8000
pytest bot/tests -v
```

## Android bridge status

BlueStacks did not launch Plato reliably on this machine. The working path is
the USB phone bridge:

```powershell
cd C:\Users\yuvrajnag\Desktop\plato-bot\plato-bot
python -m uvicorn bot.main:app --reload --port 8000
python bridge\phone_bridge.py
```

Keep Plato open on either the configured Main group or Storage group while the
bridge runs. The bridge only acts when the visible Plato group title matches
`MAIN_GROUP_TITLE` or `STORAGE_GROUP_TITLE`.

The bridge currently uses the visible Plato UI controls confirmed on the phone:

- Group title: `com.plato.android:id/plato_addressee`
- Message input: `com.plato.android:id/plato_conversation_chat_box`
- Send button: `com.plato.android:id/plato_button_send`

Incoming message bubble structure still needs one live sample message in the
group to finish tuning sender/message extraction.
