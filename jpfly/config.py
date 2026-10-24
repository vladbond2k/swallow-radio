import tomllib
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path


@dataclass
class Origin:
    code: str
    extra_cost: float = 0


@dataclass
class Config:
    origins: list[Origin]
    japan: list[str]
    depart_from: date
    depart_to: date
    min_days: int
    max_days: int
    open_jaw: bool = True
    mix_home: bool = True
    currency: str = "EUR"
    adults: int = 1
    max_stops: int = 2
    workers: int = 3
    delay: float = 1.0
    cache_hours: float = 12
    hubs: list[str] = field(default_factory=list)
    hub_japan: list[str] = field(default_factory=list)
    min_conn_h: float = 3
    max_conn_h: float = 24
    single_ticket_top: int = 30

    def depart_dates(self) -> list[date]:
        return _days(self.depart_from, self.depart_to)

    def return_dates(self) -> list[date]:
        return _days(
            self.depart_from + timedelta(days=self.min_days),
            self.depart_to + timedelta(days=self.max_days),
        )

    def extra(self, code: str) -> float:
        return next((o.extra_cost for o in self.origins if o.code == code), 0)


def _days(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def load(path: str | Path) -> Config:
    raw = tomllib.loads(Path(path).read_text())
    trip, hubs, check = raw["trip"], raw.get("hubs", {}), raw.get("check", {})
    japan = [a.upper() for a in raw["japan"]["airports"]]
    cfg = Config(
        origins=[Origin(o["code"].upper(), o.get("extra_cost", 0)) for o in raw["origins"]],
        japan=japan,
        depart_from=date.fromisoformat(trip["depart_from"]),
        depart_to=date.fromisoformat(trip["depart_to"]),
        min_days=trip["min_days"],
        max_days=trip["max_days"],
        open_jaw=trip.get("open_jaw", True),
        mix_home=trip.get("mix_home", True),
        currency=raw.get("currency", "EUR"),
        adults=raw.get("adults", 1),
        max_stops=raw.get("max_stops", 2),
        workers=raw.get("workers", 3),
        delay=raw.get("delay", 1.0),
        cache_hours=raw.get("cache_hours", 12),
        hubs=[h.upper() for h in hubs.get("airports", [])] if hubs.get("enabled", True) else [],
        hub_japan=[a.upper() for a in hubs.get("japan_airports", japan)],
        min_conn_h=hubs.get("min_connection_hours", 3),
        max_conn_h=hubs.get("max_connection_hours", 24),
        single_ticket_top=check.get("single_ticket_top", 30),
    )
    if cfg.depart_to < cfg.depart_from or cfg.max_days < cfg.min_days:
        raise SystemExit("config: date range or trip length range is reversed")
    return cfg
