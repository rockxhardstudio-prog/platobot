import math
import sqlite3
from datetime import datetime, timedelta, timezone
from bot.database.db import get_conn, transaction
from bot.services import community

GAME_SEATS_PER_TAB: dict[str, int] = {
    "bingo": 15,
    "werewolf": 9,
    "ww": 9,
    "ocho": 4,
    "poker": 6,
    "spades": 4,
    "ludo": 4,
    "pool": 2,
    "billiards": 2,
    "bb": 2,
    "bankroll": 4,
    "draw": 8,
    "smacktalk": 6,
}


def get_active_tournament() -> sqlite3.Row | None:
    return get_conn().execute("SELECT * FROM tournaments WHERE is_active = 1").fetchone()


def create_tournament(name: str, user_id: str) -> None:
    with transaction() as conn:
        conn.execute("UPDATE tournaments SET is_active = 0 WHERE is_active = 1")
        conn.execute(
            "INSERT INTO tournaments (name, created_by, is_active) VALUES (?, ?, 1)",
            (name, user_id),
        )


def update_active_tournament_field(field: str, value: str | int) -> bool:
    allowed_fields = {
        "game", "event_date", "event_time", "registration_time",
        "format", "max_slots", "prize_info", "description_text",
        "rules_text", "host_mode", "host",
    }
    if field not in allowed_fields:
        return False
    if field == "max_slots":
        try:
            val_int = int(value)
            if val_int <= 0:
                return False
            value = val_int
        except (ValueError, TypeError):
            return False

    with transaction() as conn:
        row = conn.execute("SELECT id FROM tournaments WHERE is_active = 1").fetchone()
        if not row:
            return False
        t_id = row["id"]
        conn.execute(f"UPDATE tournaments SET {field} = ?, updated_at = datetime('now') WHERE is_active = 1", (value,))

        if field == "max_slots" and value is not None:
            count_reg = conn.execute(
                "SELECT COUNT(*) as c FROM registrations WHERE tournament_id = ? AND status = 'registered'",
                (t_id,),
            ).fetchone()["c"]
            available = value - count_reg
            if available > 0:
                waitlisted_rows = conn.execute(
                    "SELECT id FROM registrations WHERE tournament_id = ? AND status = 'waitlisted' ORDER BY registered_at ASC LIMIT ?",
                    (t_id, available),
                ).fetchall()
                for w in waitlisted_rows:
                    conn.execute("UPDATE registrations SET status = 'registered' WHERE id = ?", (w["id"],))
    return True


def clear_active_tournament() -> bool:
    with transaction() as conn:
        row = conn.execute("SELECT id FROM tournaments WHERE is_active = 1").fetchone()
        if not row:
            return False
        conn.execute("UPDATE tournaments SET status = 'completed', is_active = 0, updated_at = datetime('now') WHERE is_active = 1")
    return True


def set_active_tournament_status(status: str) -> bool:
    allowed_statuses = {"draft", "open", "closed", "ongoing", "completed"}
    if status not in allowed_statuses:
        return False
    with transaction() as conn:
        row = conn.execute("SELECT id FROM tournaments WHERE is_active = 1").fetchone()
        if not row:
            return False
        conn.execute("UPDATE tournaments SET status = ?, updated_at = datetime('now') WHERE is_active = 1", (status,))
    return True


