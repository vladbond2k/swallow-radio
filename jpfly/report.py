"""Console table, CSV and a standalone HTML report."""

import csv
import html
from pathlib import Path

from .combine import Trip
from .config import Config


def _route(t: Trip) -> str:
    return f"{t.out.src}→{t.out.dst} … {t.ret.src}→{t.ret.dst}"


def _kind(t: Trip) -> str:
    if t.single_ticket is not None and t.single_ticket + t.extras <= t.separate_total:
        return "one ticket"
    hubs = [h for h in (t.out.hub, t.ret.hub) if h]
    return "self-transfer " + "+".join(hubs) if hubs else "2 one-ways"


def console(trips: list[Trip], cfg: Config, n: int = 15):
    print(f"\nTop {min(n, len(trips))} of {len(trips)} trips ({cfg.currency}, incl. ground extras):\n")
    for i, t in enumerate(trips[:n], 1):
        print(f"{i:>2}. {t.total:>7.0f}  {t.out.day:%a %d.%m} → {t.ret.day:%a %d.%m} ({t.days}d)  "
              f"{_route(t)}  [{_kind(t)}]")
        print(f"      out: {t.out.describe()}")
        print(f"      ret: {t.ret.describe()}")


def write_csv(trips: list[Trip], path: Path):
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["total", "kind", "out_day", "ret_day", "days", "home_out", "japan_in", "japan_out",
                    "home_back", "separate_total", "single_ticket", "extras", "outbound", "return",
                    "out_links", "ret_links", "single_ticket_link"])
        for t in trips:
            w.writerow([round(t.total), _kind(t), t.out.day, t.ret.day, t.days, t.out.src, t.out.dst,
                        t.ret.src, t.ret.dst, round(t.separate_total), t.single_ticket or "", t.extras,
                        t.out.describe(), t.ret.describe(),
                        " ".join(x.url for x in t.out.tickets), " ".join(x.url for x in t.ret.tickets),
                        t.single_url])


CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1f;--mut:#6b6b70;--line:#e4e1da;--acc:#c2410c;--cell:194,65,12}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececee;--mut:#9a9aa2;--line:#2c2c31;--acc:#fb923c;--cell:251,146,60}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:0;padding:24px 16px;max-width:1200px;margin:auto}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}p.mut,.mut{color:var(--mut)}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%}
td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top;white-space:nowrap}
th{font-weight:600;color:var(--mut);font-size:12px}td.legs{white-space:normal;font-size:12px;min-width:340px}
.price{font-weight:700;font-variant-numeric:tabular-nums}a{color:var(--acc)}
.cal td,.cal th{text-align:center;padding:4px 6px;font-variant-numeric:tabular-nums}
.tag{font-size:11px;border:1px solid var(--line);border-radius:4px;padding:1px 5px;color:var(--mut)}
"""


def _links(tickets, label):
    return " ".join(f'<a href="{html.escape(t.url)}" target="_blank">{label}{i + 1 if len(tickets) > 1 else ""}</a>'
                    for i, t in enumerate(tickets))


def write_html(trips: list[Trip], cfg: Config, path: Path, top: int, failed: int):
    e = html.escape
    rows = []
    for i, t in enumerate(trips[:top], 1):
        single = (f'<br><a href="{e(t.single_url)}" target="_blank">one ticket {t.single_ticket:g}</a>'
                  if t.single_ticket else "")
        rows.append(
            f"<tr><td>{i}</td><td class=price>{t.total:.0f}</td>"
            f"<td>{t.out.day:%a %d %b}<br>{t.ret.day:%a %d %b}</td><td>{t.days}d</td>"
            f"<td>{e(_route(t))}<br><span class=tag>{e(_kind(t))}</span></td>"
            f"<td class=legs>{e(t.out.describe())}<br>{e(t.ret.describe())}</td>"
            f"<td>{_links(t.out.tickets, 'out')} {_links(t.ret.tickets, 'back')}{single}</td></tr>")

    # price calendar: departure day x trip length -> cheapest total
    cal: dict = {}
    for t in trips:
        k = (t.out.day, t.days)
        cal[k] = min(cal.get(k, t.total), t.total)
    days_range = range(cfg.min_days, cfg.max_days + 1)
    cal_html = ""
    if cal:
        lo, hi = min(cal.values()), max(cal.values())
        head = "".join(f"<th>{n}</th>" for n in days_range)
        body = []
        for d in cfg.depart_dates():
            cells = []
            for n in days_range:
                v = cal.get((d, n))
                if v is None:
                    cells.append("<td class=mut>–</td>")
                else:
                    a = 0.85 - 0.75 * ((v - lo) / (hi - lo) if hi > lo else 0)
                    cells.append(f'<td style="background:rgba(var(--cell),{a:.2f})">{v:.0f}</td>')
            body.append(f"<tr><th>{d:%a %d %b}</th>{''.join(cells)}</tr>")
        cal_html = (f"<h2>Cheapest total by departure day × trip length (days)</h2><div class=wrap>"
                    f"<table class=cal><tr><th></th>{head}</tr>{''.join(body)}</table></div>")

    warn = (f"<p class=mut>⚠ {failed} searches failed (blocked or errored) — rerun later to fill gaps.</p>"
            if failed else "")
    homes = ", ".join(o.code for o in cfg.origins)
    path.write_text(f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Japan Flight Deals</title>
<style>{CSS}</style></head><body>
<h1>Cheapest trips to Japan</h1>
<p class=mut>{homes} → {", ".join(cfg.japan)} · leave {cfg.depart_from:%d %b}–{cfg.depart_to:%d %b %Y} ·
{cfg.min_days}–{cfg.max_days} days · {cfg.currency}, {cfg.adults} adult(s), incl. ground extras ·
hubs: {", ".join(cfg.hubs) or "off"}</p>{warn}
<p class=mut>Prices are Google Flights snapshots; always re-check via the links. Self-transfer = separate tickets:
no protection if the first flight is late, and check transit visa rules at the hub.</p>
{cal_html}
<h2>Top {min(top, len(trips))} trips</h2><div class=wrap><table>
<tr><th>#</th><th>Total</th><th>Dates</th><th>Len</th><th>Route</th><th>Flights</th><th>Book</th></tr>
{''.join(rows)}</table></div></body></html>""")
