"""Aviasales (Travelpayouts Data API): round-trip prices other users found in the last days.

Cached data, so it is fast and covers low-cost carriers, but a price can be a few days old.
Docs: https://support.travelpayouts.com/hc/en-us/articles/203956163
"""

import json
import random
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta

from .config import Config
from .trips import Trip

API = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"

# Aviasales searches by city; we filter back to the airports from the config.
CITY = {"HND": "TYO", "NRT": "TYO", "KIX": "OSA", "ITM": "OSA", "UKB": "OSA", "NGO": "NGO",
        "FUK": "FUK", "CTS": "SPK", "OKA": "OKA", "SDJ": "SDJ", "HIJ": "HIJ", "KOJ": "KOJ"}


def _months(a: date, b: date) -> list[str]:
    out, d = [], a.replace(day=1)
    while d <= b:
        out.append(d.strftime("%Y-%m"))
        d = (d + timedelta(days=32)).replace(day=1)
    return out


def _fetch(params: dict) -> list[dict]:
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params),
                                 headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if not body.get("success", True):
        raise RuntimeError(body.get("error"))
    return body.get("data") or []


def _fetch_demo(params: dict) -> list[dict]:
    rnd = random.Random(str(params))
    y, m = map(int, params["departure_at"].split("-"))
    ry, rm = map(int, params["return_at"].split("-"))
    airports = [a for a, c in CITY.items() if c == params["destination"]]
    out = []
    for _ in range(rnd.randint(5, 30)):
        dep = date(y, m, rnd.randint(1, 28))
        ret = date(ry, rm, rnd.randint(1, 28))
        out.append({
            "origin_airport": params["origin"], "destination_airport": rnd.choice(airports),
            "price": rnd.randint(480, 1100), "airline": rnd.choice(["TK", "QR", "CA", "LO", "AY", "MU"]),
            "flight_number": str(rnd.randint(10, 999)),
            "departure_at": f"{dep}T{rnd.randint(6, 22):02d}:30:00+01:00",
            "return_at": f"{ret}T{rnd.randint(6, 22):02d}:10:00+09:00",
            "transfers": rnd.randint(0, 2), "return_transfers": rnd.randint(0, 2),
            "duration_to": rnd.randint(700, 1500), "duration_back": rnd.randint(700, 1500),
            "link": f"/search/{params['origin']}{dep:%d%m}{params['destination']}{ret:%d%m}1",
        })
    return out


def _hm(minutes) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}" if minutes else "?"


def trips(cfg: Config, demo: bool = False) -> list[Trip]:
    if not cfg.aviasales_token and not demo:
        print("Aviasales: no token, skipped (see [aviasales] in config)", file=sys.stderr)
        return []
    fetch = _fetch_demo if demo else _fetch
    cities = sorted({CITY.get(a, a) for a in cfg.japan})
    dep_months = _months(cfg.depart_from, cfg.depart_to)
    R = cfg.return_dates()
    ret_months = _months(R[0], R[-1])
    calls = [(h, c, dm, rm) for h in cfg.origins for c in cities for dm in dep_months for rm in ret_months]
    print(f"Aviasales: {len(calls)} requests...", file=sys.stderr)

    out, seen = [], set()
    for home, city, dm, rm in calls:
        params = {"origin": home, "destination": city, "departure_at": dm, "return_at": rm,
                  "one_way": "false", "direct": "false", "unique": "false", "sorting": "price",
                  "currency": cfg.currency.lower(), "limit": 1000, "page": 1, "token": cfg.aviasales_token}
        try:
            rows = fetch(params)
        except Exception as e:
            print(f"  ! aviasales {home}->{city} {dm}/{rm}: {type(e).__name__}: {e}"[:200], file=sys.stderr)
            continue
        for r in rows:
            try:
                dep, ret = date.fromisoformat(r["departure_at"][:10]), date.fromisoformat(r["return_at"][:10])
            except (KeyError, TypeError, ValueError):
                continue
            jp = r.get("destination_airport") or city
            if CITY.get(jp) == city and jp not in cfg.japan:
                continue
            if not (cfg.depart_from <= dep <= cfg.depart_to and cfg.min_days <= (ret - dep).days <= cfg.max_days):
                continue
            if (r.get("transfers") or 0) > cfg.max_stops or (r.get("return_transfers") or 0) > cfg.max_stops:
                continue
            key = (home, jp, dep, ret, r.get("airline"), r.get("price"))
            if key in seen:
                continue
            seen.add(key)
            link = r.get("link") or ""
            fl = f"{r.get('airline', '')}{r.get('flight_number', '')}"
            out.append(Trip(
                source="Aviasales", kind="round-trip ticket (cached price)", price=r["price"],
                extras=2 * cfg.origins[home], out_day=dep, ret_day=ret,
                home_out=home, jp_in=jp, jp_out=jp, home_back=home,
                stops_out=r.get("transfers"), stops_back=r.get("return_transfers"),
                airlines=r.get("airline", ""),
                out_desc=f"{home}→{jp} {r['departure_at'][5:16].replace('T', ' ')} {fl}, "
                         f"{r.get('transfers', '?')} stops, {_hm(r.get('duration_to'))}",
                ret_desc=f"{jp}→{home} {r['return_at'][5:16].replace('T', ' ')}, "
                         f"{r.get('return_transfers', '?')} stops, {_hm(r.get('duration_back'))}",
                links=[("aviasales", "https://www.aviasales.com" + link if link.startswith("/")
                        else link or "https://www.aviasales.com")],
            ))
    print(f"Aviasales: {len(out)} matching trips", file=sys.stderr)
    return out
