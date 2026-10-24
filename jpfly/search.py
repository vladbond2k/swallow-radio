"""Two-stage search on Google Flights (via the `fli` library).

1. Calendar: cheapest round trip per departure day, one request per (home, Japan airport, trip length,
   ≤61-day window). Fast and mostly complete without filters, but with a layover limit Google only
   returns ~1 date per request, so the calendar is fetched unfiltered and serves as a price map.
2. Verify: for the cheapest calendar dates, a real round-trip flight search with the layover / travel
   time limits. Gives the true price under those limits plus the outbound flights.

Google refuses requests after a burst (~15–20 slow ones per IP), so every answer goes into an on-disk
store, a run stops on the first refusal, and the next run (or a parallel runner) continues.
"""

import json
import random
import sys
import time
from dataclasses import dataclass, field
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
    price: float                      # round trip, 1 adult
    verified: bool = False            # True: real search with the layover limit; False: calendar price
    flight: dict = field(default_factory=dict)   # outbound details for verified options

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


def _stops(cfg: Config):
    from fli.models import MaxStops

    return {0: MaxStops.NON_STOP, 1: MaxStops.ONE_STOP_OR_FEWER, 2: MaxStops.TWO_OR_FEWER_STOPS}.get(
        cfg.max_stops, MaxStops.ANY)


def _calendar(cfg: Config, home: str, dest: str, days: int, start: date, end: date) -> dict[str, float]:
    from fli.core.builders import build_date_search_segments
    from fli.models import Airport, DateSearchFilters, PassengerInfo, SeatType
    from fli.search import SearchDates

    segments, trip_type = build_date_search_segments(
        origin=Airport[home], destination=Airport[dest],
        start_date=start.isoformat(), trip_duration=days, is_round_trip=True,
    )
    filters = DateSearchFilters(
        trip_type=trip_type, passenger_info=PassengerInfo(adults=1), flight_segments=segments,
        stops=_stops(cfg), seat_type=SeatType.ECONOMY,
        from_date=start.isoformat(), to_date=end.isoformat(), duration=days,
    )
    res = SearchDates().search(filters, currency=cfg.currency, language="en", country=cfg.market)
    if res is None:          # fli returns None when Google sends back an empty error payload
        raise Blocked()
    return {r.date[0].date().isoformat(): r.price for r in res}


def _verify(cfg: Config, home: str, dest: str, out: date, back: date) -> dict:
    """Real round-trip search with the layover/travel limits; cheapest outbound row (its price is the round trip)."""
    from fli.core.builders import build_flight_segments
    from fli.models import Airport, FlightSearchFilters, LayoverRestrictions, PassengerInfo, SeatType
    from fli.search import SearchFlights
    from fli.search._decoders import parse_flight_row
    from fli.search._urls import with_locale_params
    from fli.search._wire import parse_first_wrb_payload

    segments, trip_type = build_flight_segments(
        origin=Airport[home], destination=Airport[dest], departure_date=out.isoformat(), return_date=back.isoformat())
    filters = FlightSearchFilters(
        trip_type=trip_type, passenger_info=PassengerInfo(adults=1), flight_segments=segments,
        stops=_stops(cfg), seat_type=SeatType.ECONOMY,
        layover_restrictions=(LayoverRestrictions(max_duration=int(cfg.max_layover_hours * 60))
                              if cfg.max_layover_hours else None),
        max_duration=int(cfg.max_travel_hours * 60) or None,
    )
    s = SearchFlights()
    url = with_locale_params(s.BASE_URL, cfg.currency, "en", cfg.market)
    resp = s.client.post(url=url, data=f"f.req={filters.encode()}", impersonate="chrome", allow_redirects=True)
    inner = parse_first_wrb_payload(resp.text)
    if inner is None:
        raise Blocked()
    rows = [r for i in (2, 3) if isinstance(inner[i], list) for r in inner[i][0]]
    best = None
    for row in rows:
        try:
            f = parse_flight_row(row)
        except Exception:
            continue
        if f.price and (best is None or f.price < best.price):
            best = f
    if best is None:
        return {"price": None}
    return {
        "price": best.price,
        "airlines": list(dict.fromkeys(leg.airline.name.replace("_", " ").title() for leg in best.legs)),
        "route": [best.legs[0].departure_airport.name] + [leg.arrival_airport.name for leg in best.legs],
        "dep": best.legs[0].departure_datetime.isoformat(timespec="minutes"),
        "arr": best.legs[-1].arrival_datetime.isoformat(timespec="minutes"),
        "hours": round(best.duration / 60, 1),
        "layovers": [round(lo.duration / 60, 1) for lo in best.layovers or []],
    }


