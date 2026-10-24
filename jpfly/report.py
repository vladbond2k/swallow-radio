"""Single self-contained HTML page: price calendar + cheapest options, plus a CSV."""

import csv
import json
from datetime import datetime
from pathlib import Path

from .config import Config
from .search import Option


def write_csv(opts: list[Option], path: Path):
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["price", "home", "japan", "out", "back", "days"])
        for o in opts:
            w.writerow([round(o.price), o.home, o.dest, o.out, o.back, o.days])


def console(opts: list[Option], cfg: Config, n: int = 10):
    print(f"\nTop {min(n, len(opts))} of {len(opts)} ({cfg.currency}):")
    for o in opts[:n]:
        print(f"  {o.price:>7.0f}  {o.out:%a %d.%m} → {o.back:%a %d.%m} ({o.days}d) {o.home}⇄{o.dest}")


def write_html(opts: list[Option], cands: list[Option], cfg: Config, path: Path, warnings: list[str], demo: bool):
    data = [[o.home, o.dest, o.out.isoformat(), o.days, round(o.price), o.flight] for o in opts]
    cal = [[o.home, o.dest, o.out.isoformat(), o.days, round(o.price)] for o in cands]
    meta = {
        "cur": cfg.currency, "homes": cfg.home, "japan": cfg.japan,
        "min": cfg.min_days, "max": cfg.max_days, "layover": cfg.max_layover_hours, "travel": cfg.max_travel_hours,
        "from": cfg.depart_from.isoformat(), "to": cfg.depart_to.isoformat(),
        "updated": datetime.now().strftime("%d.%m.%Y %H:%M"), "warnings": warnings, "demo": demo,
    }
    meta["verified"] = bool(cfg.max_layover_hours or cfg.max_travel_hours)
    meta_json = json.dumps(meta, ensure_ascii=False).replace("</", "<\\/")
    path.write_text(PAGE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
                    .replace("__CAL__", json.dumps(cal)).replace("__META__", meta_json))


