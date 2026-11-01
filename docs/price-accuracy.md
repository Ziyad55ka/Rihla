# Flight price accuracy

التحقق اليدوي تم لطيران الخليج. وباقي الأسعار يتحقق منها النظام آليًا بمقارنة سعر البحث مع سعر البائع.

## The manual check, 1 November 2026

RUH to BAH, 20 to 30 November 2026, one adult, Economy Light, on Gulf Air's own site.

| Outbound | Return | Site's total | Rihla's price | Gap |
| --- | --- | --- | --- | --- |
| GF 162 at 06:50: 999.00 | 01:25: 615.00 | 1,614.00 SAR | 1,614.00 SAR | **0%** |

The 998.50 seen earlier was only the outbound price, because the site shows that first and adds the return afterwards.

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
