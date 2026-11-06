"""Structured supplier contracts and end-to-end activity merge, no network."""

import asyncio
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx2 as httpx
import pytest
from test_activity_research import proposal

from app.core.config import Settings
from app.schemas.proposals import Proposal
from app.services import activity_research as ar
from app.services.ticketmaster_events import (
    EventListing,
    EventsUnavailable,
    TicketmasterEvents,
    location,
    parse_event,
)
from app.services.trip_research import ResearchError

START, END = date(2027, 1, 10), date(2027, 1, 16)
NOW = datetime(2026, 11, 5, tzinfo=UTC)


def event():
    return {
        "id": "real-event",
        "name": "Paris Music Festival",
        "url": "https://www.ticketmaster.fr/event/123",
        "dates": {
            "status": {"code": "onsale"},
            "start": {
                "localDate": "2027-01-12",
                "dateTime": "2027-01-12T19:00:00Z",
            },
        },
        "sales": {
            "public": {
                "startDateTime": "2026-01-01T00:00:00Z",
                "endDateTime": "2027-01-12T19:00:00Z",
            }
        },
        "priceRanges": [{"min": 20, "max": 80, "currency": "EUR"}],
        "_embedded": {
            "venues": [
                {
                    "name": "City Hall",
                    "city": {"name": "Paris"},
                    "country": {"countryCode": "FR"},
                }
            ]
        },
    }


def parse(item):
    return parse_event(item, "Paris", "FR", START, END, NOW)


def test_valid_event_uses_upper_price_not_cheapest_teaser():
    result = parse(event())
    assert result.day == date(2027, 1, 12)
    assert result.amount == 80 and result.currency == "EUR"
    assert "final fees are not confirmed" in result.content
    assert len(result.content) <= 500


@pytest.mark.parametrize(
    "status", ["cancelled", "postponed", "rescheduled", "offsale", "unknown"]
)
def test_only_on_sale_events_survive(status):
    item = event()
    item["dates"]["status"]["code"] = status
    assert parse(item) is None


@pytest.mark.parametrize("flag", ["dateTBD", "dateTBA", "timeTBA", "noSpecificTime"])
def test_unannounced_dates_or_times_are_not_confirmed(flag):
    item = event()
    item["dates"]["start"][flag] = True
    assert parse(item) is None


@pytest.mark.parametrize("day", ["2027-01-09", "2027-01-17", "2027-02-30", "unknown"])
def test_event_must_be_inside_own_city_stay(day):
    item = event()
    item["dates"]["start"]["localDate"] = day
    assert parse(item) is None


@pytest.mark.parametrize("field,value", [("city", "Lyon"), ("country", "US")])
def test_paris_texas_and_nearby_cities_are_not_paris_france(field, value):
    item = event()
    venue = item["_embedded"]["venues"][0]
    venue[field]["name" if field == "city" else "countryCode"] = value
    assert parse(item) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://ticketmaster.fr/x",
        "https://ticketmaster.fr.evil.test/x",
        "https://user:secret@ticketmaster.fr/x",
        "https://example.com/x",
        "javascript:alert(1)",
    ],
)
def test_untrusted_ticket_links_are_rejected(url):
    item = event()
    item["url"] = url
    assert parse(item) is None


@pytest.mark.parametrize("change", ["future", "ended", "unknown", "timezone"])
def test_public_sales_must_already_be_open(change):
    item = event()
    public = item["sales"]["public"]
    if change == "future":
        public["startDateTime"] = "2027-01-01T00:00:00Z"
    elif change == "ended":
        public["endDateTime"] = "2026-01-01T00:00:00Z"
    elif change == "unknown":
        public["startTBD"] = True
    else:
        public["startDateTime"] = "2026-01-01T00:00:00"
    assert parse(item) is None


@pytest.mark.parametrize(
    "ranges",
    [
        [],
        [{"min": 10, "max": "NaN", "currency": "EUR"}],
        [{"min": 10, "max": "Infinity", "currency": "EUR"}],
        [{"min": 80, "max": 20, "currency": "EUR"}],
        [{"min": -1, "max": 20, "currency": "EUR"}],
        [
            {"min": 1, "max": 20, "currency": "EUR"},
            {"min": 1, "max": 30, "currency": "USD"},
        ],
        [{"min": 10, "currency": "EUR"}],
    ],
)
def test_missing_or_invalid_price_does_not_remove_event_or_become_free(ranges):
    item = event()
    item["priceRanges"] = ranges
    result = parse(item)
    assert result is not None and result.amount is None