PAGE = r"""<!doctype html><html lang=ru><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Билеты в Японию</title>
<style>
:root{--bg:#fbfaf7;--fg:#1d1d1f;--mut:#6b6b70;--line:#e4e1da;--acc:#c2410c;--card:#fff;--c:194,65,12}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececee;--mut:#9a9aa2;--line:#2c2c31;--acc:#fb923c;--card:#1c1c1f;--c:251,146,60}}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif;margin:0 auto;padding:20px 16px 60px;max-width:980px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:26px 0 10px}.mut{color:var(--mut)}.warn{color:var(--acc);margin:6px 0}
.ctl{display:flex;flex-wrap:wrap;gap:10px 14px;margin:16px 0}
.ctl label{display:flex;flex-direction:column;font-size:12px;color:var(--mut);gap:3px}
select{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:8px;padding:7px 10px}
.list{display:grid;gap:8px}
.opt{display:flex;align-items:center;gap:14px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.opt .p{font-weight:700;font-size:20px;font-variant-numeric:tabular-nums;min-width:110px}
.opt .d{flex:1}.opt .s{font-size:13px;color:var(--mut)}
a{color:var(--acc)}.opt a{white-space:nowrap;font-weight:600}.lk{display:flex;flex-direction:column;gap:4px;align-items:flex-end}
.months{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px}
.month h3{font-size:14px;margin:0 0 6px;text-transform:capitalize}
.grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}
.grid .h{font-size:11px;color:var(--mut);text-align:center}
.day{border-radius:6px;padding:4px 2px;text-align:center;font-size:11px;min-height:42px;border:1px solid transparent;cursor:pointer;color:var(--fg)}
.day b{display:block;font-size:13px;font-weight:600}.day.e{cursor:default;color:var(--mut);opacity:.5}
.day.sel{border-color:var(--fg)}.day:not(.e):hover{border-color:var(--acc)}
@media (max-width:520px){.opt{flex-wrap:wrap;gap:4px 12px}.opt .p{min-width:0}.opt .d{flex-basis:100%;order:3}
 .lk{flex-direction:row;gap:14px;order:4;flex-basis:100%;margin-top:4px}}
</style></head><body>
<h1>Дешёвые поездки в Японию</h1>
<div class=mut id=sub></div><div id=warn></div>
<div class=ctl>
 <label>Длина поездки<select id=len></select></label>
 <label>Откуда<select id=home></select></label>
 <label>Куда<select id=jp></select></label>
 <label id=stopsl>Пересадок туда<select id=stops><option value=9>любое</option><option value=1>не больше 1</option><option value=0>только прямые</option></select></label>
</div>
<h2 id=toph>Самые дешёвые варианты</h2>
<div class=list id=top></div>
<h2>Календарь: цена по дню вылета</h2>
<p class=mut style="margin-top:-6px">Самая низкая цена туда-обратно при вылете в этот день. Серым с «~» — цена из календаря Google
без учёта лимита пересадок, ещё не проверенная. Нажми на день — покажу варианты.</p>
<div class=months id=cal></div>
<h2 id=dayh style="display:none"></h2><div class=list id=day></div>
<p class=mut style="margin-top:28px">Цены — минимальные из календаря Google Flights, туда-обратно, 1 взрослый, эконом.
Точный рейс и цену смотри по ссылке перед покупкой.</p>
<script>
const D0=__DATA__.map(([home,dest,out,days,price,f])=>({home,dest,out,days,price,f,total:price})), M=__META__;
// pick, per verified option, the cheapest outbound within the chosen number of stops
const pick=(o,maxStops)=>{if(!M.verified)return o;let b=null;
  for(const [n,d] of Object.entries(o.f||{}))if(+n<=maxStops&&(!b||d.price<b.price))b=d;
  return b?{...o,price:b.price,total:b.price,fl:b}:null};
const C=__CAL__.map(([home,dest,out,days,price])=>({home,dest,out,days,price}));
const $=id=>document.getElementById(id);
const money=v=>new Intl.NumberFormat("ru-RU").format(Math.round(v))+(M.cur=="PLN"?" zł":" "+M.cur);
const dt=s=>new Date(s+"T12:00");
const pad=n=>String(n).padStart(2,"0");
const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
const addDays=(s,n)=>{const d=dt(s);d.setDate(d.getDate()+n);return iso(d)};
const fd=s=>dt(s).toLocaleDateString("ru-RU",{weekday:"short",day:"numeric",month:"short"});
const NAMES={HND:"Токио Ханэда",NRT:"Токио Нарита",KIX:"Осака",ITM:"Осака Итами",NGO:"Нагоя",FUK:"Фукуока",CTS:"Саппоро",OKA:"Окинава",WRO:"Вроцлав",WAW:"Варшава",BER:"Берлин",PRG:"Прага",VIE:"Вена",KTW:"Катовице",POZ:"Познань",KRK:"Краков",GDN:"Гданьск",BUD:"Будапешт",MUC:"Мюнхен",FRA:"Франкфурт"};
const city=c=>NAMES[c]?`${NAMES[c]} (${c})`:c;
const gUrl=o=>"https://www.google.com/travel/flights?q="+encodeURIComponent(
  `Flights from ${o.home} to ${o.dest} on ${o.out} through ${addDays(o.out,o.days)}`)+"&curr="+M.cur+"&hl=ru";
// same dates on aggregators that also search small agencies and carriers Google doesn't show
const dm=s=>s.slice(8,10)+s.slice(5,7), ymd=s=>s.slice(2,4)+s.slice(5,7)+s.slice(8,10);
const aUrl=o=>`https://www.aviasales.com/search/${o.home}${dm(o.out)}${o.dest}${dm(addDays(o.out,o.days))}1`;
const sUrl=o=>`https://www.skyscanner.pl/transport/flights/${o.home.toLowerCase()}/${o.dest.toLowerCase()}/${ymd(o.out)}/${ymd(addDays(o.out,o.days))}/?adultsv2=1&currency=PLN`;
const dayWord=n=>n%10==1&&n%100!=11?"день":[2,3,4].includes(n%10)&&![12,13,14].includes(n%100)?"дня":"дней";

$("sub").textContent=`Вылет ${fd(M.from)} – ${fd(M.to)} · ${M.min}–${M.max} дней · ${M.homes.length} аэропортов вылета ⇄ ${M.japan.map(c=>NAMES[c]||c).join(", ")} ${M.layover?` · пересадки до ${M.layover} ч`:""}${M.travel?` · в пути до ${M.travel} ч`:""} · обновлено ${M.updated}`;
$("warn").innerHTML=(M.demo?["ДЕМО: цены выдуманные, только чтобы показать вид"]:[]).concat(M.warnings)
  .map(w=>`<p class=warn>⚠ ${w.replace(/</g,"&lt;")}</p>`).join("")+(D0.length?"":"<p class=warn>Ничего не найдено.</p>");
$("len").add(new Option("любая",""));for(let n=M.min;n<=M.max;n++)$("len").add(new Option(`${n} ${dayWord(n)}`,n));
$("home").add(new Option("откуда угодно",""));M.homes.forEach(h=>$("home").add(new Option(city(h),h)));
$("jp").add(new Option("любой аэропорт Японии",""));M.japan.forEach(h=>$("jp").add(new Option(city(h),h)));

let selDay=null;
const hm=s=>s?s.slice(11,16):"";
const flight=f=>!f||!f.route?"":`<div class=s>туда: ${(f.airlines||[]).join(", ")} · ${f.route.join("–")} · ${hm(f.dep)}→${hm(f.arr)}`+
  ` · ${f.hours} ч в пути${f.layovers&&f.layovers.length?` · пересадк${f.layovers.length>1?"и":"а"} ${f.layovers.join(" + ")} ч`:" · прямой"}</div>`;
const card=o=>`<div class=opt><div class=p>${money(o.total)}</div>
 <div class=d><b>${fd(o.out)} → ${fd(addDays(o.out,o.days))}</b> · ${o.days} ${dayWord(o.days)}
  <div class=s>${city(o.home)} ⇄ ${city(o.dest)}</div>${flight(o.fl)}</div>
 <div class=lk><a href="${gUrl(o)}" target=_blank rel=noopener>Google ↗</a><a href="${aUrl(o)}" target=_blank rel=noopener>Aviasales ↗</a><a href="${sUrl(o)}" target=_blank rel=noopener>Skyscanner ↗</a></div></div>`;

function render(){
  const L=$("len").value,H=$("home").value,J=$("jp").value,S=+$("stops").value;
  const D=D0.map(o=>pick(o,S)).filter(Boolean);
  const R=D.filter(o=>(!L||o.days==L)&&(!H||o.home==H)&&(!J||o.dest==J)).sort((a,b)=>a.total-b.total);
  // top list: best per (out day, length), so it's not the same dates repeated for every airport
  const seen=new Set(),top=[];for(const o of R){const k=o.out+o.days;if(!seen.has(k)){seen.add(k);top.push(o)}if(top.length==10)break}
  $("top").innerHTML=top.map(card).join("")||"<p class=mut>Нет вариантов под эти фильтры.</p>";
  const best={};R.forEach(o=>{if(!best[o.out]||o.total<best[o.out].total)best[o.out]=o});
  // days not verified yet: show the calendar price greyed out as a hint
  const hint={};C.filter(o=>(!L||o.days==L)&&(!H||o.home==H)&&(!J||o.dest==J))
    .forEach(o=>{if(!hint[o.out]||o.price<hint[o.out])hint[o.out]=o.price});
  const vals=Object.values(best).map(o=>o.total),lo=Math.min(...vals),hi=Math.max(...vals);
  let html="",d=dt(M.from);d.setDate(1);const end=dt(M.to);
  while(d<=end){
    const y=d.getFullYear(),m=d.getMonth(),first=(new Date(y,m,1).getDay()+6)%7,n=new Date(y,m+1,0).getDate();
    let g=["пн","вт","ср","чт","пт","сб","вс"].map(x=>`<div class=h>${x}</div>`).join("")+"<div></div>".repeat(first);
    for(let i=1;i<=n;i++){
      const k=iso(new Date(y,m,i)),o=best[k];
      if(!o){g+=hint[k]&&M.verified?`<div class="day e" title="цена без учёта лимита пересадок, ещё не проверена">${i}<b>~${(hint[k]/1000).toFixed(1)}k</b></div>`:`<div class="day e">${i}</div>`;continue}
      const a=hi>lo?0.85-0.75*(o.total-lo)/(hi-lo):0.6;
      g+=`<div class="day${selDay==k?" sel":""}" data-k=${k} style="background:rgba(var(--c),${a.toFixed(2)})">${i}<b>${(o.total/1000).toFixed(1)}k</b></div>`;
    }
    html+=`<div class=month><h3>${d.toLocaleDateString("ru-RU",{month:"long",year:"numeric"})}</h3><div class=grid>${g}</div></div>`;
    d=new Date(y,m+1,1);
  }
  $("cal").innerHTML=html;
  document.querySelectorAll(".day[data-k]").forEach(e=>e.onclick=()=>{selDay=e.dataset.k;render();$("dayh").scrollIntoView({behavior:"smooth"})});
  if(selDay){
    const X=R.filter(o=>o.out==selDay);
    $("dayh").style.display="";$("dayh").textContent=`Вылет ${fd(selDay)}: ${X.length} вариантов`;
    $("day").innerHTML=X.slice(0,40).map(card).join("");
  }
}
if(!M.verified)$("stopsl").style.display="none";
$("len").onchange=$("home").onchange=$("jp").onchange=$("stops").onchange=render;render();
</script></body></html>"""
