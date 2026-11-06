from datetime import UTC, datetime

from app.services.model_limits import quota_hint


def test_daily_limit_never_suggests_a_minute_retry_before_daily_reset():
    body = {
        "error": {
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [
                        {
                            "quotaId": "GenerateRequestsPerDayPerProjectPerModel-"
                            "FreeTier",
                            "quotaDimensions": {"project": "private"},
                        }
                    ],
                },
                {
                    "@type": "type.googleapis.com/google.rpc.RetryInfo",
                    "retryDelay": "12.2s",
                },
            ]
        }
    }
    hint = quota_hint(body, datetime(2026, 11, 5, 18, 0, tzinfo=UTC))
    assert hint.scope == "day"
    assert hint.retry_seconds == 14 * 3600
    assert "private" not in str(hint)


def test_minute_limit_uses_provider_retry_delay_and_handles_unknown_metadata():
    body = {
        "details": [
            {
                "@type": "google.rpc.QuotaFailure",
                "violations": [{"quotaId": "RequestsPerMinute"}],
            },
            {"@type": "google.rpc.RetryInfo", "retryDelay": "47.1s"},
        ]
    }
    assert quota_hint(body).retry_seconds == 48
    assert quota_hint(body).scope == "minute"
    for malformed in (None, [], {"error": None}, {"details": [None, "text"]}):
        assert quota_hint(malformed).retry_seconds is None
