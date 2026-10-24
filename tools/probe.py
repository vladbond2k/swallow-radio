"""Temporary diagnostics for Google's price calendar from CI. Not part of the tool."""
import itertools
import time

from fli.core.builders import build_date_search_segments
from fli.models import Airport, DateSearchFilters, MaxStops, PassengerInfo, SeatType
from fli.search import SearchDates


def run(home, dest, days, start="2027-02-01", end="2027-03-31"):
    segs, tt = build_date_search_segments(origin=Airport[home], destination=Airport[dest],
                                          start_date=start, trip_duration=days, is_round_trip=True)
    f = DateSearchFilters(trip_type=tt, passenger_info=PassengerInfo(adults=1), flight_segments=segs,
                          stops=MaxStops.TWO_OR_FEWER_STOPS, seat_type=SeatType.ECONOMY,
                          from_date=start, to_date=end, duration=days)
    t = time.time()
    try:
        res = SearchDates().search(f, currency="PLN", language="en") or []
    except Exception as e:
        res, err = [], f" ERROR {type(e).__name__}: {e}"[:200]
    else:
        err = ""
    prices = [r.price for r in res]
    print(f"{time.strftime('%H:%M:%S')} {home}->{dest} {days}d: {len(res)} dates, {time.time()-t:.1f}s, "
          f"min={min(prices, default=None)}{err}", flush=True)
    return len(res)


homes = ["WRO", "KTW", "POZ", "KRK", "PRG", "WAW", "BER", "VIE"]
dests = ["HND", "NRT", "KIX", "NGO", "FUK", "CTS", "OKA"]
pairs = list(itertools.product(homes, dests))
empty_streak, n = 0, 0
for (h, d), days in zip(itertools.cycle(pairs), itertools.cycle(range(14, 22))):
    n += 1
    if n > 120:
        break
    got = run(h, d, days)
    empty_streak = empty_streak + 1 if got == 0 else 0
    if empty_streak >= 3:
        for wait in (30, 90, 180):
            print(f"--- 3 empty in a row after {n} requests; sleeping {wait}s", flush=True)
            time.sleep(wait)
            if run(h, d, days):
                empty_streak = 0
                break
        else:
            print("--- not recovering, stop", flush=True)
            break
    time.sleep(1.5)
