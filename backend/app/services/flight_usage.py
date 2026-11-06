"""Flight source use and limits, in a local file.

Holds no private data: routes are public facts, and members appear only as a hash.
See the totals with: uv run python -m app.services.flight_usage
"""

import hashlib
import sqlite3
import time
from pathlib import Path

DAY = 86400
HOUR = 3600


class FlightUsage:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.executescript(
            "CREATE TABLE IF NOT EXISTS ignav_usage "
            "(at REAL NOT NULL, kind TEXT NOT NULL, trip TEXT NOT NULL, "
            "cached INTEGER NOT NULL);"
            "CREATE TABLE IF NOT EXISTS member_actions "
            "(at REAL NOT NULL, member TEXT NOT NULL);"
        )
        columns = [
            row[1] for row in connection.execute("PRAGMA table_info(ignav_usage)")
        ]
        if "provider" not in columns:
            connection.execute(
                "ALTER TABLE ignav_usage "
                "ADD COLUMN provider TEXT NOT NULL DEFAULT 'ignav'"
            )
        return connection

    def _write(self, sql: str, values: tuple) -> None:
        connection = self._connect()
        try:
            with connection:
                connection.execute(sql, values)
        finally:
            connection.close()

    def _count(self, sql: str, values: tuple) -> int:
        connection = self._connect()
        try:
            return connection.execute(sql, values).fetchone()[0]
        finally:
            connection.close()

    def record(
        self, kind: str, trip: str, cached: bool, provider: str = "ignav"
    ) -> None:
        self._write(
            "INSERT INTO ignav_usage (at, kind, trip, cached, provider) "
            "VALUES (?, ?, ?, ?, ?)",
            (time.time(), kind, trip, int(cached), provider),
        )

    def spent_today(self, trip: str | None = None, provider: str | None = None) -> int:
        sql = "SELECT count(*) FROM ignav_usage WHERE cached = 0 AND at > ?"
        values: list = [time.time() - DAY]
        if trip is not None:
            sql += " AND trip = ?"
            values.append(trip)
        if provider is not None:
            sql += " AND provider = ?"
            values.append(provider)
        return self._count(sql, tuple(values))

    @staticmethod
    def _member(member: str) -> str:
        return hashlib.sha256(member.encode()).hexdigest()

    def take_member_action(self, member: str, limit: int) -> bool:
        """Count one action, unless this member has used the hour's allowance."""
        key = self._member(member)
        used = self._count(
            "SELECT count(*) FROM member_actions WHERE member = ? AND at > ?",
            (key, time.time() - HOUR),
        )
        if used >= limit:
            return False
        self._write("INSERT INTO member_actions VALUES (?, ?)", (time.time(), key))
        return True

    def _free_at(self, where: str, values: tuple, limit: int, window: int) -> float:
        """When the oldest counted use leaves the window and one more is allowed."""
        connection = self._connect()
        try:
            times = [
                row[0]
                for row in connection.execute(
                    f"SELECT at FROM {where} AND at > ? ORDER BY at",
                    (*values, time.time() - window),
                )
            ]
        finally:
            connection.close()
        if len(times) < limit or limit <= 0:
            return time.time()
        return times[len(times) - limit] + window

    def member_free_at(self, member: str, limit: int) -> float:
        return self._free_at(
            "member_actions WHERE member = ?", (self._member(member),), limit, HOUR
        )

    def source_free_at(
        self, trip: str, provider: str, trip_limit: int, source_limit: int
    ) -> float:
        """The later of this trip's and the whole source's daily limits."""
        base = "ignav_usage WHERE cached = 0 AND provider = ?"
        return max(
            self._free_at(f"{base} AND trip = ?", (provider, trip), trip_limit, DAY),
            self._free_at(base, (provider,), source_limit, DAY),
        )

    def summary(self) -> list[tuple]:
        connection = self._connect()
        try:
            return connection.execute(
                "SELECT trip, provider || ':' || kind, cached, count(*) "
                "FROM ignav_usage "
                "WHERE at > ? GROUP BY trip, provider, kind, cached "
                "ORDER BY trip, provider, kind",
                (time.time() - DAY,),
            ).fetchall()
        finally:
            connection.close()


if __name__ == "__main__":
    from app.core.config import Settings

    usage = FlightUsage(Settings().flight_usage_db)
    print("Last 24 hours. New requests:", usage.spent_today())
    for trip, kind, cached, count in usage.summary():
        print(f"{trip}  {kind}  {'cache' if cached else 'new'}  {count}")
