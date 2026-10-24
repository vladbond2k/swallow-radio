import argparse
import sys
from pathlib import Path

from .config import load
from .report import console, write_csv, write_html
from .search import Store, search, store_dir


def main():
    p = argparse.ArgumentParser(prog="jpfly", description="Cheapest dates for a round trip to Japan (Google Flights).")
    p.add_argument("-c", "--config", default="config.toml")
    p.add_argument("-o", "--out", default="out", help="output dir for index.html / trips.csv")
    p.add_argument("--demo", action="store_true", help="fake prices, no network (to try the page)")
    p.add_argument("--shard", default="1/1", help="I/N: this runner asks every N-th calendar (parallel runners)")
    p.add_argument("--no-fetch", action="store_true", help="don't ask Google, just build the page from the cache")
    p.add_argument("--merge", nargs="*", default=[], help="cache dirs from other runners to merge in first")
    a = p.parse_args()

    if not Path(a.config).exists():
        sys.exit(f"no {a.config}; copy config.example.toml to {a.config}")
    cfg = load(a.config)
    for d in a.merge:
        Store(cfg, store_dir(".cache", a.demo)).absorb(Path(d))
    i, n = map(int, a.shard.split("/"))
    opts, st = search(cfg, demo=a.demo, shard=(i - 1, n), fetch_enabled=not a.no_fetch)

    warnings = []
    if st["complete"] < st["total"]:
        warnings.append(f"Собрано {st['complete']} из {st['total']} календарей полностью, ещё {st['with_data'] - st['complete']} "
                        f"частично. Google отдаёт данные порциями и ограничивает частоту запросов — "
                        f"календарь дополняется каждые 30 минут.")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    write_html(opts, cfg, out / "index.html", warnings, a.demo)
    write_csv(opts, out / "trips.csv")
    console(opts, cfg)
    print(f"\nopen {out / 'index.html'}")
    if not opts and a.shard == "1/1":   # parallel runners may legitimately end up with nothing
        sys.exit("nothing found; see errors above")