def register_user(user_id: str, username: str, game_tag: str | None) -> str:
    with transaction() as conn:
        tourney = conn.execute("SELECT id, status, max_slots FROM tournaments WHERE is_active = 1").fetchone()
        if not tourney:
            return "No active tournament right now."
        if tourney["status"] == "paused":
            return "⏸️ Tournament is currently PAUSED / ON HOLD by staff. Registrations are on hold."
        if tourney["status"] != "open":
            return "Registration is currently closed."

        t_id = tourney["id"]

        existing = conn.execute(
            "SELECT id, status FROM registrations WHERE tournament_id = ? AND user_id = ?",
            (t_id, user_id),
        ).fetchone()
        if existing and existing["status"] in ("registered", "waitlisted"):
            return f"@{username} You are already {existing['status']} for this tournament."

        count_row = conn.execute(
            "SELECT COUNT(*) as c FROM registrations WHERE tournament_id = ? AND status = 'registered'",
            (t_id,),
        ).fetchone()
        current_registered = count_row["c"]

        status = "registered"
        if tourney["max_slots"] is not None and current_registered >= tourney["max_slots"]:
            status = "waitlisted"

        if existing and existing["status"] == "cancelled":
            conn.execute(
                "UPDATE registrations SET status = ?, username = ?, game_tag = ?, registered_at = datetime('now') WHERE id = ?",
                (status, username, game_tag, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO registrations (tournament_id, user_id, username, game_tag, status) VALUES (?, ?, ?, ?, ?)",
                (t_id, user_id, username, game_tag, status),
            )

        if status == "waitlisted":
            waitlist_pos_row = conn.execute(
                "SELECT COUNT(*) as c FROM registrations WHERE tournament_id = ? AND status = 'waitlisted'",
                (t_id,),
            ).fetchone()
            return f"@{username} Added to waitlist (position {waitlist_pos_row['c']})."

        slots_text = f" ({current_registered + 1}/{tourney['max_slots']})" if tourney["max_slots"] else ""
        return f"@{username} Registered successfully!{slots_text}"


def unregister_user(user_id: str, username: str = "") -> str:
    with transaction() as conn:
        tourney = conn.execute("SELECT id, max_slots FROM tournaments WHERE is_active = 1").fetchone()
        if not tourney:
            return "No active tournament right now."

        t_id = tourney["id"]

        existing = conn.execute(
            "SELECT id, status, username FROM registrations WHERE tournament_id = ? AND user_id = ? AND status IN ('registered', 'waitlisted')",
            (t_id, user_id),
        ).fetchone()
        if not existing:
            user_tag = f"@{username} " if username else ""
            return f"{user_tag}You are not registered for the active tournament."

        uname = existing["username"] or username or user_id
        conn.execute("UPDATE registrations SET status = 'cancelled' WHERE id = ?", (existing["id"],))

        if existing["status"] == "registered":
            waitlisted = conn.execute(
                "SELECT id FROM registrations WHERE tournament_id = ? AND status = 'waitlisted' ORDER BY registered_at ASC LIMIT 1",
                (t_id,),
            ).fetchone()
            if waitlisted:
                conn.execute("UPDATE registrations SET status = 'registered' WHERE id = ?", (waitlisted["id"],))

        return f"@{uname} Your registration has been cancelled."


def get_participants() -> list[sqlite3.Row]:
    tourney = get_active_tournament()
    if not tourney:
        return []
    return get_conn().execute(
        "SELECT user_id, username, game_tag, status FROM registrations WHERE tournament_id = ? AND status IN ('registered', 'waitlisted') ORDER BY status, registered_at ASC",
        (tourney["id"],),
    ).fetchall()


def resolve_winner_identity(target: str) -> tuple[str, str]:
    clean = (target or "").strip().lstrip("@")
    if not clean:
        return ("unknown", "unknown")
    conn = get_conn()
    row = conn.execute(
        "SELECT user_id, username FROM users WHERE LOWER(user_id) = LOWER(?) OR LOWER(username) = LOWER(?) ORDER BY created_at DESC LIMIT 1",
        (clean, clean),
    ).fetchone()
    if row:
        return (str(row["user_id"]), str(row["username"]))

    reg = conn.execute(
        "SELECT user_id, username FROM registrations WHERE LOWER(user_id) = LOWER(?) OR LOWER(username) = LOWER(?) ORDER BY registered_at DESC LIMIT 1",
        (clean, clean),
    ).fetchone()
    if reg:
        return (str(reg["user_id"]), str(reg["username"]))

    xp = conn.execute(
        "SELECT user_id, username FROM xp_profiles WHERE LOWER(user_id) = LOWER(?) OR LOWER(username) = LOWER(?) LIMIT 1",
        (clean, clean),
    ).fetchone()
    if xp:
        return (str(xp["user_id"]), str(xp["username"]))

    umap = conn.execute(
        "SELECT id, username FROM user_id_map WHERE LOWER(username) = LOWER(?) OR CAST(id AS TEXT) = ? LIMIT 1",
        (clean, clean),
    ).fetchone()
    if umap:
        return (str(umap["id"]), str(umap["username"]))

    return (clean, clean)


def add_winner(target: str, tab_label: str | None, actor_id: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    exact_uid, exact_uname = resolve_winner_identity(target)
    tourney = get_active_tournament()
    t_name = str(tourney["name"]) if tourney and tourney["name"] else "Giveaway / Tourney"

    with transaction() as conn:
        existing_count = conn.execute("SELECT COUNT(*) AS cnt FROM tourney_winners").fetchone()["cnt"]
        label = (tab_label or "").strip() or f"Tab #{int(existing_count) + 1}"
        cursor = conn.execute(
            "INSERT INTO tourney_winners (tourney_name, tab_label, user_id, username, added_by) VALUES (?, ?, ?, ?, ?)",
            (t_name, label, exact_uid, exact_uname, actor_id),
        )
        new_id = cursor.lastrowid

    all_winners = get_winners()
    added_entry = next(
        (w for w in all_winners if w["id"] == new_id),
        {"id": new_id, "tourney_name": t_name, "tab_label": label, "user_id": exact_uid, "username": exact_uname},
    )
    return added_entry, all_winners


def get_winners() -> list[dict[str, object]]:
    rows = get_conn().execute(
        "SELECT id, tourney_name, tab_label, user_id, username, added_by, created_at FROM tourney_winners ORDER BY id ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def remove_winner(identifier: str) -> bool:
    clean = (identifier or "").strip().lstrip("#").lstrip("@")
    if not clean:
        return False
    all_w = get_winners()
    if not all_w:
        return False

    target_db_id: int | None = None
    try:
        num = int(clean)
        if 1 <= num <= len(all_w):
            target_db_id = int(all_w[num - 1]["id"])
        else:
            target_db_id = num
    except ValueError:
        for w in reversed(all_w):
            if str(w["username"]).lower() == clean.lower() or str(w["user_id"]).lower() == clean.lower():
                target_db_id = int(w["id"])
                break

    if target_db_id is None:
        return False

    with transaction() as conn:
        cur = conn.execute("DELETE FROM tourney_winners WHERE id = ?", (target_db_id,))
        return cur.rowcount > 0


def clear_winners() -> int:
    with transaction() as conn:
        cur = conn.execute("DELETE FROM tourney_winners")
        return cur.rowcount


def format_winners_list(winners: list[dict[str, object]], header: str = "🜲 WINNERS LIST") -> str:
    if not winners:
        return "🜲 No winners recorded yet."
    lines = [header]
    for idx, w in enumerate(winners, 1):
        uid = str(w["user_id"])
        uname = str(w["username"])
        lines.append(f"{idx}. {w['tab_label']}: @{uname} [ID: {uid}]")
    return "\n".join(lines)


def format_compact_winners_names(winners: list[dict[str, object]]) -> str:
    if not winners:
        return "None yet"
    return ", ".join(str(w["username"]) for w in winners)


# ─────────────────────────────────────────────────────────────────────────────
# TYPE 1: SMART ELIMINATION BRACKET TOURNAMENT ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def calculate_total_rounds(slots: int) -> int:
    return max(1, math.ceil(math.log2(max(2, int(slots)))))


def quick_create_tournament(slots: int, game: str, name: str, actor_id: str, rules_text: str | None = None) -> dict[str, object]:
    with transaction() as conn:
        conn.execute("UPDATE tournaments SET is_active = 0 WHERE is_active = 1")
        conn.execute("UPDATE giveaways SET is_active = 0 WHERE is_active = 1")
        conn.execute("DELETE FROM tourney_winners")
        cur = conn.execute(
            "INSERT INTO tournaments (name, game, max_slots, rules_text, status, is_active, created_by) VALUES (?, ?, ?, ?, 'open', 1, ?)",
            (name, game, slots, rules_text, actor_id),
        )
        t_id = cur.lastrowid
    if rules_text:
        community.set_tourney_rules(rules_text, actor_id)
    return {
        "id": t_id,
        "name": name,
        "game": game,
        "max_slots": slots,
        "total_rounds": calculate_total_rounds(slots),
    }


def get_current_round(tournament_id: int) -> sqlite3.Row | None:
    return get_conn().execute(
        "SELECT * FROM tourney_rounds WHERE tournament_id = ? ORDER BY round_number DESC LIMIT 1",
        (tournament_id,),
    ).fetchone()


def set_round_rules(game: str | None, rules: str, actor_id: str) -> str:
    community.set_tourney_rules(rules, actor_id)
    tourney = get_active_tournament()
    if tourney:
        if game:
            update_active_tournament_field("game", game)
        update_active_tournament_field("rules_text", rules)
        rnd = get_current_round(int(tourney["id"]))
        if rnd and rnd["status"] == "active":
            with transaction() as conn:
                conn.execute(
                    "UPDATE tourney_rounds SET game = COALESCE(?, game), rules_text = ? WHERE id = ?",
                    (game, rules, rnd["id"]),
                )
    g_label = f" ({game})" if game else ""
    return f"✦ Round Rules{g_label} ✦\n{rules}"


def _create_round_matches(
    tournament_id: int,
    round_num: int,
    players: list[tuple[str, str]],
    game: str,
    rules: str,
) -> str:
    from bot.utils.scifi import LINE_DIVIDER, to_small_caps
    now_iso = datetime.now(timezone.utc).isoformat()
    tourney = get_active_tournament()
    t_name = str(tourney["name"]) if tourney else "Tournament"

    with transaction() as conn:
        conn.execute(
            "UPDATE tourney_rounds SET status = 'completed', completed_at = datetime('now') WHERE tournament_id = ? AND status = 'active'",
            (tournament_id,),
        )
        conn.execute(
            "INSERT INTO tourney_rounds (tournament_id, round_number, game, rules_text, status, started_at) VALUES (?, ?, ?, ?, 'active', ?)",
            (tournament_id, round_num, game, rules, now_iso),
        )
        conn.execute("DELETE FROM tourney_winners")

        match_lines: list[str] = []
        match_idx = 1

        # If odd number of players (e.g., 7, 5, 3 after a double-AFK or odd bracket),
        # give the 1st player (fastest winner from previous round / top seed) an automatic BYE!
        paired_players = list(players)
        bye_player: tuple[str, str] | None = None
        if len(paired_players) > 1 and len(paired_players) % 2 == 1:
            bye_player = paired_players.pop(0)

        for i in range(0, len(paired_players), 2):
            p1_id, p1_name = paired_players[i]
            p2_id, p2_name = paired_players[i + 1]
            conn.execute(
                "INSERT INTO tourney_matches (tournament_id, round_number, match_number, player1_id, player1_name, player2_id, player2_name, status, p1_last_active, p2_last_active, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
                (tournament_id, round_num, match_idx, p1_id, p1_name, p2_id, p2_name, now_iso, now_iso, now_iso),
            )
            match_lines.append(f"  ➤ M{match_idx}: @{p1_name} ⤬ @{p2_name}")
            match_idx += 1

        if bye_player:
            b_id, b_name = bye_player
            conn.execute(
                "INSERT INTO tourney_matches (tournament_id, round_number, match_number, player1_id, player1_name, player2_id, player2_name, winner_id, winner_name, status, win_reason, completed_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, 'bye', 'bye', ?, ?)",
                (tournament_id, round_num, match_idx, b_id, b_name, b_id, b_name, now_iso, now_iso),
            )
            conn.execute(
                "INSERT INTO tourney_winners (tourney_name, tab_label, user_id, username, added_by) VALUES (?, ?, ?, ?, 'system')",
                (t_name, f"R{round_num} M{match_idx} (BYE)", b_id, b_name),
            )
            match_lines.append(f"  ➤ M{match_idx}: @{b_name} [✔︎ BYE - Auto Advances]")

    header = [
        LINE_DIVIDER,
        f"✦ {to_small_caps(t_name)} // ROUND {round_num} ✦",
        f"➥ {len(players)} Players Active",
        LINE_DIVIDER,
        f"➤ Game  :: {game or 'TBD'}",
    ]
    if rules:
        header.append(f"➤ Rules :: {rules}")
    header.append("✦ MATCHUPS ✦")
    header.extend(match_lines)
    header.append("➥ Winner of each match type: /iwon")
    return "\n".join(header)


def start_tournament_or_next_round(
    actor_id: str,
    new_game: str | None = None,
    new_rules: str | None = None,
) -> tuple[bool, str]:
    tourney = get_active_tournament()
    if not tourney:
        return False, "No active tournament found. Create one with /createtourney <slots> <game> <title>."

    t_id = int(tourney["id"])
    last_rnd = get_current_round(t_id)

    if new_game:
        update_active_tournament_field("game", new_game)
    if new_rules:
        update_active_tournament_field("rules_text", new_rules)
        community.set_tourney_rules(new_rules, actor_id)

    tourney = get_active_tournament()
    game = str(new_game or tourney["game"] or "Plato Game")
    rules = str(new_rules or tourney["rules_text"] or community.get_tourney_rules() or "Standard fair-play rules apply.")

    if not last_rnd:
        # Starting Round 1 from registered participants
        regs = get_conn().execute(
            "SELECT user_id, username FROM registrations WHERE tournament_id = ? AND status = 'registered' ORDER BY registered_at ASC",
            (t_id,),
        ).fetchall()
        if len(regs) < 2:
            return False, f"Need at least 2 registered players to start Round 1 (currently {len(regs)})."
        set_active_tournament_status("ongoing")
        players = [(str(r["user_id"]), str(r["username"])) for r in regs]
        announcement = _create_round_matches(t_id, 1, players, game, rules)
        return True, announcement

    # Starting Next Round from previous round's winners!
    prev_round_num = int(last_rnd["round_number"])
    matches = get_conn().execute(
        "SELECT * FROM tourney_matches WHERE tournament_id = ? AND round_number = ? ORDER BY match_number ASC",
        (t_id, prev_round_num),
    ).fetchall()
    pending = [m for m in matches if m["status"] == "pending"]
    if pending:
        return (
            False,
            f"Round {prev_round_num} still has {len(pending)} pending match(es). Use /checkafk or /forcewin @user first.",
        )

    advancing: list[tuple[str, str]] = []
    for m in matches:
        if m["winner_id"] and m["winner_name"]:
            advancing.append((str(m["winner_id"]), str(m["winner_name"])))

    if len(advancing) == 0:
        clear_active_tournament()
        return False, "No winners advanced from the previous round. Tournament ended."
    if len(advancing) == 1:
        champ_id, champ_name = advancing[0]
        set_active_tournament_status("completed")
        return True, f"👑 TOURNAMENT CHAMPION: @{champ_name} [ID: {champ_id}]! Congratulations!"

    next_rnd_num = prev_round_num + 1
    announcement = _create_round_matches(t_id, next_rnd_num, advancing, game, rules)
    return True, announcement


def record_match_win(
    caller_id: str,
    caller_name: str,
    is_staff_override: bool = False,
    target_winner: str | None = None,
    win_reason: str = "played",
) -> tuple[bool, str]:
    tourney = get_active_tournament()
    if tourney and tourney["status"] == "paused":
        return False, "⏸️ Tournament is currently PAUSED / ON HOLD by staff. Win declarations are on hold."
    if not tourney or tourney["status"] not in ("ongoing", "open", "closed"):
        # Check if there is an active giveaway instead!
        ga = get_active_giveaway()
        if ga:
            if ga["status"] == "paused":
                return False, "⏸️ Giveaway is currently PAUSED / ON HOLD by staff. Win declarations are on hold."
            winner_target = target_winner if (is_staff_override and target_winner) else caller_name
            return record_giveaway_winner(winner_target, caller_id)
        return False, "No active tournament or giveaway match is currently running."

    t_id = int(tourney["id"])
    t_name = str(tourney["name"])
    rnd = get_current_round(t_id)
    if not rnd:
        return False, "The tournament has not started its first round yet."

    rnd_num = int(rnd["round_number"])
    lookup_target = (target_winner or caller_name or caller_id).strip().lstrip("@")
    clean_caller_id = (caller_id or "").strip().lstrip("@").lower()
    clean_lookup = lookup_target.lower()

    conn = get_conn()
    matches = conn.execute(
        "SELECT * FROM tourney_matches WHERE tournament_id = ? AND round_number = ? ORDER BY match_number ASC",
        (t_id, rnd_num),
    ).fetchall()

    target_match: sqlite3.Row | None = None
    winner_uid = ""
    winner_uname = ""

    for m in matches:
        p1_id = str(m["player1_id"] or "")
        p1_name = str(m["player1_name"] or "")
        p2_id = str(m["player2_id"] or "")
        p2_name = str(m["player2_name"] or "")

        p1_match = clean_lookup in (p1_id.lower(), p1_name.lower()) or (not is_staff_override and clean_caller_id in (p1_id.lower(), p1_name.lower()))
        p2_match = clean_lookup in (p2_id.lower(), p2_name.lower()) or (not is_staff_override and clean_caller_id in (p2_id.lower(), p2_name.lower()))

        if p1_match or p2_match:
            target_match = m
            if p1_match:
                winner_uid, winner_uname = p1_id, p1_name
            else:
                winner_uid, winner_uname = p2_id, p2_name
            break

    if not target_match:
        return False, f"@{caller_name} You do not have an active match in Round {rnd_num}."

    if target_match["status"] != "pending" and not is_staff_override:
        return (
            False,
            f"Match #{target_match['match_number']} is already recorded (Winner: @{target_match['winner_name']}). Use /reportissue if there is a mistake.",
        )

    m_num = int(target_match["match_number"])
    now_iso = datetime.now(timezone.utc).isoformat()

    with transaction() as tconn:
        tconn.execute(
            "UPDATE tourney_matches SET winner_id = ?, winner_name = ?, status = 'completed', win_reason = ?, completed_at = ? WHERE id = ?",
            (winner_uid, winner_uname, win_reason, now_iso, target_match["id"]),
        )
        # Ensure no duplicate entry for the same match in tourney_winners
        tconn.execute(
            "DELETE FROM tourney_winners WHERE tab_label = ?",
            (f"R{rnd_num} M{m_num}",),
        )
        tconn.execute(
            "INSERT INTO tourney_winners (tourney_name, tab_label, user_id, username, added_by) VALUES (?, ?, ?, ?, ?)",
            (t_name, f"R{rnd_num} M{m_num}", winner_uid, winner_uname, caller_id),
        )

    updated_matches = conn.execute(
        "SELECT * FROM tourney_matches WHERE tournament_id = ? AND round_number = ? ORDER BY match_number ASC",
        (t_id, rnd_num),
    ).fetchall()
    pending_left = [m for m in updated_matches if m["status"] == "pending"]
    round_winners = get_winners()
    winners_names_str = format_compact_winners_names(round_winners)

    lines = [
        f"✔︎ R{rnd_num} Match #{m_num} Winner: @{winner_uname} [ID: {winner_uid}]!",
        f"🜲 Round {rnd_num} Winners ({len(round_winners)}/{len(updated_matches)}): {winners_names_str}",
    ]

    if not pending_left:
        # All matches in this round are finished!
        advancing = [
            (str(m["winner_id"]), str(m["winner_name"]))
            for m in updated_matches
            if m["winner_id"] and m["winner_name"]
        ]
        if len(advancing) == 1:
            champ_id, champ_name = advancing[0]
            set_active_tournament_status("completed")
            lines.append(f"\n🜲 TOURNAMENT CHAMPION: @{champ_name} [ID: {champ_id}]! GG!")
        elif len(advancing) > 1:
            next_rnd_num = rnd_num + 1
            game = str(tourney["game"] or "Plato Game")
            rules = str(tourney["rules_text"] or community.get_tourney_rules() or "Standard fair-play rules apply.")
            next_round_text = _create_round_matches(t_id, next_rnd_num, advancing, game, rules)
            lines.append(f"\n✦ All Round {rnd_num} matches complete! Advancing to Round {next_rnd_num}:\n{next_round_text}")
    else:
        lines.append(f"➥ {len(pending_left)} match(es) remaining in Round {rnd_num}.")

    return True, "\n".join(lines)


def touch_player_activity(user_id: str, username: str) -> None:
    tourney = get_active_tournament()
    if not tourney or tourney["status"] != "ongoing":
        return
    t_id = int(tourney["id"])
    rnd = get_current_round(t_id)
    if not rnd or rnd["status"] != "active":
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    uid_low = (user_id or "").strip().lower()
    uname_low = (username or "").strip().lower()
    with transaction() as conn:
        conn.execute(
            "UPDATE tourney_matches SET p1_last_active = ? WHERE tournament_id = ? AND round_number = ? AND status = 'pending' AND (LOWER(player1_id) = ? OR LOWER(player1_name) = ?)",
            (now_iso, t_id, int(rnd["round_number"]), uid_low, uname_low),
        )
        conn.execute(
            "UPDATE tourney_matches SET p2_last_active = ? WHERE tournament_id = ? AND round_number = ? AND status = 'pending' AND (LOWER(player2_id) = ? OR LOWER(player2_name) = ?)",
            (now_iso, t_id, int(rnd["round_number"]), uid_low, uname_low),
        )


def report_match_issue(user_id: str, username: str, issue_text: str) -> str:
    clean_issue = (issue_text or "").strip() or "Opponent is AFK / offline"
    tourney = get_active_tournament()
    t_id = int(tourney["id"]) if tourney else None
    rnd = get_current_round(t_id) if t_id else None
    rnd_num = int(rnd["round_number"]) if rnd else None
    m_num: int | None = None
    opp_name: str | None = None
    now_iso = datetime.now(timezone.utc).isoformat()

    if t_id and rnd_num:
        matches = get_conn().execute(
            "SELECT * FROM tourney_matches WHERE tournament_id = ? AND round_number = ? AND status = 'pending'",
            (t_id, rnd_num),
        ).fetchall()
        u_low = username.strip().lower()
        id_low = user_id.strip().lower()
        for m in matches:
            if u_low in (str(m["player1_name"]).lower(), str(m["player1_id"]).lower()) or id_low in (str(m["player1_name"]).lower(), str(m["player1_id"]).lower()):
                m_num = int(m["match_number"])
                opp_name = str(m["player2_name"] or "")
                break
            if u_low in (str(m["player2_name"]).lower(), str(m["player2_id"]).lower()) or id_low in (str(m["player2_name"]).lower(), str(m["player2_id"]).lower()):
                m_num = int(m["match_number"])
                opp_name = str(m["player1_name"] or "")
                break

    with transaction() as conn:
        conn.execute(
            "INSERT INTO tourney_issues (tournament_id, round_number, match_number, reporter_id, reporter_name, opponent_name, issue_text, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)",
            (t_id, rnd_num, m_num, user_id, username, opp_name, clean_issue, now_iso),
        )
        if t_id and rnd_num and m_num and opp_name:
            conn.execute(
                "UPDATE tourney_matches SET afk_reported_against = ?, afk_reported_at = ? WHERE tournament_id = ? AND round_number = ? AND match_number = ? AND status = 'pending'",
                (opp_name, now_iso, t_id, rnd_num, m_num),
            )

    if m_num and opp_name:
        return (
            f"🚨 Issue logged for R{rnd_num} Match #{m_num} (@{username} vs @{opp_name}): \"{clean_issue}\"\n"
            f"⏱ 5-minute AFK timer started for @{opp_name}. If @{opp_name} stays AFK > 5 mins, @{username} gets an automatic walkover win!"
        )
    return f"🚨 Issue reported to staff by @{username}: \"{clean_issue}\""


def check_and_resolve_afk(timeout_minutes: float = 5.0, force_all_pending: bool = False) -> str | None:
    tourney = get_active_tournament()
    if not tourney or tourney["status"] != "ongoing":
        return None
    t_id = int(tourney["id"])
    t_name = str(tourney["name"])
    rnd = get_current_round(t_id)
    if not rnd or rnd["status"] != "active":
        return None

    rnd_num = int(rnd["round_number"])
    now = datetime.now(timezone.utc)
    conn = get_conn()
    pending = conn.execute(
        "SELECT * FROM tourney_matches WHERE tournament_id = ? AND round_number = ? AND status = 'pending' ORDER BY match_number ASC",
        (t_id, rnd_num),
    ).fetchall()
    if not pending:
        return None

    resolved_msgs: list[str] = []
    for m in pending:
        m_num = int(m["match_number"])
        p1_id, p1_name = str(m["player1_id"]), str(m["player1_name"])
        p2_id, p2_name = str(m["player2_id"] or ""), str(m["player2_name"] or "")
        rep_against = str(m["afk_reported_against"] or "")
        rep_at_raw = str(m["afk_reported_at"] or "")

        if rep_against and rep_at_raw:
            try:
                rep_dt = datetime.fromisoformat(rep_at_raw.replace("Z", "+00:00"))
                elapsed_mins = (now - rep_dt).total_seconds() / 60.0
            except ValueError:
                elapsed_mins = timeout_minutes + 1.0

            if force_all_pending or elapsed_mins >= timeout_minutes:
                if rep_against.lower() == p2_name.lower():
                    w_uid, w_uname, afk_uname = p1_id, p1_name, p2_name
                else:
                    w_uid, w_uname, afk_uname = p2_id, p2_name, p1_name
                with transaction() as tconn:
                    tconn.execute(
                        "UPDATE tourney_matches SET winner_id=?, winner_name=?, status='walkover', win_reason='afk_walkover', completed_at=? WHERE id=?",
                        (w_uid, w_uname, now.isoformat(), m["id"]),
                    )
                    tconn.execute(
                        "INSERT INTO tourney_winners (tourney_name, tab_label, user_id, username, added_by) VALUES (?, ?, ?, ?, 'afk_system')",
                        (t_name, f"R{rnd_num} M{m_num} (Walkover)", w_uid, w_uname),
                    )
                resolved_msgs.append(f"⏱ M{m_num}: @{w_uname} wins by Walkover (@{afk_uname} AFK > 5m)!")
                continue

        # Check player last_active timestamps if no report or report not yet expired
        def _mins_since(ts_str: str) -> float:
            if not ts_str:
                return 0.0
            try:
                dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                return (now - dt).total_seconds() / 60.0
            except ValueError:
                return 0.0

        p1_idle = _mins_since(str(m["p1_last_active"] or ""))
        p2_idle = _mins_since(str(m["p2_last_active"] or ""))

        if force_all_pending or (timeout_minutes > 0 and p1_idle >= timeout_minutes and p2_idle >= timeout_minutes):
            # Both players went AFK in this match -> mark double_afk so remaining winners advance (e.g., 6 instead of 8!)
            with transaction() as tconn:
                tconn.execute(
                    "UPDATE tourney_matches SET status='double_afk', win_reason='both_afk', completed_at=? WHERE id=?",
                    (now.isoformat(), m["id"]),
                )
            resolved_msgs.append(f"⚠️ M{m_num}: Both @{p1_name} & @{p2_name} AFK (Double AFK) — match voided.")
        elif timeout_minutes > 0 and (p1_idle >= timeout_minutes or p2_idle >= timeout_minutes):
            if p2_idle >= timeout_minutes:
                w_uid, w_uname, afk_uname = p1_id, p1_name, p2_name
            else:
                w_uid, w_uname, afk_uname = p2_id, p2_name, p1_name
            with transaction() as tconn:
                tconn.execute(
                    "UPDATE tourney_matches SET winner_id=?, winner_name=?, status='walkover', win_reason='afk_walkover', completed_at=? WHERE id=?",
                    (w_uid, w_uname, now.isoformat(), m["id"]),
                )
                tconn.execute(
                    "INSERT INTO tourney_winners (tourney_name, tab_label, user_id, username, added_by) VALUES (?, ?, ?, ?, 'afk_system')",
                    (t_name, f"R{rnd_num} M{m_num} (Walkover)", w_uid, w_uname),
                )
            resolved_msgs.append(f"⏱ M{m_num}: @{w_uname} wins by Walkover (@{afk_uname} AFK > 5m)!")

    if not resolved_msgs:
        return None

    # Check if all matches in this round are now done
    after_pending = conn.execute(
        "SELECT COUNT(*) AS c FROM tourney_matches WHERE tournament_id = ? AND round_number = ? AND status = 'pending'",
        (t_id, rnd_num),
    ).fetchone()["c"]
    round_winners = get_winners()
    resolved_msgs.append(f"🏆 Round {rnd_num} Winners: {format_compact_winners_names(round_winners)}")

    if int(after_pending) == 0:
        ok, next_msg = start_tournament_or_next_round("afk_system")
        if ok:
            resolved_msgs.append(f"\n{next_msg}")

    return "\n".join(resolved_msgs)


def disqualify_player(target_user: str, actor_id: str) -> str:
    tourney = get_active_tournament()
    if not tourney:
        return "No active tournament found."
    t_id = int(tourney["id"])
    t_name = str(tourney["name"])
    rnd = get_current_round(t_id)
    if not rnd:
        return "Tournament has not started a round yet."
    rnd_num = int(rnd["round_number"])
    clean = target_user.strip().lstrip("@").lower()
    conn = get_conn()
    matches = conn.execute(
        "SELECT * FROM tourney_matches WHERE tournament_id = ? AND round_number = ? AND status = 'pending'",
        (t_id, rnd_num),
    ).fetchall()

    for m in matches:
        p1_id, p1_name = str(m["player1_id"]), str(m["player1_name"])
        p2_id, p2_name = str(m["player2_id"] or ""), str(m["player2_name"] or "")
        if clean in (p1_id.lower(), p1_name.lower()):
            return record_match_win(actor_id, p2_name, is_staff_override=True, target_winner=p2_name, win_reason="opponent_dq")[1]
        if clean in (p2_id.lower(), p2_name.lower()):
            return record_match_win(actor_id, p1_name, is_staff_override=True, target_winner=p1_name, win_reason="opponent_dq")[1]
    return f"Player '{target_user}' does not have a pending match in Round {rnd_num}."


def get_current_matches_text() -> str:
    tourney = get_active_tournament()
    if not tourney:
        return "No active tournament right now."
    t_id = int(tourney["id"])
    rnd = get_current_round(t_id)
    if not rnd:
        return f"🏆 {tourney['name']} [{tourney['status'].upper()}] — Round 1 has not started yet."
    rnd_num = int(rnd["round_number"])
    matches = get_conn().execute(
        "SELECT * FROM tourney_matches WHERE tournament_id = ? AND round_number = ? ORDER BY match_number ASC",
        (t_id, rnd_num),
    ).fetchall()
    if not matches:
        return f"No matches found for Round {rnd_num}."
    from bot.utils.scifi import LINE_DIVIDER, to_small_caps
    lines = [
        LINE_DIVIDER,
        f"✦ {to_small_caps(tourney['name'])} // ROUND {rnd_num} ✦",
        f"➥ Game :: {rnd['game'] or tourney['game'] or 'Game'}",
        LINE_DIVIDER,
    ]
    for m in matches:
        if m["status"] == "pending":
            lines.append(f"  ➤ M{m['match_number']}: @{m['player1_name']} ⤬ @{m['player2_name']} [Playing]")
        elif m["status"] == "bye":
            lines.append(f"  ➤ M{m['match_number']}: @{m['player1_name']} [✔︎ BYE - Advances]")
        elif m["status"] == "double_afk":
            lines.append(f"  ➤ M{m['match_number']}: @{m['player1_name']} ⤬ @{m['player2_name']} [✘ Both AFK]")
        else:
            lines.append(f"  ➤ M{m['match_number']}: @{m['player1_name']} ⤬ @{m['player2_name']} [✔︎ Won: @{m['winner_name']}]")
    return "\n".join(lines)


def get_my_match_text(user_id: str, username: str) -> str:
    tourney = get_active_tournament()
    if not tourney:
        return "No active tournament right now."
    t_id = int(tourney["id"])
    rnd = get_current_round(t_id)
    if not rnd:
        return f"@{username} Round 1 has not started yet."
    rnd_num = int(rnd["round_number"])
    matches = get_conn().execute(
        "SELECT * FROM tourney_matches WHERE tournament_id = ? AND round_number = ?",
        (t_id, rnd_num),
    ).fetchall()
    u_low = username.strip().lower()
    id_low = user_id.strip().lower()
    for m in matches:
        if u_low in (str(m["player1_name"]).lower(), str(m["player1_id"]).lower()) or id_low in (str(m["player1_name"]).lower(), str(m["player1_id"]).lower()):
            if m["status"] == "bye":
                return f"✦ @{username} — You have an automatic BYE in Round {rnd_num}! [✔︎ Auto Advances]"
            return (
                f"✦ MATCH STATUS // @{username} ✦\n"
                f"➥ Round {rnd_num} Match #{m['match_number']}: You ⤬ @{m['player2_name']}\n"
                f"➥ Status: [{m['status'].upper()}]\n"
                f"➥ Claim win via /iwon | Report issues via /reportissue"
            )
        if u_low in (str(m["player2_name"] or "").lower(), str(m["player2_id"] or "").lower()) or id_low in (str(m["player2_name"] or "").lower(), str(m["player2_id"] or "").lower()):
            return (
                f"✦ MATCH STATUS // @{username} ✦\n"
                f"➥ Round {rnd_num} Match #{m['match_number']}: You ⤬ @{m['player1_name']}\n"
                f"➥ Status: [{m['status'].upper()}]\n"
                f"➥ Claim win via /iwon | Report issues via /reportissue"
            )
    return f"@{username} You do not have a match in Round {rnd_num}."


def get_open_issues_text() -> str:
    rows = get_conn().execute(
        "SELECT * FROM tourney_issues WHERE status = 'open' ORDER BY id DESC LIMIT 8"
    ).fetchall()
    if not rows:
        return "✔︎ No open tournament issues reported."
    lines = ["🗲 OPEN TOURNEY ISSUES:"]
    for r in rows:
        m_str = f"R{r['round_number']} M{r['match_number']}" if r["round_number"] and r["match_number"] else "General"
        opp = f" (vs @{r['opponent_name']})" if r["opponent_name"] else ""
        lines.append(f"• #{r['id']} [{m_str}] @{r['reporter_name']}{opp}: {r['issue_text']}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# TYPE 2: SMART MULTI-TAB GIVEAWAY ENGINE (CAPACITY-BASED BATCHES)
# ─────────────────────────────────────────────────────────────────────────────

def get_active_giveaway() -> sqlite3.Row | None:
    return get_conn().execute("SELECT * FROM giveaways WHERE is_active = 1 ORDER BY id DESC LIMIT 1").fetchone()


def get_seats_for_game(game: str) -> int:
    clean = (game or "").strip().lower()
    for key, cap in GAME_SEATS_PER_TAB.items():
        if key in clean:
            return cap
    return 15


def calculate_batch_tabs(online_count: int, seats_per_tab: int, remaining_winners: int) -> int:
    if remaining_winners <= 0:
        return 0
    cap = max(1, int(seats_per_tab))
    online = max(cap, int(online_count))
    tabs_by_online = max(1, online // cap)
    return min(tabs_by_online, remaining_winners)


def create_giveaway(
    target_winners: int,
    game: str,
    online_count: int,
    info_text: str,
    rules_text: str,
    actor_id: str,
    seats_override: int | None = None,
) -> tuple[dict[str, object], str]:
    seats = seats_override if (seats_override and seats_override > 0) else get_seats_for_game(game)
    batch1_tabs = calculate_batch_tabs(online_count, seats, target_winners)
    title = f"{game.title()} Giveaway ({target_winners} Winners)"

    with transaction() as conn:
        conn.execute("UPDATE giveaways SET is_active = 0, status = 'completed' WHERE is_active = 1")
        conn.execute("DELETE FROM tourney_winners")
        cur = conn.execute(
            "INSERT INTO giveaways (title, game, seats_per_tab, target_winners, online_count, current_batch, tabs_in_current_batch, winners_in_current_batch, info_text, rules_text, status, is_active, created_by) "
            "VALUES (?, ?, ?, ?, ?, 1, ?, 0, ?, ?, 'active', 1, ?)",
            (title, game, seats, target_winners, online_count, batch1_tabs, info_text, rules_text, actor_id),
        )
        ga_id = cur.lastrowid

    if rules_text:
        community.set_tourney_rules(rules_text, actor_id)

    announcement = "\n".join([
        f"🎁 {title.upper()} STARTED!",
        f"ℹ️ Info: {info_text or 'Join the tabs in chat to win!'}",
        f"📜 Rules: {rules_text or 'Follow host instructions.'}",
        f"👥 Online: {online_count} | Seat Cap: {seats}/tab",
        f"🎮 WAVE #1: Creating {batch1_tabs} {game} tab(s) now! (0/{target_winners} winners crowned)",
    ])
    return {
        "id": ga_id,
        "title": title,
        "game": game,
        "seats_per_tab": seats,
        "target_winners": target_winners,
        "online_count": online_count,
        "batch1_tabs": batch1_tabs,
    }, announcement


def record_giveaway_winner(
    target_user: str,
    actor_id: str,
    online_count_override: int | None = None,
) -> tuple[bool, str]:
    ga = get_active_giveaway()
    if not ga:
        return False, "No active giveaway right now."
    if ga["status"] == "paused":
        return False, "⏸️ Giveaway is currently PAUSED / ON HOLD by staff. Adding winners is on hold."

    exact_uid, exact_uname = resolve_winner_identity(target_user)
    ga_id = int(ga["id"])
    target_total = int(ga["target_winners"])
    seats = int(ga["seats_per_tab"])
    online = int(online_count_override if online_count_override is not None else ga["online_count"])
    cur_batch = int(ga["current_batch"])
    tabs_in_batch = int(ga["tabs_in_current_batch"])
    wins_in_batch = int(ga["winners_in_current_batch"]) + 1
    game = str(ga["game"])

    with transaction() as conn:
        existing_cnt = conn.execute("SELECT COUNT(*) AS c FROM tourney_winners").fetchone()["c"]
        win_num = int(existing_cnt) + 1
        conn.execute(
            "INSERT INTO tourney_winners (tourney_name, tab_label, user_id, username, added_by) VALUES (?, ?, ?, ?, ?)",
            (str(ga["title"]), f"GA Tab #{win_num}", exact_uid, exact_uname, actor_id),
        )
        conn.execute(
            "UPDATE giveaways SET winners_in_current_batch = ?, online_count = ? WHERE id = ?",
            (wins_in_batch, online, ga_id),
        )

    all_winners = get_winners()
    names_so_far = format_compact_winners_names(all_winners)
    total_now = len(all_winners)
    remaining = max(0, target_total - total_now)

    lines = [
        f"🎉 GIVEAWAY WINNER ({total_now}/{target_total}): @{exact_uname} [ID: {exact_uid}]!",
        f"🏆 Winners so far: {names_so_far}",
    ]

    if remaining == 0:
        with transaction() as conn:
            conn.execute("UPDATE giveaways SET status = 'completed', is_active = 0 WHERE id = ?", (ga_id,))
        lines.append(f"\n🥳 ALL {target_total}/{target_total} GIVEAWAY WINNERS CROWNED! Use /winners to view exact IDs for prizes.")
    elif wins_in_batch >= tabs_in_batch:
        next_batch = cur_batch + 1
        next_tabs = calculate_batch_tabs(online, seats, remaining)
        with transaction() as conn:
            conn.execute(
                "UPDATE giveaways SET current_batch = ?, tabs_in_current_batch = ?, winners_in_current_batch = 0 WHERE id = ?",
                (next_batch, next_tabs, ga_id),
            )
        lines.append(
            f"📢 Wave #{cur_batch} complete! Starting WAVE #{next_batch}: Creating {next_tabs} {game} tab(s) ({remaining} winner(s) left)!"
        )
    else:
        tabs_left_in_wave = tabs_in_batch - wins_in_batch
        lines.append(f"⏳ {tabs_left_in_wave} tab(s) still running in Wave #{cur_batch} ({remaining} total winner(s) left).")

    return True, "\n".join(lines)


def end_giveaway() -> bool:
    with transaction() as conn:
        cur = conn.execute("UPDATE giveaways SET status = 'completed', is_active = 0 WHERE is_active = 1")
        return cur.rowcount > 0


def get_draft_summary() -> str:
    tourney = get_active_tournament()
    ga = get_active_giveaway()
    lines = []
    if tourney:
        regs = get_conn().execute(
            "SELECT COUNT(*) AS c FROM registrations WHERE tournament_id = ? AND status = 'registered'",
            (tourney["id"],),
        ).fetchone()["c"]
        lines.append(f"🏆 TOURNAMENT: {tourney['name']} [{tourney['status'].upper()}]")
        lines.append(f"• Game: {tourney['game'] or 'TBD'}")
        lines.append(f"• Slots: {tourney['max_slots'] or 'Unlimited'} ({regs} registered)")
        if tourney["rules_text"]:
            lines.append(f"• Rules: {tourney['rules_text']}")
        if tourney["prize_info"]:
            lines.append(f"• Prize: {tourney['prize_info']}")
        lines.append("⚡ Use /start to launch or advance rounds!")
    if ga:
        lines.append(f"🎁 GIVEAWAY: {ga['title']} [{ga['status'].upper()}]")
        lines.append(f"• Game: {ga['game']} (Cap: {ga['seats_per_tab']}/tab)")
        lines.append(f"• Target Winners: {ga['target_winners']} | Online: {ga['online_count']}")
        lines.append(f"• Current Wave: #{ga['current_batch']} ({ga['tabs_in_current_batch']} tabs)")
        if ga["rules_text"]:
            lines.append(f"• Rules: {ga['rules_text']}")
        lines.append("⚡ Use /start to launch Wave #1 in Main GC!")
    if not lines:
        return "No tournament or giveaway is currently active or drafted. Use /createtour or /createga to start."
    return "\n".join(lines)


def pause_event(actor_id: str) -> tuple[bool, str]:
    tourney = get_active_tournament()
    ga = get_active_giveaway()
    if tourney and tourney["status"] in ("open", "ongoing", "draft"):
        with transaction() as conn:
            conn.execute("UPDATE tournaments SET status = 'paused' WHERE id = ?", (tourney["id"],))
        return True, f"⏸️ Tournament '{tourney['name']}' is now PAUSED / ON HOLD by staff."
    if ga and ga["status"] in ("active", "draft"):
        with transaction() as conn:
            conn.execute("UPDATE giveaways SET status = 'paused' WHERE id = ?", (ga["id"],))
        return True, f"⏸️ Giveaway '{ga['title']}' is now PAUSED / ON HOLD by staff."
    return False, "No active running tournament or giveaway to pause."


def resume_event(actor_id: str) -> tuple[bool, str]:
    tourney = get_active_tournament()
    ga = get_active_giveaway()
    if tourney and tourney["status"] == "paused":
        cur_rnd = get_current_round(int(tourney["id"]))
        res_status = "ongoing" if cur_rnd else "open"
        with transaction() as conn:
            conn.execute("UPDATE tournaments SET status = ? WHERE id = ?", (res_status, tourney["id"]))
        return True, f"▶️ Tournament '{tourney['name']}' RESUMED ({res_status.upper()})! Play continues."
    if ga and ga["status"] == "paused":
        with transaction() as conn:
            conn.execute("UPDATE giveaways SET status = 'active' WHERE id = ?", (ga["id"],))
        return True, f"▶️ Giveaway '{ga['title']}' RESUMED! Play continues."
    return False, "No paused tournament or giveaway to resume."


def end_active_event(actor_id: str) -> tuple[bool, str]:
    tourney = get_active_tournament()
    ga = get_active_giveaway()
    ended = []
    if tourney:
        with transaction() as conn:
            conn.execute("UPDATE tournaments SET status = 'completed', is_active = 0 WHERE id = ?", (tourney["id"],))
        ended.append(f"🏆 Tournament '{tourney['name']}' ended.")
    if ga:
        with transaction() as conn:
            conn.execute("UPDATE giveaways SET status = 'completed', is_active = 0 WHERE id = ?", (ga["id"],))
        ended.append(f"🎁 Giveaway '{ga['title']}' ended.")
    if not ended:
        return False, "No active tournament or giveaway to end."
    return True, "\n".join(ended) + "\n📢 Use /winners to view the recorded winners list."