def test_location_aliases_and_ambiguous_unknown_locations():
    assert location("باريس", "فرنسا") == ("Paris", "FR")
    assert location("Córdoba", "Spain") == ("Córdoba", "ES")
    assert location("Springfield", "Somewhere") is None


def test_adapter_preserves_local_dates_deduplicates_and_bounds_requests():
    calls = []

    def handle(request):
        calls.append(dict(request.url.params))
        return httpx.Response(200, json={"_embedded": {"events": [event(), event()]}})

    provider = TicketmasterEvents("private-key", httpx.MockTransport(handle))
    found = asyncio.run(provider.find("باريس", "فرنسا", START, END))
    assert len(found) == 1 and len(calls) == 1
    assert calls[0]["countryCode"] == "FR" and calls[0]["city"] == "Paris"
    assert calls[0]["localStartDateTime"] == "2027-01-10T00:00:00,2027-01-16T23:59:59"
    assert calls[0]["size"] == "20" and calls[0]["includeTest"] == "no"


@pytest.mark.parametrize(
    "status,body",
    [(429, {}), (503, {}), (200, []), (200, {"_embedded": {"events": "bad"}})],
)
def test_source_failure_is_distinct_from_no_events_and_never_leaks_key(
    status, body, caplog
):
    provider = TicketmasterEvents(
        "private-key", httpx.MockTransport(lambda r: httpx.Response(status, json=body))
    )
    with pytest.raises(EventsUnavailable) as error:
        asyncio.run(provider.find("Paris", "France", START, END))
    assert "private-key" not in str(error.value) + caplog.text


def test_events_survive_model_quota_without_stale_activities_or_private_inputs(
    monkeypatch,
):
    p = proposal()
    p.activity_focus = ["events_festivals"]
    p.cities[0].city = "Paris"

    # The transport layer already verifies city and dates; return a same-stay listing.
    async def find(self, city, destination, start, end):
        assert not any(
            word in city + destination for word in ("budget", "member", "departure")
        )
        if city != "Paris":
            return []
        return [
            EventListing(
                "event-1",
                "Paris Concert",
                "Paris",
                "City Hall",
                start,
                "https://ticketmaster.fr/event/1",
                Decimal(80),
                "EUR",
            )
        ]

    async def quota(*args):
        raise ResearchError("model_quota", "Temporarily unavailable")

    monkeypatch.setattr(TicketmasterEvents, "find", find)
    monkeypatch.setattr(ar, "_find_researched_activities", quota)
    result = asyncio.run(
        ar.find_activities(p, Settings(_env_file=None, ticketmaster_api_key="test"))
    )
    activity = result.cities[0].activities[0]
    assert (
        activity.name.value == "Paris Concert"
        and activity.scheduled_date.value == str(p.start_date)
    )
    assert activity.price_per_person.status == "Estimated"
    assert activity.research_notes == ["guide_search_unavailable", "events_only"]
    assert all(not stay.activities for stay in result.cities[1:])
    assert result.flights == p.flights
    assert Proposal.model_validate(result.model_dump()) == result
    assert any("Ticketmaster:" in source.title for source in result.sources)


def test_event_outage_does_not_discard_valid_attractions(monkeypatch):
    from activity_fixture import mock_data

    p = Proposal.model_validate(mock_data()["proposals"][0])

    async def fail(*args):
        raise EventsUnavailable

    async def guides(*args):
        return deepcopy(p)

    monkeypatch.setattr(TicketmasterEvents, "find", fail)
    monkeypatch.setattr(ar, "_find_researched_activities", guides)
    result = asyncio.run(
        ar.find_activities(p, Settings(_env_file=None, ticketmaster_api_key="test"))
    )
    assert result.cities[0].activities[0].name == p.cities[0].activities[0].name
    assert result.cities[0].activities[0].research_notes == ["event_source_unavailable"]


def test_new_key_is_not_in_settings_representation():
    assert "private-key" not in repr(
        Settings(_env_file=None, ticketmaster_api_key="private-key")
    )


@pytest.mark.parametrize("outage", [False, True])
def test_event_only_setup_distinguishes_empty_results_from_outage(monkeypatch, outage):
    async def find(*args):
        if outage:
            raise EventsUnavailable
        return []

    monkeypatch.setattr(TicketmasterEvents, "find", find)
    with pytest.raises(ResearchError) as error:
        asyncio.run(
            ar.find_activities(
                proposal(), Settings(_env_file=None, ticketmaster_api_key="test")
            )
        )
    assert error.value.code == ("search_unavailable" if outage else "no_results")
