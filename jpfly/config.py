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
    if cfg.depart_to < cfg.depart_from or cfg.max_days < cfg.min_days:
        raise SystemExit("config: date range or trip length range is reversed")
    return cfg
