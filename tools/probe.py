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




def ow(home, dest, start="2027-02-01", end="2027-03-31"):
    segs, tt = build_date_search_segments(origin=Airport[home], destination=Airport[dest], start_date=start)
    f = DateSearchFilters(trip_type=tt, passenger_info=PassengerInfo(adults=1), flight_segments=segs,
                          stops=MaxStops.TWO_OR_FEWER_STOPS, seat_type=SeatType.ECONOMY, from_date=start, to_date=end)
    t = time.time()
    try:
        res = SearchDates().search(f, currency="PLN", language="en")
        n = "None" if res is None else len(res)
        print(f"{time.strftime('%H:%M:%S')} ONE-WAY {home}->{dest}: {n} dates, {time.time()-t:.1f}s, "
              f"min={min((r.price for r in res or []), default=None)}", flush=True)
    except Exception as e:
        print(f"ONE-WAY {home}->{dest}: ERROR {type(e).__name__}: {e}"[:300], flush=True)


for h, d in [("WRO", "KIX"), ("KIX", "WRO"), ("KTW", "HND"), ("HND", "KTW"), ("POZ", "NRT"), ("NRT", "POZ"),
             ("WAW", "NGO"), ("NGO", "WAW")]:
    ow(h, d)
    time.sleep(2)