def _calendar_demo(cfg: Config, home: str, dest: str, days: int, start: date, end: date) -> dict[str, float]:
    rnd = random.Random(f"{home}{dest}{days}{start}")
    base = 2400 + 300 * (dest not in ("HND", "NRT", "KIX")) + 200 * (home not in ("WAW", "BER", "VIE"))
    n = (end - start).days + 1
    return {(start + timedelta(days=i)).isoformat(): round(base + 1200 * rnd.random() - 25 * (days - 14), -1)
            for i in range(n) if rnd.random() > 0.1}


def _verify_demo(cfg: Config, home: str, dest: str, out: date, back: date) -> dict:
    rnd = random.Random(f"{home}{dest}{out}{back}")
    if rnd.random() < 0.2:
        return {"price": None}
    lay = round(rnd.uniform(1, cfg.max_layover_hours or 8), 1)
    return {"price": 2700 + rnd.randint(0, 1500), "airlines": [rnd.choice(["Lot", "Turkish Airlines", "Finnair"])],
            "route": [home, rnd.choice(["IST", "HEL", "DOH"]), dest], "dep": f"{out}T10:05",
            "arr": f"{out + timedelta(days=1)}T08:40", "hours": round(14 + lay, 1), "layovers": [lay]}


class Store:
    """JSON records on disk, one file per request, merged across runs and parallel runners."""

    def __init__(self, root: Path, max_age_h: float):
        self.root, self.max_age = Path(root), max_age_h * 3600
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return self.root / f"{name}.json"

    def read(self, name: str) -> dict | None:
        p = self.path(name)
        return json.loads(p.read_text()) if p.exists() else None

    def write(self, name: str, rec: dict):
        self.path(name).write_text(json.dumps(rec))

    def absorb(self, other_root: Path):
        """Merge another store (e.g. from a parallel runner): newest wins; calendar prices merge per date."""
        for f in Path(other_root).glob("*.json"):
            theirs, mine = json.loads(f.read_text()), self.read(f.stem)
            if mine is None:
                self.write(f.stem, theirs)
            elif "prices" in theirs:
                mine["asked"] = max(mine.get("asked", 0), theirs.get("asked", 0))
                for d, v in theirs["prices"].items():
                    if d not in mine["prices"] or v[1] > mine["prices"][d][1]:
                        mine["prices"][d] = v
                self.write(f.stem, mine)
            elif theirs.get("asked", 0) > mine.get("asked", 0):
                self.write(f.stem, theirs)


def store_dir(cache_dir: str, demo: bool) -> Path:
    return Path(cache_dir) / ("demo" if demo else "calendar")


