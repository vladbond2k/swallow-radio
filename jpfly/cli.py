import argparse
import shutil
import sys
from pathlib import Path

from . import combine as C
from .config import load
from .report import console, write_csv, write_html
from .search import Searcher


def main():
    p = argparse.ArgumentParser(prog="jpfly", description="Find the cheapest home → Japan → home trip.")
    p.add_argument("-c", "--config", default="config.toml")
    p.add_argument("-o", "--out", default="out", help="output dir for report.html / trips.csv")
    p.add_argument("--top", type=int, default=100, help="trips shown in the HTML report")
    p.add_argument("--no-hubs", action="store_true", help="skip self-transfer search (much faster)")
    p.add_argument("--no-single", action="store_true", help="skip re-pricing best combos as one ticket")
    p.add_argument("--demo", action="store_true", help="fake prices, no network (to try the tool)")
    p.add_argument("--init", action="store_true", help="create config.toml from the example and exit")
    a = p.parse_args()

    if a.init:
        src = Path(__file__).parent.parent / "config.example.toml"
        if Path(a.config).exists():
            sys.exit(f"{a.config} already exists")
        shutil.copy(src, a.config)
        print(f"created {a.config} — edit origins/dates, then run: jpfly")
        return

    if not Path(a.config).exists():
        sys.exit(f"no {a.config}; run `jpfly --init` first")
    cfg = load(a.config)
    if a.no_hubs:
        cfg.hubs = []

    s = Searcher(cfg, demo=a.demo)
    s.prefetch(C.plan_jobs(cfg))
    outs, rets = C.build_options(cfg, s)
    trips = C.dedupe(C.combine(cfg, outs, rets))
    if not trips:
        sys.exit("no trips found — widen dates, add airports, or check the errors above")
    if not a.no_single and cfg.single_ticket_top:
        print(f"re-pricing top {cfg.single_ticket_top} combos as single tickets...", file=sys.stderr)
        C.check_single_tickets(cfg, s, trips)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    console(trips, cfg)
    write_csv(trips, out / "trips.csv")
    write_html(trips, cfg, out / "report.html", a.top, s.failed)
    print(f"\nreport: {out / 'report.html'}   all trips: {out / 'trips.csv'}")
    if s.failed:
        print(f"warning: {s.failed} searches failed; rerun later (cached ones are skipped)", file=sys.stderr)
