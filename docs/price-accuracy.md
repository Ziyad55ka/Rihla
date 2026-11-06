# Flight price accuracy

التحقق اليدوي تم لطيران الخليج. وباقي الأسعار يتحقق منها النظام آليًا بمقارنة سعر البحث مع سعر البائع.

## The manual check, 1 November 2026

RUH to BAH, 20 to 30 November 2026, one adult, Economy Light, on Gulf Air's own site.

| Outbound | Return | Site's total | Rihla's price | Gap |
| --- | --- | --- | --- | --- |
| GF 162 at 06:50: 999.00 | 01:25: 615.00 | 1,614.00 SAR | 1,614.00 SAR | **0%** |

The 998.50 seen earlier was only the outbound price, because the site shows that first and adds the return afterwards.

## Base fare and the checkout price

Rihla shows the base fare. The checkout page can be higher because of choices made there, which does not make the base fare wrong.

Example on Lufthansa's site: the total was 2,729 SAR, of which 474 SAR was optional seat selection. That leaves 2,255 SAR for the ticket, the fare Ignav reported for the same route. Skip optional extras such as seat selection when comparing.

## How to measure a flight

1. In Rihla, open the proposal and press **Refresh the price**. Note the flight numbers, times and price.
2. Open the airline's own site, not an agent. Search round trip, same route, same dates, one adult.
3. Choose the outbound flight in the cheapest fare. Note its price, but do not stop here.
4. Choose the return flight in the cheapest fare.
5. Read the **total** on the next step, and note the fare's name and bag.
6. Gap = (Rihla's price − site's total) ÷ site's total. The goal is under 5%.

Compare within about 30 minutes, because prices change and Ignav may reuse a result for that long.

## The automatic check

After every search and check, Rihla compares the search's price with the seller's for that flight:

| Case | What happens |
| --- | --- |
| Under `PRICE_GAP_LOG_PERCENT` (5) | The seller's price is used, and the page says nothing |
| Over it | The seller's price is used, and the gap is logged |
| Seller differs from the airline | The airline is preferred. An agent cheaper by `AGENT_CHEAPER_PERCENT` (5) is offered, marked as an agent |
| No seller price | The search's price is used, and it is counted apart |

Every check is kept in `backend/.local/price-accuracy.sqlite3`: the airline, route, gap and time, with no private data. Print the report from `backend`:

```powershell
uv run python -m app.services.price_accuracy
```

## The live accuracy run

`backend/scripts/live_accuracy.py` searches for real and checks every result
against independent sources. It spends real requests, so it is not part of pytest.
Run it from `backend`:

```powershell
uv run python -m scripts.live_accuracy                 # daily set, about 10 Google Flights requests
uv run python -m scripts.live_accuracy --set weekly    # 15 routes, about 45 requests
uv run python -m scripts.live_accuracy --only RUH-JED  # one route
```

Each route checks: one booking for outbound and return; the airline link's
airports, dates and passengers; the dates and the time home; the Google Flights
page with both flights chosen; Rihla's price against the airline's own total on
Google's booking page (PASS within 2%, FAIL above 5%); and what is known about bags.
A route expected to find nothing must say why in plain words. The activity check
confirms every quote is in its source and counts prices that are only estimates.

Routes are in `scripts/live_scenarios.json`, with dates counted from today. The
report is saved to `backend/.local/accuracy/`, after every route as it goes.

Results on 6 Nov 2026: RUH-JED (flyadeal), DMM-IST (Saudia) and RUH-LHR (Turkish)
matched the airline's own price exactly (0.0%). No source states the checked bag,
so every flight now says what may cost extra and to check the airline's site.
