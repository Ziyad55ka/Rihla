"""Ignav use, limits and the short fare cache, in a local file.

Holds no private data: routes are public facts, and members appear only as a hash.
See the totals with: uv run python -m app.services.flight_usage
"""

import hashlib
import json
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
            "CREATE TABLE IF NOT EXISTS fare_cache "
            "(key TEXT PRIMARY KEY, at REAL NOT NULL, body TEXT NOT NULL);"
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

    def record(self, kind: str, trip: str, cached: bool) -> None:
        self._write(
            "INSERT INTO ignav_usage VALUES (?, ?, ?, ?)",
            (time.time(), kind, trip, int(cached)),
        )

    def spent_today(self, trip: str | None = None) -> int:
        since = time.time() - DAY
        if trip is None:
            return self._count(
                "SELECT count(*) FROM ignav_usage WHERE cached = 0 AND at > ?",
                (since,),
            )
        return self._count(
            "SELECT count(*) FROM ignav_usage WHERE cached = 0 AND at > ? AND trip = ?",
            (since, trip),
        )

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

    def cache_get(self, key: str, max_age_seconds: float) -> tuple[float, dict] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT at, body FROM fare_cache WHERE key = ?", (key,)
            ).fetchone()
        finally:
            connection.close()
        if row is None or time.time() - row[0] >= max_age_seconds:
            return None
        return row[0], json.loads(row[1])

    def cache_put(self, key: str, body: dict) -> None:
        self._write(
            "INSERT OR REPLACE INTO fare_cache VALUES (?, ?, ?)",
            (key, time.time(), json.dumps(body)),
        )

    def summary(self) -> list[tuple]:
        connection = self._connect()
        try:
            return connection.execute(
                "SELECT trip, kind, cached, count(*) FROM ignav_usage "
                "WHERE at > ? GROUP BY trip, kind, cached ORDER BY trip, kind",
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
