"""Turn one-way tickets into full trips and rank them."""

from dataclasses import dataclass, field
from datetime import date, timedelta

from .config import Config
from .search import Searcher, Ticket, search_url


@dataclass
class Option:
    """One direction of the trip: one ticket, or two separate tickets glued at a hub."""

    tickets: list[Ticket]

    @property
    def price(self) -> float:
        return sum(t.price for t in self.tickets)

    @property
    def src(self) -> str:
        return self.tickets[0].src

    @property
    def dst(self) -> str:
        return self.tickets[-1].dst

    @property
    def day(self) -> date:
        return self.tickets[0].dep.date()

    @property
    def hub(self) -> str | None:
        return self.tickets[0].dst if len(self.tickets) > 1 else None

    def describe(self) -> str:
        parts = []
        for t in self.tickets:
            route = "-".join([t.src, *t.via, t.dst])
            parts.append(f"{route} {t.dep:%d.%m %H:%M}→{t.arr:%d.%m %H:%M} {'/'.join(t.airlines)} {t.price:g}")
        return "  +  ".join(parts)


@dataclass
class Trip:
    out: Option
    ret: Option
    extras: float
    single_ticket: float | None = None   # price if bought as one RT / multi-city ticket
    single_url: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def separate_total(self) -> float:
        return self.out.price + self.ret.price + self.extras

    @property
    def total(self) -> float:
        if self.single_ticket is not None:
            return min(self.separate_total, self.single_ticket + self.extras)
        return self.separate_total

    @property
    def days(self) -> int:
        return (self.ret.day - self.out.day).days


def _best(opts: dict, key, opt: Option):
    cur = opts.get(key)
    if cur is None or opt.price < cur.price:
        opts[key] = opt


def _glue(first: list[Ticket], second_by_day, cfg: Config) -> Option | None:
    """Cheapest valid self-transfer: ticket from `first` then a later ticket out of the hub."""
    best = None
    lo, hi = timedelta(hours=cfg.min_conn_h), timedelta(hours=cfg.max_conn_h)
    for a in first:
        for d in (a.arr.date(), a.arr.date() + timedelta(days=1)):
            for b in second_by_day(d):
                if lo <= b.dep - a.arr <= hi and (best is None or a.price + b.price < best.price):
                    best = Option([a, b])
    return best


def plan_jobs(cfg: Config) -> list[tuple[str, str, date]]:
    homes = [o.code for o in cfg.origins]
    D, R = cfg.depart_dates(), cfg.return_dates()
    plus1 = lambda days: sorted({x for d in days for x in (d, d + timedelta(days=1))})
    jobs = [(h, j, d) for h in homes for j in cfg.japan for d in D]
    jobs += [(j, h, d) for j in cfg.japan for h in homes for d in R]
    for hub in cfg.hubs:
        jobs += [(h, hub, d) for h in homes for d in D]
        jobs += [(hub, j, d) for j in cfg.hub_japan for d in plus1(D)]
        jobs += [(j, hub, d) for j in cfg.hub_japan for d in R]
        jobs += [(hub, h, d) for h in homes for d in plus1(R)]
    return jobs


def build_options(cfg: Config, s: Searcher):
    homes = [o.code for o in cfg.origins]
    D, R = cfg.depart_dates(), cfg.return_dates()
    outs, rets = {}, {}  # (src, dst, day, kind) -> cheapest Option

    for h in homes:
        for j in cfg.japan:
            for d in D:
                if t := s.tickets(h, j, d):
                    _best(outs, (h, j, d, "direct"), Option([t[0]]))
            for d in R:
                if t := s.tickets(j, h, d):
                    _best(rets, (j, h, d, "direct"), Option([t[0]]))

    for hub in cfg.hubs:
        if hub in homes or hub in cfg.japan:
            continue
        for h in homes:
            for j in cfg.hub_japan:
                for d in D:
                    if o := _glue(s.tickets(h, hub, d), lambda x: s.tickets(hub, j, x), cfg):
                        _best(outs, (h, j, d, "hub"), o)
                for d in R:
                    if o := _glue(s.tickets(j, hub, d), lambda x: s.tickets(hub, h, x), cfg):
                        _best(rets, (j, h, d, "hub"), o)
    return list(outs.values()), list(rets.values())


def combine(cfg: Config, outs: list[Option], rets: list[Option]) -> list[Trip]:
    by_day: dict[date, list[Option]] = {}
    for r in rets:
        by_day.setdefault(r.day, []).append(r)
    trips = []
    for o in outs:
        for n in range(cfg.min_days, cfg.max_days + 1):
            for r in by_day.get(o.day + timedelta(days=n), []):
                if not cfg.open_jaw and r.src != o.dst:
                    continue
                if not cfg.mix_home and r.dst != o.src:
                    continue
                if r.tickets[0].dep < o.tickets[-1].arr:
                    continue
                trips.append(Trip(o, r, cfg.extra(o.src) + cfg.extra(r.dst)))
    trips.sort(key=lambda t: t.total)
    return trips


def check_single_tickets(cfg: Config, s: Searcher, trips: list[Trip]):
    """Re-price the best date/airport combos as one ticket; legacy carriers often price RT below 2x one-way."""
    seen = set()
    for t in trips:
        if len(seen) >= cfg.single_ticket_top:
            break
        legs = [(t.out.src, t.out.dst, t.out.day), (t.ret.src, t.ret.dst, t.ret.day)]
        key = tuple(legs)
        if key in seen:
            continue
        seen.add(key)
        price = s.single_ticket_price(legs)
        if price:
            t.single_ticket, t.single_url = price, search_url(cfg, legs)
    trips.sort(key=lambda t: t.total)


def dedupe(trips: list[Trip]) -> list[Trip]:
    """Keep the best trip per (home out, japan in, japan out, home back, out day, back day)."""
    seen, out = set(), []
    for t in trips:
        k = (t.out.src, t.out.dst, t.ret.src, t.ret.dst, t.out.day, t.ret.day)
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out