class Searcher:
    def __init__(self, cfg: Config, demo: bool, cache_dir: str):
        self.cfg, self.demo = cfg, demo
        self.store = Store(store_dir(cache_dir, demo), cfg.cache_hours)
        self.cal_fetch = _calendar_demo if demo else _calendar
        self.ver_fetch = _verify_demo if demo else _verify
        lengths = sorted(range(cfg.min_days, cfg.max_days + 1),
                         key=lambda d: abs(d - (cfg.min_days + cfg.max_days) / 2))
        self.cal_jobs = [(h, j, d, s, e) for d in lengths for (s, e) in _windows(cfg)
                         for h in cfg.home for j in cfg.japan]
        self.limited = bool(cfg.max_layover_hours or cfg.max_travel_hours)
        self.asked = 0

    # Record names. The calendar one has no layover part on purpose: it is always fetched unfiltered.
    def cal_name(self, key) -> str:
        home, dest, days, start, end = key
        return f"{self.cfg.currency}-{self.cfg.max_stops}-{home}-{dest}-{days}-{start}-{end}"

    def ver_name(self, home, dest, out, back) -> str:
        c = self.cfg
        return f"v-{c.currency}-s{c.max_stops}-l{c.max_layover_hours:g}-t{c.max_travel_hours:g}-{home}-{dest}-{out}-{back}"

    def cal_prices(self, key) -> dict:
        rec = self.store.read(self.cal_name(key)) or {"prices": {}}
        cutoff = time.time() - self.store.max_age
        return {d: v[0] for d, v in rec["prices"].items() if v[1] >= cutoff}

    def cal_complete(self, key) -> bool:
        _, _, _, start, end = key
        return len(self.cal_prices(key)) >= COMPLETE * ((end - start).days + 1)

    def verified(self, o: "Option") -> dict | None:
        rec = self.store.read(self.ver_name(o.home, o.dest, o.out, o.back))
        if rec and time.time() - rec["asked"] < self.store.max_age:
            return rec
        return None

    def _ask(self, fn, *args):
        """One request with backoff. Returns the answer, or None on a non-rate-limit error; raises Blocked to stop."""
        for wait in (0, *self.cfg.backoff):
            if wait:
                print(f"  Google refused; waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
            try:
                res = fn(self.cfg, *args)
                self.asked += 1
                if not self.demo:
                    time.sleep(self.cfg.delay)
                return res
            except Blocked:
                continue
            except Exception as e:  # network error, unknown airport, Google changed the response
                print(f"  ! {args}: {type(e).__name__}: {e}"[:200], file=sys.stderr)
                return None
        raise Blocked()

    def candidates(self) -> list[Option]:
        """Calendar options, cheapest first, one per (home, dest, out, back)."""
        best = {}
        for key in self.cal_jobs:
            home, dest, days, _, _ = key
            for out, price in self.cal_prices(key).items():
                d = date.fromisoformat(out)
                if not (self.cfg.depart_from <= d <= self.cfg.depart_to) or price <= 0:
                    continue
                o = Option(home, dest, d, d + timedelta(days=days), price)
                k = (home, dest, o.out, o.back)
                if k not in best or price < best[k].price:
                    best[k] = o
        return sorted(best.values(), key=lambda o: o.price)

    def _verify_some(self, i: int, n: int, budget: int) -> int:
        """Re-check up to `budget` of the cheapest unverified calendar dates owned by this shard."""
        todo = [o for o in self.candidates()[: self.cfg.verify_top] if not self.verified(o)]
        todo = [o for idx, o in enumerate(todo) if idx % n == i][:budget]
        if todo:
            print(f"verify: {len(todo)} cheapest dates with the layover limit", file=sys.stderr)
        for o in todo:
            res = self._ask(self.ver_fetch, o.home, o.dest, o.out, o.back)
            if res is not None:
                self.store.write(self.ver_name(o.home, o.dest, o.out, o.back), {"asked": time.time(), **res})
                print(f"  {o.home}->{o.dest} {o.out}..{o.back}: calendar {o.price:g}, "
                      f"within limits {res.get('price') or 'none'}", file=sys.stderr)
        return len(todo)

    def run(self, shard: tuple[int, int]):
        i, n = shard
        try:
            # 1) Verify the cheapest known dates first: verified options are what the page shows.
            used = self._verify_some(i, n, self.cfg.verify_per_run) if self.limited else 0
            # 2) Fill the calendar with whatever quota is left.
            mine = [k for idx, k in enumerate(self.cal_jobs) if idx % n == i]
            todo = sorted((k for k in mine if not self.cal_complete(k)),
                          key=lambda k: (self.store.read(self.cal_name(k)) or {}).get("asked", 0))
            print(f"calendar: {len(self.cal_jobs)} total, shard {i + 1}/{n} asking {len(todo)}", file=sys.stderr)
            for key in todo:
                got = self._ask(self.cal_fetch, *key)
                if got is None:
                    continue
                rec = self.store.read(self.cal_name(key)) or {"asked": 0, "prices": {}}
                now = time.time()
                rec["asked"] = now
                rec["prices"].update({d: [p, now] for d, p in got.items()})
                self.store.write(self.cal_name(key), rec)
                print(f"  {key[0]}->{key[1]} {key[2]}d {key[3]}: {len(got)} dates", file=sys.stderr)
            # 3) Calendar done and quota left: verify the dates it just revealed.
            if self.limited:
                self._verify_some(i, n, self.cfg.verify_per_run - used)
        except Blocked:
            print(f"Google refuses after {self.asked} requests; stopping. The next run continues.", file=sys.stderr)

    def results(self) -> tuple[list[Option], dict]:
        cands = self.candidates()
        if not self.limited:
            opts = cands
        else:
            opts = []
            for o in cands:
                v = self.verified(o)
                if v and v.get("price"):
                    opts.append(Option(o.home, o.dest, o.out, o.back, v["price"], True,
                                       {k: v[k] for k in ("airlines", "route", "dep", "arr", "hours", "layovers")
                                        if k in v}))
            opts.sort(key=lambda o: o.price)
        st = {
            "cal_total": len(self.cal_jobs),
            "cal_complete": sum(self.cal_complete(k) for k in self.cal_jobs),
            "cal_with_data": sum(bool(self.cal_prices(k)) for k in self.cal_jobs),
            "verified": sum(1 for o in cands[: self.cfg.verify_top] if self.verified(o)),
            "verify_top": min(self.cfg.verify_top, len(cands)),
            "limited": self.limited,
        }
        return opts, cands, st


def search(cfg: Config, demo: bool = False, cache_dir: str = ".cache", shard: tuple[int, int] = (0, 1),
           fetch_enabled: bool = True):
    s = Searcher(cfg, demo, cache_dir)
    if fetch_enabled:
        s.run(shard)
    return s.results()
