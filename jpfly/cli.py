import argparse
import json
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
        Store(store_dir(".cache", a.demo), cfg.cache_hours).absorb(Path(d))
    i, n = map(int, a.shard.split("/"))
    opts, cands, st = search(cfg, demo=a.demo, shard=(i - 1, n), fetch_enabled=not a.no_fetch)

    warnings = []
    if st["cal_complete"] < st["cal_total"]:
        warnings.append(f"Календарь цен: {st['cal_complete']} из {st['cal_total']} собрано полностью, "
                        f"{st['cal_with_data'] - st['cal_complete']} частично. Дополняется при следующих запусках.")
    if st["limited"] and st["verified"] < st["verify_top"]:
        warnings.append(f"С учётом лимита пересадок проверено {st['verified']} из {st['verify_top']} самых дешёвых "
                        f"дат — список ниже растёт с каждым запуском.")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    write_html(opts, cands, cfg, out / "index.html", warnings, a.demo)
    write_csv(opts, out / "trips.csv")
    # Read by the workflow to decide whether to chain another run right away.
    done = st["cal_asked"] >= st["cal_total"] and (not st["limited"] or st["verified"] >= 0.9 * st["verify_top"])
    (out / "status.json").write_text(json.dumps({**st, "done": done}))
    console(opts, cfg)
    print(f"\nopen {out / 'index.html'}")
    if not opts and a.shard == "1/1":   # parallel runners may legitimately end up with nothing
        sys.exit("nothing found; see errors above")
