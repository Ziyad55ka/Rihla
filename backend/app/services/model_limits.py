"""Safe quota hints: never return provider messages, projects, or prompt contents."""

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class QuotaHint:
    scope: Literal["day", "minute", "unknown"] = "unknown"
    retry_seconds: int | None = None


def quota_hint(details: object, now: datetime | None = None) -> QuotaHint:
    if not isinstance(details, dict):
        return QuotaHint()
    error = details.get("error", details)
    if not isinstance(error, dict):
        return QuotaHint()
    scope = "unknown"
    seconds = None
    entries = error.get("details")
    for item in entries if isinstance(entries, list) else []:
        if not isinstance(item, dict):
            continue
        if str(item.get("@type", "")).endswith("QuotaFailure"):
            violations = item.get("violations")
            for violation in violations if isinstance(violations, list) else []:
                if not isinstance(violation, dict):
                    continue
                identifier = str(violation.get("quotaId", "")).casefold()
                if "perday" in identifier:
                    scope = "day"
                elif "perminute" in identifier and scope != "day":
                    scope = "minute"
        if str(item.get("@type", "")).endswith("RetryInfo"):
            match = re.fullmatch(
                r"([0-9]+(?:\.[0-9]+)?)s", str(item.get("retryDelay", ""))
            )
            if match:
                seconds = min(math.ceil(float(match.group(1))), 172800)
    if scope == "day":
        current = (now or datetime.now(UTC)).astimezone(ZoneInfo("America/Los_Angeles"))
        reset = (current + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        seconds = max(
            seconds or 0,
            math.ceil(
                (reset.astimezone(UTC) - current.astimezone(UTC)).total_seconds()
            ),
        )
    return QuotaHint(scope, seconds)
