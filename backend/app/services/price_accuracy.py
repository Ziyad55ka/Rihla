"""How close search prices are to sellers' prices, in a local file.

Every check is kept so the report can give an average. Holds no private data: only the
airline, the route, the gap and the time. A gap above the limit is also logged.
See the report with: uv run python -m app.services.price_accuracy
"""

import logging
import sqlite3
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccuracyReport:
    checks: int
    # Checks where a seller stated no price, so there was nothing to compare.
    no_seller_price: int
    average_gap_percent: float | None
    under_limit_percent: float | None


class PriceAccuracy:
    def __init__(self, path: Path, limit_percent: Decimal = Decimal(5)) -> None:
        self.path = path
        self.limit_percent = limit_percent

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS price_checks "
            "(at REAL NOT NULL, airline TEXT NOT NULL, route TEXT NOT NULL, "
            "gap_percent REAL)"
        )
        return connection

    def record(self, airline: str, route: str, gap_percent: Decimal | None) -> None:
        """A gap of None means the seller stated no price."""
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "INSERT INTO price_checks VALUES (?, ?, ?, ?)",
                    (
                        time.time(),
                        airline,
                        route,
                        None if gap_percent is None else float(abs(gap_percent)),
                    ),
                )
        finally:
            connection.close()
        if gap_percent is not None and abs(gap_percent) > self.limit_percent:
            logger.info(
                "price_gap route=%s percent=%s", route, round(abs(gap_percent), 1)
            )

    def report(self) -> AccuracyReport:
        connection = self._connect()
        try:
            gaps = [
                row[0]
                for row in connection.execute("SELECT gap_percent FROM price_checks")
            ]
        finally:
            connection.close()
        known = [item for item in gaps if item is not None]
        limit = float(self.limit_percent)
        return AccuracyReport(
            checks=len(gaps),
            no_seller_price=len(gaps) - len(known),
            average_gap_percent=round(sum(known) / len(known), 1) if known else None,
            under_limit_percent=(
                round(100 * sum(item < limit for item in known) / len(known), 1)
                if known
                else None
            ),
        )

    def worst(self, count: int = 10) -> list[tuple[str, str, float]]:
        connection = self._connect()
        try:
            return connection.execute(
                "SELECT airline, route, gap_percent FROM price_checks "
                "WHERE gap_percent IS NOT NULL ORDER BY gap_percent DESC LIMIT ?",
                (count,),
            ).fetchall()
        finally:
            connection.close()


if __name__ == "__main__":
    import sys

    from app.core.config import Settings

    sys.stdout.reconfigure(encoding="utf-8")
    settings = Settings()
    accuracy = PriceAccuracy(settings.price_accuracy_db, settings.price_gap_log_percent)
    result = accuracy.report()
    print("Checks:", result.checks)
    print("With no seller price to compare:", result.no_seller_price)
    print("Average gap between search and seller:", result.average_gap_percent, "%")
    print(f"Under {settings.price_gap_log_percent}%:", result.under_limit_percent, "%")
    for airline, route, gap in accuracy.worst():
        print(f"{gap:.1f}%  {route}  {airline}")
