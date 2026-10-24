import argparse
import shutil
import sys
from pathlib import Path

from . import aviasales
from .config import load
from .google import Google
from .report import console, write_csv, write_html


def main():
    p = argparse.ArgumentParser(prog="jpfly", description="Cheapest home → Japan → home trips from Google Flights + Aviasales.")
    p.add_argument("-c", "--config", default="config.toml")
    p.add_argument("-o", "--out", default="out", help="output dir for report.html / trips.csv")
    p.add_argument("--limit", type=int, default=3000, help="max Google combos kept (cheapest first)")
    p.add_argument("--demo", action="store_true", help="fake prices, no network (to try the tool)")
    p.add_argument("--init", action="store_true", help="create config.toml from the example and exit")
    a = p.parse_args()

    if a.init:
        if Path(a.config).exists():
            sys.exit(f"{a.config} already exists")
        shutil.copy(Path(__file__).parent.parent / "config.example.toml", a.config)
        print(f"created {a.config}: set your home airports and dates, then run `jpfly`")
        return
    if not Path(a.config).exists():
        sys.exit(f"no {a.config}; run `jpfly --init` first")
    cfg = load(a.config)

    trips, warnings = [], []
    if cfg.google:
        g = Google(cfg, demo=a.demo)
        trips += g.trips(a.limit)
        if g.failed:
            warnings.append(f"{g.failed} Google searches failed (blocked or errored); rerun later to fill gaps.")
    trips += aviasales.trips(cfg, demo=a.demo)
    if not cfg.aviasales_token and not a.demo:
        warnings.append("Aviasales skipped: no token in config.")
    if not trips:
        sys.exit("nothing found; widen dates/airports or check the errors above")
    trips.sort(key=lambda t: t.total)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    console(trips, cfg)
    write_csv(trips, out / "trips.csv")
    write_html(trips, cfg, out / "report.html", warnings)
    print(f"\nopen {out / 'report.html'}  (all rows also in {out / 'trips.csv'})")
    for w in warnings:
        print("warning:", w, file=sys.stderr)
