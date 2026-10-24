"""Fetching flight prices from Google Flights (via fast-flights), with a disk cache."""

import hashlib
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .config import Config


@dataclass
class Ticket:
    """One bookable ticket in one direction (may contain several flights)."""

    src: str
    dst: str
    dep: datetime
    arr: datetime
    price: float
    airlines: list[str]
    via: list[str]
    url: str

    @property
    def stops(self) -> int:
        return len(self.via)


def _q(cfg: Config, trip: str, legs: list[tuple[str, str, date]]):
    from fast_flights import FlightQuery, Passengers, create_query

    return create_query(
        flights=[FlightQuery(date=d.isoformat(), from_airport=a, to_airport=b) for a, b, d in legs],
        trip=trip,
        passengers=Passengers(adults=cfg.adults),
        currency=cfg.currency,
        language="en",
        max_stops=cfg.max_stops,
    )


def search_url(cfg: Config, legs: list[tuple[str, str, date]]) -> str:
    trip = "one-way" if len(legs) == 1 else (
        "round-trip" if legs[0][0] == legs[1][1] and legs[0][1] == legs[1][0] else "multi-city")
    try:
        return _q(cfg, trip, legs).url()
    except ImportError:
        a, b, d = legs[0]
        return f"https://www.google.com/travel/flights?q=Flights%20from%20{a}%20to%20{b}%20on%20{d}"


def _google_fetch(cfg: Config, trip: str, legs) -> list[dict]:
    from fast_flights import FlightsNotFound, get_flights

    try:
        res = get_flights(_q(cfg, trip, legs))
    except FlightsNotFound:
        return []
    out = []
    for f in res:
        if not f.price or not f.flights:
            continue
        out.append({
            "price": f.price,
            "airlines": list(f.airlines),
            "segments": [{
                "from": s.from_airport.code,
                "to": s.to_airport.code,
                "dep": datetime(*s.departure.date, *s.departure.time).isoformat(),
                "arr": datetime(*s.arrival.date, *s.arrival.time).isoformat(),
            } for s in f.flights],
        })
    return out


def _demo_fetch(cfg: Config, trip: str, legs) -> list[dict]:
    """Fake but deterministic prices, for trying the tool without network."""
    a, b, d = legs[0]
    rnd = random.Random(f"{trip}{legs}")
    far = (a in cfg.japan + cfg.hub_japan) != (b in cfg.japan + cfg.hub_japan)
    base = (380 if far else 70) * (1.6 if trip != "one-way" else 1)
    out = []
    for _ in range(rnd.randint(0, 6)):
        dep = datetime(d.year, d.month, d.day, rnd.randint(6, 22), rnd.choice([0, 15, 30, 45]))
        hours = rnd.uniform(11, 26) if far else rnd.uniform(2, 6)
        arr = datetime.fromtimestamp(dep.timestamp() + hours * 3600).replace(second=0, microsecond=0)
        via = rnd.choice([[], ["IST"], ["DOH"], ["PEK", "PVG"]]) if far else []
        pts = [a, *via, b]
        out.append({
            "price": int(base * rnd.uniform(0.7, 1.9)),
            "airlines": [rnd.choice(["Turkish", "Qatar", "Air China", "LOT", "Emirates", "Wizz"])],
            "segments": [{"from": pts[i], "to": pts[i + 1], "dep": dep.isoformat() if i == 0 else None,
                          "arr": arr.isoformat() if i == len(pts) - 2 else None} for i in range(len(pts) - 1)],
        })
    return out


class Searcher:
    def __init__(self, cfg: Config, demo: bool = False, cache_dir: str = ".cache"):
        self.cfg = cfg
        self.fetch = _demo_fetch if demo else _google_fetch
        self.cache_dir = Path(cache_dir) / ("demo" if demo else "google")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.failed = 0
        self._lock = threading.Lock()

    def _key(self, trip, legs) -> Path:
        raw = json.dumps([trip, [(a, b, d.isoformat()) for a, b, d in legs],
                          self.cfg.currency, self.cfg.adults, self.cfg.max_stops])
        return self.cache_dir / (hashlib.sha1(raw.encode()).hexdigest() + ".json")

    def cached(self, trip, legs) -> list[dict] | None:
        p = self._key(trip, legs)
        if p.exists() and time.time() - p.stat().st_mtime < self.cfg.cache_hours * 3600:
            return json.loads(p.read_text())
        return None

    def raw(self, trip: str, legs) -> list[dict]:
        hit = self.cached(trip, legs)
        if hit is not None:
            return hit
        for attempt in range(3):
            try:
                data = self.fetch(self.cfg, trip, legs)
                self._key(trip, legs).write_text(json.dumps(data))
                return data
            except Exception as e:  # network errors, captcha pages, parser changes
                err = e
                time.sleep(self.cfg.delay * 3 * (attempt + 1))
            finally:
                time.sleep(self.cfg.delay)
        with self._lock:
            self.failed += 1
        print(f"  ! {trip} {legs[0][0]}->{legs[0][1]} {legs[0][2]}: {type(err).__name__}: {err}"[:200],
              file=sys.stderr)
        return []

    def tickets(self, src: str, dst: str, d: date) -> list[Ticket]:
        legs = [(src, dst, d)]
        url = search_url(self.cfg, legs)
        out = []
        for r in self.raw("one-way", legs):
            segs = r["segments"]
            out.append(Ticket(
                src=src, dst=dst,
                dep=datetime.fromisoformat(segs[0]["dep"]),
                arr=datetime.fromisoformat(segs[-1]["arr"]),
                price=r["price"], airlines=r["airlines"],
                via=[s["to"] for s in segs[:-1]], url=url,
            ))
        return sorted(out, key=lambda t: t.price)

    def single_ticket_price(self, legs) -> float | None:
        """Price of the whole round-trip / multi-city itinerary as one ticket."""
        trip = "round-trip" if legs[0][0] == legs[1][1] and legs[0][1] == legs[1][0] else "multi-city"
        prices = [r["price"] for r in self.raw(trip, legs) if r["price"]]
        return min(prices) if prices else None

    def prefetch(self, jobs: list[tuple[str, str, date]]):
        """Fetch many one-way searches in parallel (results land in the cache)."""
        jobs = list(dict.fromkeys(jobs))
        todo = [j for j in jobs if self.cached("one-way", [j]) is None]
        print(f"{len(jobs)} searches, {len(jobs) - len(todo)} cached, fetching {len(todo)}...", file=sys.stderr)
        done = 0
        with ThreadPoolExecutor(self.cfg.workers) as ex:
            for _ in as_completed([ex.submit(self.raw, "one-way", [j]) for j in todo]):
                done += 1
                if done % 20 == 0 or done == len(todo):
                    print(f"  {done}/{len(todo)}", file=sys.stderr)
