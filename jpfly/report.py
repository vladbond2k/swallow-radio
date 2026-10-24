"""CSV + a single self-contained HTML page with a sortable, filterable table."""

import csv
import json
from pathlib import Path

from .config import Config
from .trips import Trip


def _row(t: Trip) -> dict:
    return {
        "source": t.source, "kind": t.kind, "total": round(t.total), "price": round(t.price),
        "extras": round(t.extras), "out": t.out_day.isoformat(), "ret": t.ret_day.isoformat(), "days": t.days,
        "home_out": t.home_out, "jp_in": t.jp_in, "jp_out": t.jp_out, "home_back": t.home_back,
        "stops": max(s for s in (t.stops_out, t.stops_back, 0) if s is not None),
        "airlines": t.airlines, "out_desc": t.out_desc, "ret_desc": t.ret_desc, "links": t.links,
    }


def console(trips: list[Trip], cfg: Config, n: int = 10):
    print(f"\nTop {min(n, len(trips))} of {len(trips)} ({cfg.currency}, incl. ground costs):")
    for i, t in enumerate(trips[:n], 1):
        print(f"{i:>2}. {t.total:>6.0f}  {t.out_day:%a %d.%m}→{t.ret_day:%a %d.%m} ({t.days}d)  "
              f"{t.home_out}→{t.jp_in} … {t.jp_out}→{t.home_back}  {t.source}: {t.kind}")


def write_csv(trips: list[Trip], path: Path):
    rows = [_row(t) for t in trips]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            r["links"] = " ".join(u for _, u in r["links"])
            w.writerow(r)


def write_html(trips: list[Trip], cfg: Config, path: Path, warnings: list[str]):
    data = json.dumps([_row(t) for t in trips], ensure_ascii=False).replace("</", "<\\/")
    homes = ", ".join(cfg.origins)
    sub = (f"{homes} → {', '.join(cfg.japan)} · leave {cfg.depart_from:%d %b}–{cfg.depart_to:%d %b %Y} · "
           f"{cfg.min_days}–{cfg.max_days} days · {cfg.currency}, {cfg.adults} adult(s), totals include ground costs")
    warn = "".join(f"<p class=warn>⚠ {w}</p>" for w in warnings)
    path.write_text(PAGE.replace("__SUB__", sub).replace("__WARN__", warn)
                    .replace("__CUR__", cfg.currency).replace("__DATA__", data))


PAGE = r"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Japan Flights</title>
<style>
:root{--bg:#fbfaf7;--fg:#1d1d1f;--mut:#6b6b70;--line:#e4e1da;--acc:#c2410c;--hi:#fff1e8;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececee;--mut:#9a9aa2;--line:#2c2c31;--acc:#fb923c;--hi:#2a1d14;--card:#1c1c1f}}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:0 auto;padding:20px 16px;max-width:1280px}
h1{font-size:22px;margin:0 0 4px}.mut{color:var(--mut)}.warn{color:var(--acc);margin:4px 0}
.filters{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:end;background:var(--card);border:1px solid var(--line);
 border-radius:8px;padding:12px;margin:14px 0}
.filters label,.grp{display:flex;flex-direction:column;font-size:12px;color:var(--mut);gap:3px}
.filters input,.filters select{font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:5px;padding:4px 6px}
.filters input[type=number]{width:80px}.chk{flex-direction:row!important;align-items:center;gap:5px!important;font-size:14px!important;color:var(--fg)!important}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%}
th{font-size:12px;color:var(--mut);text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);cursor:pointer;user-select:none;white-space:nowrap}
th.sorted{color:var(--fg)}
td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top;white-space:nowrap}
td.f{white-space:normal;font-size:12px;min-width:320px}
tr:hover td{background:var(--hi)}
.p{font-weight:700;font-variant-numeric:tabular-nums;font-size:15px}
.tag{font-size:11px;border:1px solid var(--line);border-radius:4px;padding:1px 5px;color:var(--mut)}
a{color:var(--acc)}
</style></head><body>
<h1>Cheapest trips to Japan</h1>
<div class=mut>__SUB__</div>__WARN__
<p class=mut>Google = live prices (two one-way tickets, or one ticket if that was cheaper). Aviasales = round-trip prices
other people found recently: may be outdated, re-check on the site. Always confirm the final price via the link.</p>
<div class=filters>
 <div class=grp>Source<span><label class=chk><input type=checkbox id=sG checked>Google</label>
  <label class=chk><input type=checkbox id=sA checked>Aviasales</label></span></div>
 <label>Leave from<input type=date id=d1></label><label>Leave until<input type=date id=d2></label>
 <label>Days min<input type=number id=n1></label><label>Days max<input type=number id=n2></label>
 <label>Max stops<select id=st><option value=9>any</option><option value=0>direct</option><option value=1>≤1</option><option value=2>≤2</option></select></label>
 <label>Home airport<select id=home><option value="">any</option></select></label>
 <label>Japan airport<select id=jp><option value="">any</option></select></label>
 <label>Same airport in/out<select id=same><option value="">any</option><option value=1>yes</option></select></label>
 <label>Max price (__CUR__)<input type=number id=pmax></label>
 <span class=mut id=cnt></span>
