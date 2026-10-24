import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass
class Config:
    home: list[str]
    japan: list[str]
    depart_from: date
    depart_to: date
    min_days: int
    max_days: int
    max_stops: int = 2
    currency: str = "PLN"
    delay: float = 3.0                       # pause between requests, seconds
    backoff: tuple = (60,)          # waits after Google refuses, then give up for this run
    cache_hours: float = 30                  # answers older than this are fetched again


def load(path: str | Path) -> Config:
    raw = tomllib.loads(Path(path).read_text())
    trip = raw["trip"]
    cfg = Config(
        home=[a.upper() for a in raw["home"]["airports"]],
        japan=[a.upper() for a in raw["japan"]["airports"]],
        depart_from=date.fromisoformat(trip["depart_from"]),
        depart_to=date.fromisoformat(trip["depart_to"]),
        min_days=trip["min_days"],
        max_days=trip["max_days"],
        max_stops=trip.get("max_stops", 2),
        currency=raw.get("currency", "PLN").upper(),
    )
    g = raw.get("google", {})
    cfg.delay = g.get("delay", cfg.delay)
    cfg.backoff = tuple(g.get("backoff", cfg.backoff))
    cfg.cache_hours = g.get("cache_hours", cfg.cache_hours)
    if cfg.depart_to < cfg.depart_from or cfg.max_days < cfg.min_days:
        raise SystemExit("config: date range or trip length range is reversed")
    return cfg
