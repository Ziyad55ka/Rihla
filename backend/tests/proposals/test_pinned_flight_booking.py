import asyncio
import json
from copy import deepcopy

import httpx2 as httpx

from app.services.flight_prices import complete_return_fare
from app.services.google_flights_check import GoogleFlightsCheck, _booking_params
from tests.proposals.test_seller_link import BACK, OUT, QUERY, forwards_to, page


def test_missing_booking_token_pins_every_segment_of_the_same_round_trip():
    back = deepcopy(BACK)
    back.pop("booking_token")
    seen = []

    def handle(request):
        if request.url.host == "serpapi.com":
            params = request.url.params
            if "selected_flights_json" in params:
                selected = json.loads(params["selected_flights_json"])
                seen.append(selected)
                assert selected["outbound"][0] == {
                    "flight_number": "EY554",
                    "departure_id": "RUH",
                    "arrival_id": "AUH",
                    "date": "2026-12-17",
                }
                assert selected["return"][1]["flight_number"] == "EY559"
                assert params["adults"] == "3"
                assert "booking_token" not in params and "departure_token" not in params
                return httpx.Response(200, json=page(("Etihad", True, 4500)))
            return httpx.Response(
                200,
                json={"best_flights": [back if "departure_token" in params else OUT]},
            )
        return forwards_to("https://digital.etihad.com/book?adults=3")(request)

    check = GoogleFlightsCheck("fake", httpx.MockTransport(handle))
    fare, answered = asyncio.run(check.fare(QUERY))
    assert answered and fare and complete_return_fare(fare, QUERY)
    assert fare.amount == "1500.00"
    assert len(seen) == 1


def test_pinning_rejects_a_different_date_or_a_broken_connection():
    check = GoogleFlightsCheck("fake")
    back = deepcopy(BACK)
    back.pop("booking_token")
    wrong = deepcopy(OUT)
    wrong["flights"][0]["departure_airport"]["time"] = "2026-12-18 10:30"
    assert _booking_params(QUERY, check._params(QUERY), wrong, back) is None
    wrong = deepcopy(OUT)
    wrong["flights"][1]["departure_airport"]["id"] = "DXB"
    assert _booking_params(QUERY, check._params(QUERY), wrong, back) is None