</div>
<div class=wrap><table><thead><tr>
 <th data-k=total>Total</th><th data-k=out>Dates</th><th data-k=days>Days</th><th data-k=jp_in>Route</th>
 <th data-k=stops>Stops</th><th data-k=source>Source</th><th>Flights</th><th>Book</th>
</tr></thead><tbody id=tb></tbody></table></div>
<script>
const D=__DATA__, $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt=d=>new Date(d+"T00:00").toLocaleDateString("en-GB",{weekday:"short",day:"numeric",month:"short"});
for(const [id,keys] of [["home",["home_out","home_back"]],["jp",["jp_in","jp_out"]]]){
  [...new Set(D.flatMap(r=>keys.map(k=>r[k])))].sort().forEach(v=>$(id).add(new Option(v,v)));
}
let sortK="total",asc=true;
function render(){
  const g=$("sG").checked,a=$("sA").checked,d1=$("d1").value,d2=$("d2").value,n1=+$("n1").value||0,n2=+$("n2").value||999,
    st=+$("st").value,h=$("home").value,j=$("jp").value,same=$("same").value,pm=+$("pmax").value||1e9;
  let R=D.filter(r=>(r.source=="Google"?g:a)&&(!d1||r.out>=d1)&&(!d2||r.out<=d2)&&r.days>=n1&&r.days<=n2&&r.stops<=st
    &&(!h||r.home_out==h||r.home_back==h)&&(!j||r.jp_in==j||r.jp_out==j)&&(!same||r.jp_in==r.jp_out)&&r.total<=pm);
  R.sort((x,y)=>(x[sortK]>y[sortK]?1:x[sortK]<y[sortK]?-1:x.total-y.total)*(asc?1:-1));
  $("cnt").textContent=`${R.length} of ${D.length} trips`+(R.length>300?" (showing 300)":"");
  $("tb").innerHTML=R.slice(0,300).map(r=>`<tr>
   <td class=p>${r.total}${r.extras?`<div class=mut style="font-weight:400;font-size:11px">${r.price}+${r.extras}</div>`:""}</td>
   <td>${fmt(r.out)}<br>${fmt(r.ret)}</td><td>${r.days}</td>
   <td>${esc(r.home_out)}→${esc(r.jp_in)}<br>${esc(r.jp_out)}→${esc(r.home_back)}</td><td>${r.stops}</td>
   <td>${esc(r.source)}<br><span class=tag>${esc(r.kind)}</span></td>
   <td class=f>${esc(r.out_desc)}<br>${esc(r.ret_desc)}</td>
   <td>${r.links.map(([l,u])=>`<a href="${esc(u)}" target=_blank rel=noopener>${esc(l)}</a>`).join("<br>")}</td></tr>`).join("");
  document.querySelectorAll("th[data-k]").forEach(th=>th.classList.toggle("sorted",th.dataset.k==sortK));
}
document.querySelectorAll("th[data-k]").forEach(th=>th.onclick=()=>{asc=sortK==th.dataset.k?!asc:true;sortK=th.dataset.k;render()});
document.querySelectorAll(".filters input,.filters select").forEach(e=>e.oninput=render);
render();
</script></body></html>"""
