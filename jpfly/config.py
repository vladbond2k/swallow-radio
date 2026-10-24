import os
import tomllib
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


@dataclass
class Config:
    origins: dict[str, float]      # home airport -> ground cost each way
    japan: list[str]
    depart_from: date
    depart_to: date
    min_days: int
    max_days: int
    currency: str = "EUR"
    adults: int = 1
    max_stops: int = 2
    workers: int = 3
    delay: float = 1.0
    cache_hours: float = 12
    google: bool = True
    single_ticket_top: int = 20
    aviasales_token: str = ""

    def depart_dates(self) -> list[date]:
        return _days(self.depart_from, self.depart_to)

    def return_dates(self) -> list[date]:
        return _days(self.depart_from + timedelta(days=self.min_days),
                     self.depart_to + timedelta(days=self.max_days))


def _days(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def load(path: str | Path) -> Config:
    raw = tomllib.loads(Path(path).read_text())
    trip, g, av = raw["trip"], raw.get("google", {}), raw.get("aviasales", {})
    cfg = Config(
        origins={o["code"].upper(): o.get("extra_cost", 0) for o in raw["origins"]},
        japan=[a.upper() for a in raw["japan"]["airports"]],
        depart_from=date.fromisoformat(trip["depart_from"]),
        depart_to=date.fromisoformat(trip["depart_to"]),
        min_days=trip["min_days"],
        max_days=trip["max_days"],
        currency=raw.get("currency", "EUR"),
        adults=raw.get("adults", 1),
        max_stops=raw.get("max_stops", 2),
        google=g.get("enabled", True),
        workers=g.get("workers", 3),
        delay=g.get("delay", 1.0),
        cache_hours=g.get("cache_hours", 12),
        single_ticket_top=g.get("single_ticket_top", 20),
        aviasales_token=av.get("token") or os.environ.get("TRAVELPAYOUTS_TOKEN", ""),
    )
    if cfg.depart_to < cfg.depart_from or cfg.max_days < cfg.min_days:
        raise SystemExit("config: date range or trip length range is reversed")
    return cfg
