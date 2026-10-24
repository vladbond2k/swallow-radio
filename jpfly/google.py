"""Google Flights via fast-flights: one-way searches for every day, glued into trips, with a disk cache."""

import hashlib
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import Config
from .trips import Trip


@dataclass
class Ticket:
    src: str
    dst: str
    dep: datetime
    arr: datetime
    price: float
    airlines: list[str]
    via: list[str]

    def describe(self) -> str:
        route = "-".join([self.src, *self.via, self.dst])
        return f"{route} {self.dep:%d.%m %H:%M}→{self.arr:%d.%m %H:%M} {'/'.join(self.airlines)} ({self.price:g})"


def _query(cfg: Config, legs: list[tuple[str, str, date]]):
    from fast_flights import FlightQuery, Passengers, create_query

    if len(legs) == 1:
        trip = "one-way"
    elif legs[0][0] == legs[1][1] and legs[0][1] == legs[1][0]:
        trip = "round-trip"
    else:
        trip = "multi-city"
    return create_query(
        flights=[FlightQuery(date=d.isoformat(), from_airport=a, to_airport=b) for a, b, d in legs],
        trip=trip,
        passengers=Passengers(adults=cfg.adults),
        currency=cfg.currency,
        language="en",
        max_stops=cfg.max_stops,
    )


def url(cfg: Config, legs) -> str:
    return _query(cfg, legs).url()


def _fetch_google(cfg: Config, legs) -> list[dict]:
    from fast_flights import FlightsNotFound, get_flights

    try:
        res = get_flights(_query(cfg, legs))
    except FlightsNotFound:
        return []
    return [{
        "price": f.price,
        "airlines": list(f.airlines),
        "segments": [{
            "from": s.from_airport.code,
            "to": s.to_airport.code,
            "dep": datetime(*s.departure.date, *s.departure.time).isoformat(),
            "arr": datetime(*s.arrival.date, *s.arrival.time).isoformat(),
        } for s in f.flights],
    } for f in res if f.price and f.flights]


def _fetch_demo(cfg: Config, legs) -> list[dict]:
    """Fake but deterministic results, to try the tool without network."""
    a, b, d = legs[0]
    rnd = random.Random(str(legs))
    out = []
    for _ in range(rnd.randint(0, 5)):
        dep = datetime(d.year, d.month, d.day, rnd.randint(6, 22), rnd.choice([0, 15, 30, 45]))
        arr = dep + timedelta(minutes=rnd.randint(11 * 60, 26 * 60))
        pts = [a, *rnd.choice([[], ["IST"], ["DOH"], ["PEK"], ["HEL"]]), b]
        segs = [{"from": pts[i], "to": pts[i + 1], "dep": dep.isoformat(), "arr": arr.isoformat()}
                for i in range(len(pts) - 1)]
        out.append({"price": int(380 * len(legs) * 0.8 * rnd.uniform(0.75, 1.9)),
                    "airlines": [rnd.choice(["Turkish Airlines", "Qatar Airways", "Air China", "LOT", "Finnair"])],
                    "segments": segs})
    return out


