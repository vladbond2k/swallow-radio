from dataclasses import dataclass, field
from datetime import date


@dataclass
class Trip:
    """A full home -> Japan -> home option from one source."""

    source: str                  # "Google" / "Aviasales"
    kind: str                    # "round-trip ticket", "2 one-way tickets", ...
    price: float                 # what you pay for tickets
    extras: float                # ground transport to/from home airports
    out_day: date
    ret_day: date
    home_out: str
    jp_in: str
    jp_out: str
    home_back: str
    stops_out: int | None
    stops_back: int | None
    airlines: str
    out_desc: str
    ret_desc: str
    links: list[tuple[str, str]] = field(default_factory=list)   # (label, url)

    @property
    def total(self) -> float:
        return self.price + self.extras

    @property
    def days(self) -> int:
        return (self.ret_day - self.out_day).days
