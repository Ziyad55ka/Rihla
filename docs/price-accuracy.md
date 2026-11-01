# Flight price accuracy

This compares Rihla's price with what a person sees on the airline's site. Fill in the empty column after checking the sites yourself.

## How to measure one flight

The airline's site shows the outbound price first and adds the return afterwards, so its first number is not the trip's price.

1. In Rihla, open the proposal and press **Refresh the price**. Note the flight numbers, times and price.
2. Open the airline's own site, not an agent. Search round trip, same route, same dates, one adult.
3. Choose the outbound flight in the cheapest fare. Note its price, but do not stop here.
4. Choose the return flight in the cheapest fare.
5. Read the **total** on the next step, and note the fare's name and bag.
6. Gap = (Rihla's price − site's total) ÷ site's total. The goal is under 5%.

Compare within about 30 minutes, because prices change and Ignav may reuse a result for that long.

## Results, 1 November 2026

Ignav, round trip, 20 to 30 November 2026, one adult, Saudi market. Prices are in SAR. The search and seller columns both come from Ignav, so a 0% there only shows Ignav agrees with itself. **The manual column is the real test.**

| Route | Airline | Flights | Leaves | Search | Seller | Gap | Fare | Link | Each direction? | Site price (manual) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RUH–BAH | Gulf Air | GF 162, GF 163 | 06:50 | 900 | 1,614 | 79.3% | economy | Results | No | **1,614, a 0% gap** (999 + 615) |
| RUH–BAH | flynas | XY 237, XY 234 | 07:55 | 1,000 | 1,000 | 0% | economy | Results | No | |
| RUH–DXB | flydubai | FZ 848, FZ 847 | 09:55 | 5,597 | 5,597 | 0% | economy | Results | No | |
| JED–CAI | Saudia | SV 305, SV 388 | 14:40 | 1,775 | 1,775 | 0% | economy | Results | No | |
| JED–DXB | Emirates | EK 806, EK 801 | 11:15 | 2,891 | 2,891 | 0% | economy | This flight | No | |
| JED–CAI | EgyptAir | MS 670, MS 643 | 22:55 | 1,200 | Not stated | – | economy | Results | No | |
| RUH–IST | Turkish Airlines | TK 147, TK 144 | 01:10 | 1,819 | Not stated | – | economy | This flight | No | |
| DMM–DOH | Qatar Airways | QR 1151, QR 1150 | 10:50 | 2,437 | Not stated | – | economy | Results | No | |

- **Average gap, search to seller:** 15.9% over the five flights with a seller price, and 80% of them are under 5%. The one outlier is explained below.
- **Gulf Air's 79.3%:** the search's 900 belongs to another seller, flynas, on the same flights. Gulf Air's own 1,614 matched its site.
- **flydubai's 5,597:** this looks high, since the cheapest trip on that route was 994. It was the cheapest with flydubai both ways. Check it first.
- **Link:** Turkish Airlines says `exact_flight`, and Qatar Airways says `search_results`. The others do not say, so it is worked out from whether the link holds the flight numbers.
- **Not found on one airline both ways:** Emirates on RUH–DXB, flynas on RUH–IST and flyadeal on RUH–DXB.
- **Agents:** only Emirates had one with a price, Travomint at 3,057, above the airline.
- **Requests used:** 14 of the 16 allowed.

Ignav gave the cheapest result for each airline, with no fare name or bag on any of them.

## The automatic check

After every search and check, Rihla compares the search's price with the seller's for that flight:

| Case | What happens |
| --- | --- |
| Under `PRICE_GAP_LOG_PERCENT` (5) | The seller's price is used, and the page says nothing |
| Over it | The seller's price is used, and the gap is logged |
| Seller differs from the airline | The airline is preferred. An agent cheaper by `AGENT_CHEAPER_PERCENT` (5) is offered, marked as an agent |
| No seller price | The search's price is used, and it is counted apart |

Every check is kept in `backend/.local/price-accuracy.sqlite3`, because the report needs an average: the airline, route, gap and time, with no private data. Print the report from `backend`:

```powershell
uv run python -m app.services.price_accuracy
```
