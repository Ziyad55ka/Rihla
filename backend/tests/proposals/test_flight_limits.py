import time

from app.services.flight_usage import DAY, HOUR, FlightUsage


def test_member_limit_says_when_the_oldest_press_expires(tmp_path, monkeypatch):
    usage = FlightUsage(tmp_path / "usage.sqlite3")
    clock = [1_000_000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    for step in range(3):
        clock[0] = 1_000_000.0 + step * 60
        assert usage.take_member_action("m", 3)
    assert not usage.take_member_action("m", 3)
    # The first of the three presses leaves the hour first.
    assert usage.member_free_at("m", 3) == 1_000_000.0 + HOUR


def test_source_limit_takes_the_later_of_trip_and_whole_source(tmp_path, monkeypatch):
    usage = FlightUsage(tmp_path / "usage.sqlite3")
    clock = [2_000_000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    usage.record("search", "generation", False)
    clock[0] += 100
    usage.record("search", "trip-a", False)
    clock[0] += 100
    usage.record("search", "trip-a", False)
    # Source limit 3 is full: the oldest use, at the start, frees it.
    assert usage.source_free_at("trip-a", "ignav", 10, 3) == 2_000_000.0 + DAY
    # Trip limit 1 is full too: its second-newest use frees it later.
    assert usage.source_free_at("trip-a", "ignav", 1, 10) == 2_000_200.0 + DAY
    # Nothing is full: allowed now.
    assert usage.source_free_at("trip-b", "ignav", 5, 10) == clock[0]