class Google:
    def __init__(self, cfg: Config, demo: bool = False, cache_dir: str = ".cache"):
        self.cfg = cfg
        self.fetch = _fetch_demo if demo else _fetch_google
        self.cache = Path(cache_dir) / ("google-demo" if demo else "google")
        self.cache.mkdir(parents=True, exist_ok=True)
        self.failed = 0

    def _path(self, legs) -> Path:
        key = json.dumps([[(a, b, d.isoformat()) for a, b, d in legs],
                          self.cfg.currency, self.cfg.adults, self.cfg.max_stops])
        return self.cache / (hashlib.sha1(key.encode()).hexdigest() + ".json")

    def _cached(self, legs) -> list[dict] | None:
        p = self._path(legs)
        if p.exists() and time.time() - p.stat().st_mtime < self.cfg.cache_hours * 3600:
            return json.loads(p.read_text())
        return None

    def raw(self, legs) -> list[dict]:
        if (hit := self._cached(legs)) is not None:
            return hit
        err = None
        for attempt in range(3):
            try:
                data = self.fetch(self.cfg, legs)
                self._path(legs).write_text(json.dumps(data))
                return data
            except Exception as e:  # network errors, captcha pages, parser changes
                err = e
                time.sleep(self.cfg.delay * 3 * (attempt + 1))
            finally:
                time.sleep(self.cfg.delay)
        self.failed += 1
        print(f"  ! google {legs[0][0]}->{legs[0][1]} {legs[0][2]}: {type(err).__name__}: {err}"[:200],
              file=sys.stderr)
        return []

    def cheapest(self, src: str, dst: str, d: date) -> Ticket | None:
        best = min(self.raw([(src, dst, d)]), key=lambda r: r["price"], default=None)
        if best is None:
            return None
        segs = best["segments"]
        return Ticket(src, dst, datetime.fromisoformat(segs[0]["dep"]), datetime.fromisoformat(segs[-1]["arr"]),
                      best["price"], best["airlines"], [s["to"] for s in segs[:-1]])

    def trips(self, limit: int) -> list[Trip]:
        cfg = self.cfg
        D, R = cfg.depart_dates(), cfg.return_dates()
        jobs = [(h, j, d) for h in cfg.origins for j in cfg.japan for d in D]
        jobs += [(j, h, d) for j in cfg.japan for h in cfg.origins for d in R]
        todo = [j for j in jobs if self._cached([j]) is None]
        print(f"Google: {len(jobs)} one-way searches, {len(jobs) - len(todo)} cached, fetching {len(todo)}...",
              file=sys.stderr)
        with ThreadPoolExecutor(cfg.workers) as ex:
            for i, _ in enumerate(as_completed([ex.submit(self.raw, [j]) for j in todo]), 1):
                if i % 25 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)}", file=sys.stderr)

        outs = [t for h in cfg.origins for j in cfg.japan for d in D if (t := self.cheapest(h, j, d))]
        rets: dict[date, list[Ticket]] = {}
        for j in cfg.japan:
            for h in cfg.origins:
                for d in R:
                    if t := self.cheapest(j, h, d):
                        rets.setdefault(d, []).append(t)

        trips = []
        for o in outs:
            for n in range(cfg.min_days, cfg.max_days + 1):
                for r in rets.get(o.dep.date() + timedelta(days=n), []):
                    if r.dep > o.arr:
                        trips.append(self._trip(o, r))
        trips.sort(key=lambda t: t.total)
        trips = trips[:limit]
        self._single_tickets(trips)
        return trips

    def _trip(self, o: Ticket, r: Ticket) -> Trip:
        cfg = self.cfg
        return Trip(
            source="Google", kind="2 one-way tickets", price=o.price + r.price,
            extras=cfg.origins[o.src] + cfg.origins[r.dst],
            out_day=o.dep.date(), ret_day=r.dep.date(),
            home_out=o.src, jp_in=o.dst, jp_out=r.src, home_back=r.dst,
            stops_out=len(o.via), stops_back=len(r.via),
            airlines=" / ".join(dict.fromkeys(o.airlines + r.airlines)),
            out_desc=o.describe(), ret_desc=r.describe(),
            links=[("there", url(cfg, [(o.src, o.dst, o.dep.date())])),
                   ("back", url(cfg, [(r.src, r.dst, r.dep.date())]))],
        )

    def _single_tickets(self, trips: list[Trip]):
        """Round-trip tickets are often cheaper than two one-ways; re-price the best combos as one ticket."""
        n = self.cfg.single_ticket_top
        if not n:
            return
        print(f"Google: re-pricing top {n} as single tickets...", file=sys.stderr)
        seen = set()
        for t in trips:
            legs = [(t.home_out, t.jp_in, t.out_day), (t.jp_out, t.home_back, t.ret_day)]
            if tuple(legs) in seen:
                continue
            if len(seen) >= n:
                break
            seen.add(tuple(legs))
            prices = [r["price"] for r in self.raw(legs)]
            if prices and min(prices) < t.price:
                t.price, t.kind = min(prices), "one ticket"
                t.out_desc = "[exact flights: see link] " + t.out_desc
                t.links = [("ticket", url(self.cfg, legs))]
        trips.sort(key=lambda t: t.total)
