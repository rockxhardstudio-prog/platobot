from datetime import datetime, timezone
from bot.database.db import get_conn, transaction


class OutboxPlatoClient:
    LEASE_TIMEOUT_SECONDS = 25
    MAX_ATTEMPTS = 3

    def send_message(self, group_id: str, text: str) -> None:
        with transaction() as conn:
            conn.execute(
                "INSERT INTO outbox (group_id, text, status, attempts) VALUES (?, ?, 'pending', 0)",
                (group_id, text),
            )

    def recover_stale_sending(self) -> None:
        with transaction() as conn:
            stale_rows = conn.execute(
                "SELECT id, attempts FROM outbox WHERE status='sending' "
                "AND last_attempt_at IS NOT NULL "
                "AND (strftime('%s', 'now') - strftime('%s', last_attempt_at)) > ?",
                (self.LEASE_TIMEOUT_SECONDS,),
            ).fetchall()
            for row in stale_rows:
                if row["attempts"] >= self.MAX_ATTEMPTS:
                    conn.execute(
                        "UPDATE outbox SET status='failed', error='Lease timeout exceeded max attempts' WHERE id=?",
                        (row["id"],),
                    )
                else:
                    conn.execute(
                        "UPDATE outbox SET status='pending' WHERE id=?",
                        (row["id"],),
                    )

    def pending(self, group_id: str | None = None, limit: int = 20) -> list[dict]:
        conn = get_conn()
        query = (
            "SELECT id, group_id, text, status, attempts FROM outbox "
            "WHERE status IN ('pending', 'sending') "
        )
        params = []
        if group_id:
            query += "AND group_id=? "
            params.append(group_id)
        query += "ORDER BY id LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    def claim(self, group_id: str | None = None, limit: int = 1) -> list[dict]:
        self.recover_stale_sending()
        with transaction() as conn:
            query = (
                "SELECT id, group_id, text, attempts FROM outbox "
                "WHERE status='pending' "
            )
            params = []
            if group_id:
                query += "AND group_id=? "
                params.append(group_id)
            query += "ORDER BY id LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, tuple(params)).fetchall()
            claimed = []
            for row in rows:
                new_attempts = row["attempts"] + 1
                conn.execute(
                    "UPDATE outbox SET status='sending', attempts=?, last_attempt_at=datetime('now') WHERE id=?",
                    (new_attempts, row["id"]),
                )
                claimed.append({
                    "id": row["id"],
                    "group_id": row["group_id"],
                    "text": row["text"],
                    "attempts": new_attempts,
                })
            return claimed

    def ack(self, outbox_id: int) -> None:
        with transaction() as conn:
            conn.execute(
                "UPDATE outbox SET status='delivered', delivered_at=datetime('now') WHERE id=?",
                (outbox_id,),
            )

    def fail(self, outbox_id: int, reason: str = "") -> None:
        with transaction() as conn:
            row = conn.execute("SELECT attempts FROM outbox WHERE id=?", (outbox_id,)).fetchone()
            if row and row["attempts"] < self.MAX_ATTEMPTS:
                conn.execute(
                    "UPDATE outbox SET status='pending', error=? WHERE id=?",
                    (reason, outbox_id),
                )
            else:
                conn.execute(
                    "UPDATE outbox SET status='failed', error=? WHERE id=?",
                    (reason, outbox_id),
                )
