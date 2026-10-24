"""Temporary diagnostics for Google's price calendar from CI. Not part of the tool."""
import time
from datetime import date

from fli.core.builders import build_date_search_segments
from fli.models import Airport, DateSearchFilters, MaxStops, PassengerInfo, SeatType
from fli.search import SearchDates
from fli.search import dates as dmod

orig_parse = dmod.parse_first_wrb_payload


def spy(text):
    r = orig_parse(text)
    if r is None:
        print(f"    payload=None, response len={len(text)}, head={text[:300]!r}")
    return r


dmod.parse_first_wrb_payload = spy


def run(label, home, dests, start, end, days, stops=MaxStops.TWO_OR_FEWER_STOPS):
    segs, tt = build_date_search_segments(origin=[Airport[h] for h in home], destination=[Airport[d] for d in dests],
                                          start_date=start, trip_duration=days, is_round_trip=True)
    f = DateSearchFilters(trip_type=tt, passenger_info=PassengerInfo(adults=1), flight_segments=segs, stops=stops,
                          seat_type=SeatType.ECONOMY, from_date=start, to_date=end, duration=days)
    t = time.time()
    try:
        res = SearchDates().search(f, currency="PLN", language="en") or []
        ds = sorted(r.date[0].date() for r in res)
        print(f"{label}: {len(res)} dates in {time.time()-t:.1f}s; "
              f"{ds[0] if ds else '-'}..{ds[-1] if ds else '-'}; min={min((r.price for r in res), default=None)}", flush=True)
    except Exception as e:
        print(f"{label}: ERROR after {time.time()-t:.1f}s {type(e).__name__}: {e}"[:400], flush=True)


J7 = ["HND", "NRT", "KIX", "NGO", "FUK", "CTS", "OKA"]
run("A WRO->7JP 14d Feb-Mar (1 chunk)", ["WRO"], J7, "2027-02-01", "2027-03-31", 14)
time.sleep(5)
run("B WRO->HND 14d Feb-Mar", ["WRO"], ["HND"], "2027-02-01", "2027-03-31", 14)
time.sleep(5)
run("C WRO->HND,NRT,KIX 14d", ["WRO"], ["HND", "NRT", "KIX"], "2027-02-01", "2027-03-31", 14)
time.sleep(5)
run("D WRO->7JP any stops", ["WRO"], J7, "2027-02-01", "2027-03-31", 14, MaxStops.ANY)
time.sleep(5)
run("E 5 homes->7JP 14d", ["WRO", "WAW", "BER", "PRG", "VIE"], J7, "2027-02-01", "2027-03-31", 14)
time.sleep(5)
run("F WAW->7JP 14d", ["WAW"], J7, "2027-02-01", "2027-03-31", 14)
time.sleep(5)
run("G WRO->7JP 14d Jan15-Apr30 (2 chunks)", ["WRO"], J7, "2027-01-15", "2027-04-30", 14)
print("burst test: 10 quick requests", flush=True)
for i in range(10):
    run(f"  burst {i}", ["BER"], J7, "2027-02-01", "2027-03-31", 14 + i % 8)
