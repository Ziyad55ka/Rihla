"""Persistent, atomic per-account limits for Rihla's login endpoint only.

Supabase still verifies/stores passwords. This file stores email hashes and times,
never passwords or sessions. SQLite supports local workers sharing one file.
"""

import hashlib
import json
import math
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

WINDOW = 15 * 60
LEASE_SECONDS = 60


def limited(seconds: int, code: str = "login_locked") -> HTTPException:
    return HTTPException(
        429,
        {"code": code, "message": "Please wait before trying to sign in again."},
        headers={"Retry-After": str(max(1, seconds))},
    )


@dataclass(frozen=True)
class LoginLease:
    account_key: str
    token: str


class LoginLimits:
    def __init__(self, path: Path, clock=time.time):
        self.path = path
        self.clock = clock

    @contextmanager
    def transaction(self):
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=2)
            connection.row_factory = sqlite3.Row
            connection.execute("""create table if not exists login_limits (
                account_key text primary key, failures text not null,
                blocked_until real not null, lease_token text not null,
                lease_until real not null, touched_at real not null)""")
            connection.execute("begin immediate")
            yield connection
            connection.commit()
        except sqlite3.Error as error:
            raise HTTPException(
                503, "Sign-in protection is unavailable. Try again."
            ) from error
        except OSError as error:
            raise HTTPException(
                503, "Sign-in protection is unavailable. Try again."
            ) from error
        finally:
            if connection is not None:
                connection.close()

    def reserve(self, email: str) -> LoginLease:
        key = hashlib.sha256(email.strip().lower().encode()).hexdigest()
        token = secrets.token_hex(16)
        now = self.clock()
        with self.transaction() as db:
            db.execute(
                "delete from login_limits where touched_at < ? "
                "and lease_until < ? and blocked_until < ?",
                (now - 86400, now, now),
            )
            row = db.execute(
                "select * from login_limits where account_key = ?", (key,)
            ).fetchone()
            if row and row["blocked_until"] > now:
                raise limited(math.ceil(row["blocked_until"] - now))
            if row and row["lease_until"] > now:
                raise limited(1, "login_in_progress")
            failures = (
                [stamp for stamp in json.loads(row["failures"]) if stamp > now - WINDOW]
                if row
                else []
            )
            db.execute(
                """insert into login_limits values(?,?,?,?,?,?)
                on conflict(account_key) do update set failures=excluded.failures,
                blocked_until=0, lease_token=excluded.lease_token,
                lease_until=excluded.lease_until, touched_at=excluded.touched_at""",
                (key, json.dumps(failures), 0, token, now + LEASE_SECONDS, now),
            )
        return LoginLease(key, token)

    def complete(self, lease: LoginLease, outcome: str) -> int:
        now = self.clock()
        with self.transaction() as db:
            row = db.execute(
                "select * from login_limits where account_key = ?", (lease.account_key,)
            ).fetchone()
            if (
                not row
                or row["lease_token"] != lease.token
                or row["lease_until"] <= now
            ):
                raise HTTPException(
                    503, "The sign-in attempt expired. Please try again."
                )
            failures = [
                stamp for stamp in json.loads(row["failures"]) if stamp > now - WINDOW
            ]
            # Count all failures in the rolling window, including those before
            # a successful login. Success releases the lease without a reset.
            if outcome == "invalid":
                failures.append(now)
            blocked = now + WINDOW if len(failures) >= 5 else 0
            db.execute(
                """update login_limits set failures=?, blocked_until=?,
                lease_token='', lease_until=0, touched_at=? where account_key=?""",
                (json.dumps(failures), blocked, now, lease.account_key),
            )
        return WINDOW if blocked else 0
