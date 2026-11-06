"""Which sources may name and price a stay, and which only inspire the choice."""

from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.schemas.proposals import CityStay, InfoField, Proposal, SarPrice

SourceKind = Literal["booking", "ideas", "flight"]
FLIGHT_SOURCE_TITLE = "Ignav booking link"


def on_domain(url: str, domains: list[str] | tuple[str, ...]) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").casefold()
    for item in domains:
        domain, slash, path = item.partition("/")
        if (host == domain or host.endswith(f".{domain}")) and (
            not slash or f"{parts.path}/".startswith(f"/{path}/")
        ):
            return True
    return False


def search_hosts(domains: list[str]) -> list[str]:
    """The search filter takes sites only, so on_domain checks any path afterwards."""
    return list(dict.fromkeys(item.partition("/")[0] for item in domains))


def classify_source(url: str, title: str, booking_domains: list[str]) -> SourceKind:
    if title.startswith(FLIGHT_SOURCE_TITLE):
        return "flight"
    return "booking" if on_domain(url, booking_domains) else "ideas"


def _city_search(url: str | None) -> str | None:
    """Drop the hotel from a "hotel, city, country" search, keeping the rest."""
    if not url:
        return url
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    fixed = []
    for key, value in query:
        place = value.split(", ")
        if key == "ss" and len(place) >= 3:
            value = ", ".join(place[-2:])
        fixed.append((key, value))
    return urlunsplit(parts._replace(query=urlencode(fixed)))


def apply_source_policy(proposal: Proposal, booking_domains: list[str]) -> Proposal:
    """Label sources, and hide stay details that no approved booking source supports.

    Runs on reading as well, so proposals saved before this rule follow it too.
    """
    kinds = {
        source.id: classify_source(source.url, source.title, booking_domains)
        for source in proposal.sources
    }

    def backed(field: InfoField | SarPrice) -> bool:
        return any(kinds.get(item.source_id) == "booking" for item in field.evidence)

    stays: list[CityStay] = []
    removed_price = False
    for stay in proposal.cities:
        update: dict = {}
        if stay.hotel_name.status != "Not available" and not backed(stay.hotel_name):
            update["hotel_name"] = InfoField(
                value=None, status="Not available", evidence=[]
            )
            update["booking_url"] = _city_search(stay.booking_url)
        price = stay.hotel_price_per_night
        rough_allowance = price.status == "Unconfirmed" and not price.evidence
        if rough_allowance:
            removed_price = True
        if (
            price.status != "Not available"
            and not rough_allowance
            and not backed(price)
        ):
            update["hotel_price_per_night"] = SarPrice(
                amount_sar=None, status="Not available", evidence=[]
            )
            removed_price = True
        stays.append(stay.model_copy(update=update))
    status = proposal.budget_status
    if removed_price and status == "within_group_budget":
        status = "includes_unconfirmed"
    from app.services.landmark_catalog import enrich_reviewed

    return enrich_reviewed(
        proposal.model_copy(
            update={
                "cities": stays,
                "flights": [
                    route.model_copy(
                        update={
                            "price_per_person": route.price_per_person.model_copy(
                                update={"status": "Estimated"}
                            )
                            if route.price_source == "search"
                            and route.price_per_person.status == "Sourced"
                            else route.price_per_person
                        }
                    )
                    for route in proposal.flights
                ],
                "budget_status": status,
                "sources": [
                    item.model_copy(update={"kind": kinds[item.id]})
                    for item in proposal.sources
                ],
            }
        )
    )
