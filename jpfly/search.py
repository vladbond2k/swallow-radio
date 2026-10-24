"""Google Flights price calendar (via the `fli` library): cheapest round trip per departure day.

One request = one (home airport, Japan airport, trip length, ≤61-day window). What we learned from Google:
- multi-airport requests are slow and return ~1 date, so airports are never combined;
- for some routes the calendar comes back complete in 0.1s, for others it returns 1–10 dates
  after 15–30s, and asking again later can return different dates;
- after ~20 slow requests Google starts answering with an empty error payload for a while.

So every answer is merged into a store (date -> price, with a timestamp), incomplete calendars
are asked again in later runs, and a run stops as soon as Google starts refusing. Runs every
couple of hours fill the calendar up.
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
COMPLETE = 0.8           # a calendar with at least this share of the window's days counts as complete


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


def _calendar(cfg: Config, home: str, dest: str, days: int, start: date, end: date) -> dict[str, float]:
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
    return {r.date[0].date().isoformat(): r.price for r in res}


def _calendar_demo(cfg: Config, home: str, dest: str, days: int, start: date, end: date) -> dict[str, float]:
    rnd = random.Random(f"{home}{dest}{days}{start}")
    base = 2400 + 300 * (dest not in ("HND", "NRT", "KIX")) + 200 * (home not in ("WAW", "BER", "VIE"))
    n = (end - start).days + 1
    return {(start + timedelta(days=i)).isoformat(): round(base + 1200 * rnd.random() - 25 * (days - 14), -1)
            for i in range(n) if rnd.random() > 0.1}


class Store:
    """Calendar answers on disk: one JSON per request key, {"asked": ts, "prices": {date: [price, ts]}}."""

    def __init__(self, cfg: Config, root: Path):
        self.cfg, self.root = cfg, root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key) -> Path:
        home, dest, days, start, end = key
        return self.root / f"{self.cfg.currency}-{self.cfg.max_stops}-{home}-{dest}-{days}-{start}-{end}.json"

    def load(self, key) -> dict:
        p = self._path(key)
        rec = json.loads(p.read_text()) if p.exists() else {"asked": 0, "prices": {}}
        cutoff = time.time() - self.cfg.cache_hours * 3600
        rec["prices"] = {d: v for d, v in rec["prices"].items() if v[1] >= cutoff}
        return rec

    def merge(self, key, prices: dict[str, float]):
        rec, now = self.load(key), time.time()
        rec["asked"] = now
        rec["prices"].update({d: [p, now] for d, p in prices.items()})
        self._path(key).write_text(json.dumps(rec))

    def complete(self, key) -> bool:
        _, _, _, start, end = key
        return len(self.load(key)["prices"]) >= COMPLETE * ((end - start).days + 1)


def search(cfg: Config, demo: bool = False, cache_dir: str = ".cache") -> tuple[list[Option], dict]:
    fetch = _calendar_demo if demo else _calendar
    store = Store(cfg, Path(cache_dir) / ("demo" if demo else "calendar"))
    lengths = sorted(range(cfg.min_days, cfg.max_days + 1), key=lambda d: abs(d - (cfg.min_days + cfg.max_days) / 2))
    jobs = [(h, j, d, s, e) for d in lengths for (s, e) in _windows(cfg) for h in cfg.home for j in cfg.japan]

    # Never-asked first, then incomplete calendars asked longest ago; complete ones are skipped until they expire.
    todo = sorted((k for k in jobs if not store.complete(k)), key=lambda k: store.load(k)["asked"])
    print(f"{len(jobs)} calendars, {len(jobs) - len(todo)} complete, asking {len(todo)} (until Google refuses)",
          file=sys.stderr)
    asked, stopped = 0, False
    for key in todo:
        for wait in (0, *cfg.backoff):
            if wait:
                print(f"  Google refused; waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
            try:
                got = fetch(cfg, *key)
                store.merge(key, got)
                asked += 1
                print(f"  {key[0]}->{key[1]} {key[2]}d {key[3]}: {len(got)} dates", file=sys.stderr)
                break
            except Blocked:
                continue
            except Exception as e:  # network error, unknown airport, Google changed the response
                print(f"  ! {key}: {type(e).__name__}: {e}"[:200], file=sys.stderr)
                break
        else:
            print(f"Google refuses after {asked} requests; stopping. The next run continues.", file=sys.stderr)
            stopped = True
            break
        if not demo:
            time.sleep(cfg.delay)

    opts, have = [], 0
    for key in jobs:
        prices = store.load(key)["prices"]
        have += bool(prices)
        home, dest, days, _, _ = key
        for out, (price, _) in prices.items():
            d = date.fromisoformat(out)
            if cfg.depart_from <= d <= cfg.depart_to and price > 0:
                opts.append(Option(home, dest, d, d + timedelta(days=days), price))
    opts.sort(key=lambda o: o.price)
    complete = sum(store.complete(k) for k in jobs)
    return opts, {"total": len(jobs), "complete": complete, "with_data": have, "asked": asked, "stopped": stopped}
