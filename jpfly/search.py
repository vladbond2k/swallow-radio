"""Google Flights price calendar (via the `fli` library): cheapest round trip per departure day.

One request = one (home airport, Japan airport, trip length, ≤61-day window). Single-airport
requests come back fast and complete; multi-airport ones are slow and nearly empty, so we never
combine airports. Google starts refusing after a burst of requests, so we pace them, back off
when refused, cache every answer on disk, and let the next run pick up where this one stopped.
"""

import json
import random
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .config import Config

CHUNK_DAYS = 61          # Google's calendar answers at most this many departure days per request


class Blocked(Exception):
    """Google answered without data (rate limited)."""


@dataclass
class Option:
    home: str
    dest: str
    out: date
    back: date
    price: float      # round trip, 1 adult

    @property
    def days(self) -> int:
        return (self.back - self.out).days


def _windows(cfg: Config) -> list[tuple[date, date]]:
    start = max(cfg.depart_from, date.today() + timedelta(days=1))
    out = []
    while start <= cfg.depart_to:
        end = min(start + timedelta(days=CHUNK_DAYS - 1), cfg.depart_to)
        out.append((start, end))
        start = end + timedelta(days=1)
    return out


def _calendar(cfg: Config, home: str, dest: str, days: int, start: date, end: date) -> list[tuple[str, float]]:
    from fli.core.builders import build_date_search_segments
    from fli.models import Airport, DateSearchFilters, MaxStops, PassengerInfo, SeatType
    from fli.search import SearchDates

    stops = {0: MaxStops.NON_STOP, 1: MaxStops.ONE_STOP_OR_FEWER, 2: MaxStops.TWO_OR_FEWER_STOPS}
    segments, trip_type = build_date_search_segments(
        origin=Airport[home], destination=Airport[dest],
        start_date=start.isoformat(), trip_duration=days, is_round_trip=True,
    )
    filters = DateSearchFilters(
        trip_type=trip_type, passenger_info=PassengerInfo(adults=1), flight_segments=segments,
        stops=stops.get(cfg.max_stops, MaxStops.ANY), seat_type=SeatType.ECONOMY,
        from_date=start.isoformat(), to_date=end.isoformat(), duration=days,
    )
    res = SearchDates().search(filters, currency=cfg.currency, language="en")
    if res is None:          # fli returns None when Google sends back an empty error payload
        raise Blocked()
    return [(r.date[0].date().isoformat(), r.price) for r in res]


def _calendar_demo(cfg: Config, home: str, dest: str, days: int, start: date, end: date) -> list[tuple[str, float]]:
    rnd = random.Random(f"{home}{dest}{days}{start}")
    base = 2400 + 300 * (dest not in ("HND", "NRT", "KIX")) + 200 * (home not in ("WAW", "BER", "VIE"))
    n = (end - start).days + 1
    return [((start + timedelta(days=i)).isoformat(), round(base + 1200 * rnd.random() - 25 * (days - 14), -1))
            for i in range(n) if rnd.random() > 0.1]


class Cache:
    def __init__(self, cfg: Config, root: Path):
        self.cfg, self.root = cfg, root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key) -> Path:
        home, dest, days, start, end = key
        return self.root / f"{self.cfg.currency}-{self.cfg.max_stops}-{home}-{dest}-{days}-{start}-{end}.json"

    def get(self, key):
        p = self._path(key)
        if p.exists() and time.time() - p.stat().st_mtime < self.cfg.cache_hours * 3600:
            return json.loads(p.read_text())
        return None

    def put(self, key, rows):
        self._path(key).write_text(json.dumps(rows))


def search(cfg: Config, demo: bool = False, cache_dir: str = ".cache") -> tuple[list[Option], dict]:
    fetch = _calendar_demo if demo else _calendar
    cache = Cache(cfg, Path(cache_dir) / ("demo" if demo else "calendar"))
    # Order matters when a run gets cut off: cover every airport pair at a mid length first, then the rest.
    lengths = sorted(range(cfg.min_days, cfg.max_days + 1), key=lambda d: abs(d - (cfg.min_days + cfg.max_days) / 2))
    jobs = [(h, j, d, s, e) for d in lengths for (s, e) in _windows(cfg) for h in cfg.home for j in cfg.japan]

    todo = [k for k in jobs if cache.get(k) is None]
    print(f"{len(jobs)} calendar requests needed, {len(jobs) - len(todo)} cached, fetching {len(todo)}", file=sys.stderr)
    stopped = False
    for i, key in enumerate(todo, 1):
        for wait in (0, *cfg.backoff):
            if wait:
                print(f"  Google refused; waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
            try:
                cache.put(key, fetch(cfg, *key))
                break
            except Blocked:
                continue
            except Exception as e:  # network error, unknown airport, Google changed the response
                print(f"  ! {key}: {type(e).__name__}: {e}"[:200], file=sys.stderr)
                break
        else:
            print(f"Google keeps refusing after {i - 1} requests; stopping, next run continues.", file=sys.stderr)
            stopped = True
            break
        if i % 10 == 0:
            print(f"  {i}/{len(todo)}", file=sys.stderr)
        if not demo:
            time.sleep(cfg.delay)

    opts, done = [], 0
    for key in jobs:
        rows = cache.get(key)
        if rows is None:
            continue
        done += 1
        home, dest, days, _, _ = key
        for out, price in rows:
            d = date.fromisoformat(out)
            if cfg.depart_from <= d <= cfg.depart_to and price > 0:
                opts.append(Option(home, dest, d, d + timedelta(days=days), price))
    opts.sort(key=lambda o: o.price)
    return opts, {"done": done, "total": len(jobs), "stopped": stopped}
