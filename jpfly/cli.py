import argparse
import sys
from pathlib import Path

from .config import load
from .report import console, write_csv, write_html
from .search import search


def main():
    p = argparse.ArgumentParser(prog="jpfly", description="Cheapest dates for a round trip to Japan (Google Flights).")
    p.add_argument("-c", "--config", default="config.toml")
    p.add_argument("-o", "--out", default="out", help="output dir for index.html / trips.csv")
    p.add_argument("--demo", action="store_true", help="fake prices, no network (to try the page)")
    a = p.parse_args()

    if not Path(a.config).exists():
        sys.exit(f"no {a.config}; copy config.example.toml to {a.config}")
    cfg = load(a.config)
    opts, st = search(cfg, demo=a.demo)

    warnings = []
    if st["complete"] < st["total"]:
        warnings.append(f"Собрано {st['complete']} из {st['total']} календарей полностью, ещё {st['with_data'] - st['complete']} "
                        f"частично. Google отдаёт данные порциями и ограничивает частоту запросов — "
                        f"календарь дополняется каждые 2 часа.")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    write_html(opts, cfg, out / "index.html", warnings, a.demo)
    write_csv(opts, out / "trips.csv")
    console(opts, cfg)
    print(f"\nopen {out / 'index.html'}")
    if not opts:
        sys.exit("nothing found; see errors above")
