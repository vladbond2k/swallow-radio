"""Google Flights price calendar (via the `fli` library): cheapest round trip per departure day."""

import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta

from .config import Config


@dataclass
class Option:
    home: str
    out: date
    back: date
    price: float      # tickets, round trip
    extra: float      # getting to the home airport and back

    @property
    def total(self) -> float:
        return self.price + self.extra

    @property
    def days(self) -> int:
        return (self.back - self.out).days


def _calendar(cfg: Config, home: str, days: int) -> list[tuple[date, float]]:
    from fli.core.builders import build_date_search_segments
    from fli.models import Airport, DateSearchFilters, MaxStops, PassengerInfo, SeatType
    from fli.search import SearchDates

    stops = {0: MaxStops.NON_STOP, 1: MaxStops.ONE_STOP_OR_FEWER, 2: MaxStops.TWO_OR_FEWER_STOPS}
    start = max(cfg.depart_from, date.today() + timedelta(days=1)).isoformat()
    segments, trip_type = build_date_search_segments(
        origin=Airport[home],
        destination=[Airport[a] for a in cfg.japan],
        start_date=start,
        trip_duration=days,
        is_round_trip=True,
    )
    filters = DateSearchFilters(
        trip_type=trip_type,
        passenger_info=PassengerInfo(adults=1),
        flight_segments=segments,
        stops=stops.get(cfg.max_stops, MaxStops.ANY),
        seat_type=SeatType.ECONOMY,
        from_date=start,
        to_date=cfg.depart_to.isoformat(),
        duration=days,
    )
    res = SearchDates().search(filters, currency=cfg.currency, language="en")
    return [(r.date[0].date(), r.price) for r in res or []]


def _calendar_demo(cfg: Config, home: str, days: int) -> list[tuple[date, float]]:
    rnd = random.Random(f"{home}{days}")
    n = (cfg.depart_to - cfg.depart_from).days + 1
    return [(cfg.depart_from + timedelta(days=i),
             round(2600 + 900 * rnd.random() + 500 * ((i // 7) % 3) - 30 * (days - 14), -1))
            for i in range(n) if rnd.random() > 0.05]


def search(cfg: Config, demo: bool = False) -> tuple[list[Option], list[str]]:
    fetch = _calendar_demo if demo else _calendar
    opts, errors = [], []
    jobs = [(h, d) for h in cfg.home for d in range(cfg.min_days, cfg.max_days + 1)]
    for i, (home, days) in enumerate(jobs, 1):
        print(f"[{i}/{len(jobs)}] {home} → Japan, {days} days", file=sys.stderr)
        try:
            rows = fetch(cfg, home, days)
        except Exception as e:  # blocked, network, Google changed the response
            errors.append(f"{home}, {days} days: {type(e).__name__}: {e}"[:200])
            print("  ! " + errors[-1], file=sys.stderr)
            continue
        for out, price in rows:
            if cfg.depart_from <= out <= cfg.depart_to and price > 0:
                opts.append(Option(home, out, out + timedelta(days=days), price, cfg.home[home]))
    opts.sort(key=lambda o: o.total)
    return opts, errors
