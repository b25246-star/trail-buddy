"""Route engine: GPX -> stage-by-stage roadmap + offline SVG map.
Pure standard library, so it works with no internet and no extra installs."""
import json
import math
import webbrowser
import xml.etree.ElementTree as ET
from html import escape

import config


# ---------------------------------------------------------------- GPX parsing
def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _read_point(el):
    ele = 0.0
    for child in el:
        if _local(child.tag) == "ele":
            ele = float(child.text)
    return {"lat": float(el.get("lat")), "lon": float(el.get("lon")), "ele": ele}


def load_gpx(path):
    raw = path.read_bytes()
    if not raw.strip():
        raise ValueError(f"{path.name} is empty. Paste your GPX data into it and save.")
    for enc in ("utf-8-sig", "utf-16"):
        try:
            text = raw.decode(enc).lstrip()
            break
        except UnicodeError:
            continue
    else:
        raise ValueError(f"{path.name}: could not read file encoding. Save it as UTF-8.")
    if not text.startswith("<"):
        raise ValueError(f"{path.name} does not look like XML/GPX (starts with {text[:20]!r}).")
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as e:
        raise ValueError(f"{path.name} is not valid GPX: {e}")
    points, waypoints, name = [], [], path.stem.replace("_", " ").title()
    for el in root.iter():
        tag = _local(el.tag)
        if tag in ("trkpt", "rtept"):
            points.append(_read_point(el))
        elif tag == "wpt":
            wp = _read_point(el)
            wp["name"], wp["desc"] = "Waypoint", ""
            for child in el:
                if _local(child.tag) == "name":
                    wp["name"] = (child.text or "").strip()
                elif _local(child.tag) == "desc":
                    wp["desc"] = (child.text or "").strip()
            waypoints.append(wp)
        elif tag == "name" and el.text and not points and not waypoints:
            name = el.text.strip()
    if len(points) < 2:
        raise ValueError(f"{path.name}: needs at least 2 track points")
    return name, points, waypoints


# --------------------------------------------------------------------- maths
def haversine_m(a, b):
    r = 6371000
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = p2 - p1
    dl = math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _smooth(values, window=3):
    half = window // 2
    out = []
    for i in range(len(values)):
        chunk = values[max(0, i - half): i + half + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def hours(dist_km, ascent_m):
    return dist_km / config.WALK_SPEED_KMH + ascent_m / config.ASCENT_M_PER_HOUR


def fmt_time(h):
    mins = int(round(h * 60))
    return f"{mins // 60}h {mins % 60:02d}m" if mins >= 60 else f"{mins} min"


# ------------------------------------------------------------------ analysis
def analyse(path):
    name, points, waypoints = load_gpx(path)
    return analyse_track(name, points, waypoints)


def analyse_track(name, points, waypoints):
    ele = _smooth([p["ele"] for p in points])
    cum = [0.0]
    for i in range(1, len(points)):
        cum.append(cum[-1] + haversine_m(points[i - 1], points[i]) / 1000)

    # snap each waypoint to its nearest track point
    marks = []
    for wp in waypoints:
        idx = min(range(len(points)), key=lambda i: haversine_m(wp, points[i]))
        marks.append({"idx": idx, "name": wp["name"], "desc": wp["desc"]})
    marks.sort(key=lambda m: m["idx"])
    seen, unique = set(), []
    for m in marks:
        if m["idx"] not in seen:
            seen.add(m["idx"])
            unique.append(m)
    marks = unique
    if not marks or marks[0]["idx"] != 0:
        marks.insert(0, {"idx": 0, "name": "Start", "desc": ""})
    if marks[-1]["idx"] != len(points) - 1:
        marks.append({"idx": len(points) - 1, "name": "End", "desc": ""})

    for m in marks:
        m["km"] = cum[m["idx"]]
        m["ele"] = ele[m["idx"]]

    stages = []
    for a, b in zip(marks, marks[1:]):
        seg = range(a["idx"], b["idx"] + 1)
        ascent = sum(max(0, ele[i + 1] - ele[i]) for i in seg if i + 1 <= b["idx"])
        descent = sum(max(0, ele[i] - ele[i + 1]) for i in seg if i + 1 <= b["idx"])
        dist = cum[b["idx"]] - cum[a["idx"]]
        stages.append({"from": a, "to": b, "dist": dist, "ascent": ascent,
                       "descent": descent, "time": hours(dist, ascent)})

    total_ascent = sum(s["ascent"] for s in stages)
    total_descent = sum(s["descent"] for s in stages)
    return {
        "name": name, "points": points, "ele": ele, "cum": cum, "marks": marks,
        "stages": stages, "total_km": cum[-1], "ascent": total_ascent,
        "descent": total_descent,
        "time_up": hours(cum[-1], total_ascent),
        "time_down": hours(cum[-1], 0) * 0.8 + total_descent / 1500,
        "max_ele": max(ele), "min_ele": min(ele),
        "warnings": [], "source": "GPX file",
    }


# ------------------------------------------------------------- text roadmap
def roadmap_text(info):
    lines = [
        f"ROADMAP: {info['name']}",
        f"Distance {info['total_km']:.1f} km one way | climb {info['ascent']:.0f} m | "
        f"high point {info['max_ele']:.0f} m",
        f"Estimated time: up {fmt_time(info['time_up'])}, "
        f"down about {fmt_time(info['time_down'])}",
        "",
    ]
    for w in info.get("warnings", []):
        lines.append(f"WARNING: {w}")
    if info.get("warnings"):
        lines.append("")
    for n, s in enumerate(info["stages"], 1):
        lines.append(
            f"Stage {n}: {s['from']['name']} -> {s['to']['name']}\n"
            f"   {s['dist']:.1f} km, +{s['ascent']:.0f} m, about {fmt_time(s['time'])} "
            f"(arrive at {s['to']['km']:.1f} km, {s['to']['ele']:.0f} m)"
        )
        if s["to"]["desc"]:
            lines.append(f"   Note: {s['to']['desc']}")
    lines.append("\nTimes are estimates from distance and climb. Add rest stops, "
                 "and start early so you are back before dark.")
    return "\n".join(lines)


# ------------------------------------------------------------------- SVG map
def _nice_scale(m_per_px, target_px=120):
    options = [50, 100, 200, 500, 1000, 2000, 5000]
    length = min(options, key=lambda o: abs(o / m_per_px - target_px))
    return length, length / m_per_px


def _map_svg(info, W=720, H=520, pad=50):
    pts = info["points"]
    lat0 = sum(p["lat"] for p in pts) / len(pts)
    kx = math.cos(math.radians(lat0))
    xs = [p["lon"] * kx for p in pts]
    ys = [p["lat"] for p in pts]
    minx, miny = min(xs), min(ys)
    sx = max(max(xs) - minx, 1e-9)
    sy = max(max(ys) - miny, 1e-9)
    scale = min((W - 2 * pad) / sx, (H - 2 * pad) / sy)
    ox, oy = (W - sx * scale) / 2, (H - sy * scale) / 2

    def xy(p):
        return (ox + (p["lon"] * kx - minx) * scale,
                H - (oy + (p["lat"] - miny) * scale))

    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(xy, pts))
    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
           f'role="img" aria-label="Route map">',
           f'<rect width="{W}" height="{H}" fill="#f4f1e8" rx="10"/>']
    for g in range(1, 6):  # faint grid
        out.append(f'<line x1="{g * W / 6:.0f}" y1="0" x2="{g * W / 6:.0f}" y2="{H}" stroke="#e2ddcc"/>')
        out.append(f'<line x1="0" y1="{g * H / 6:.0f}" x2="{W}" y2="{g * H / 6:.0f}" stroke="#e2ddcc"/>')
    out.append(f'<polyline points="{path}" fill="none" stroke="#fff" stroke-width="9" '
               f'stroke-linecap="round" stroke-linejoin="round"/>')
    out.append(f'<polyline points="{path}" fill="none" stroke="#d6451f" stroke-width="4" '
               f'stroke-linecap="round" stroke-linejoin="round"/>')

    last = len(info["marks"]) - 1
    for n, m in enumerate(info["marks"]):
        x, y = xy(pts[m["idx"]])
        colour = "#2e8b57" if n == 0 else "#b3261e" if n == last else "#1f4e79"
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="13" fill="{colour}" stroke="#fff" stroke-width="3"/>')
        out.append(f'<text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="middle" font-size="14" '
                   f'font-weight="700" fill="#fff">{n + 1}</text>')
        out.append(f'<text x="{x + 18:.1f}" y="{y + 5:.1f}" font-size="13" fill="#222" '
                   f'stroke="#f4f1e8" stroke-width="4" paint-order="stroke">{escape(m["name"])}</text>')

    # north arrow + scale bar
    out.append(f'<g transform="translate({W - 40},40)"><polygon points="0,-22 8,8 0,2 -8,8" fill="#333"/>'
               f'<text y="26" text-anchor="middle" font-size="13" font-weight="700">N</text></g>')
    m_per_px = 111320 / scale
    length_m, px = _nice_scale(m_per_px)
    label = f"{length_m} m" if length_m < 1000 else f"{length_m // 1000} km"
    out.append(f'<g transform="translate(24,{H - 28})"><line x2="{px:.0f}" stroke="#333" stroke-width="3"/>'
               f'<line y1="-6" y2="6" stroke="#333" stroke-width="3"/>'
               f'<line x1="{px:.0f}" x2="{px:.0f}" y1="-6" y2="6" stroke="#333" stroke-width="3"/>'
               f'<text x="{px / 2:.0f}" y="-10" text-anchor="middle" font-size="12">{label}</text></g>')
    out.append("</svg>")
    return "\n".join(out)


def _profile_svg(info, W=720, H=220, pad=40):
    cum, ele = info["cum"], info["ele"]
    lo, hi = min(ele) - 20, max(ele) + 20
    total = max(cum[-1], 1e-9)

    def xy(d, e):
        return (pad + d / total * (W - 2 * pad),
                H - pad - (e - lo) / (hi - lo) * (H - 2 * pad))

    line = [xy(d, e) for d, e in zip(cum, ele)]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in line)
    area = f"{pad},{H - pad} {pts} {line[-1][0]:.1f},{H - pad}"
    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" '
           f'aria-label="Elevation profile">',
           f'<rect width="{W}" height="{H}" fill="#f4f1e8" rx="10"/>',
           f'<polygon points="{area}" fill="#d6451f" fill-opacity="0.18"/>',
           f'<polyline points="{pts}" fill="none" stroke="#d6451f" stroke-width="3"/>',
           f'<text x="{pad}" y="20" font-size="13" font-weight="700">Elevation (m) vs distance (km)</text>',
           f'<text x="8" y="{xy(0, hi)[1] + 4:.0f}" font-size="11">{hi:.0f}</text>',
           f'<text x="8" y="{xy(0, lo)[1] + 4:.0f}" font-size="11">{lo:.0f}</text>']
    for n, m in enumerate(info["marks"]):
        x, y = xy(cum[m["idx"]], ele[m["idx"]])
        out.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{H - pad}" stroke="#1f4e79" stroke-dasharray="3 3"/>')
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="#1f4e79"/>')
        out.append(f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="11" fill="#fff" font-weight="700">{n + 1}</text>')
        out.append(f'<text x="{x:.1f}" y="{H - pad + 16}" text-anchor="middle" font-size="11">{m["km"]:.1f}</text>')
    out.append("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------- HTML export
PAGE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%%TITLE%% - Trail Buddy</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
body{font-family:system-ui,sans-serif;max-width:760px;margin:24px auto;padding:0 12px;color:#222}
.sketch svg{width:100%;height:auto;margin:8px 0}
#map{height:460px;border-radius:10px;display:none;margin:8px 0}
.pin{width:26px;height:26px;border-radius:50%;color:#fff;font:700 13px/26px system-ui;text-align:center;border:2px solid #fff;box-shadow:0 1px 4px #0006}
table{border-collapse:collapse;width:100%}
td,th{border-bottom:1px solid #ddd;padding:6px;text-align:left;font-size:14px}
pre{white-space:pre-wrap;font-family:inherit;background:#f4f1e8;padding:12px;border-radius:8px}
.stats span{display:inline-block;background:#f4f1e8;border-radius:8px;padding:6px 12px;margin:3px}
.warn{background:#fff3cd;border-radius:8px;padding:8px 12px;margin:8px 0}
#locbtn{display:none;padding:8px 14px;border:0;border-radius:8px;background:#1f4e79;color:#fff;font-size:14px;cursor:pointer}
#mapnote{font-size:13px;color:#555}
</style></head><body>
<h1>%%TITLE%%</h1>
<div class="stats"><span><b>%%KM%% km</b> one way</span><span><b>+%%ASCENT%% m</b> climb</span>
<span><b>%%MAXELE%% m</b> high point</span><span>Up <b>%%TUP%%</b></span><span>Down <b>%%TDOWN%%</b></span></div>
%%WARNINGS%%
<div id="map"></div>
<div id="svgmap" class="sketch">%%MAPSVG%%</div>
<button id="locbtn">Show my location</button>
<p id="mapnote"></p>
<div class="sketch">%%PROFILE%%</div>
<h2>Stages</h2><table><tr><th>#</th><th>Waypoint</th><th>Distance</th><th>Elevation</th><th>Stage</th></tr>%%ROWS%%</table>
%%TIPS%%
<p><small>Source: %%SOURCE%%. Estimates only: check weather and conditions locally and tell someone your plan.</small></p>
<script>
(function(){
  var route=%%ROUTE%%, marks=%%MARKS%%;
  var note=document.getElementById('mapnote');
  if(!window.L){
    note.textContent='Offline: showing the built-in route sketch (no map tiles). Connect to the internet for the live map.';
    return;
  }
  document.getElementById('svgmap').style.display='none';
  document.getElementById('map').style.display='block';
  var btn=document.getElementById('locbtn'); btn.style.display='inline-block';
  var map=L.map('map');
  var topo=L.tileLayer('https://tile.opentopomap.org/{z}/{x}/{y}.png',{maxZoom:17,attribution:'Map data &copy; OpenStreetMap contributors, SRTM | Style &copy; OpenTopoMap (CC-BY-SA)'});
  var osm=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'});
  topo.addTo(map);
  L.control.layers({'Topographic (contours)':topo,'Street map':osm}).addTo(map);
  var line=L.polyline(route,{color:'#d6451f',weight:5}).addTo(map);
  marks.forEach(function(m){
    var icon=L.divIcon({className:'',html:'<div class="pin" style="background:'+m.color+'">'+m.n+'</div>',iconSize:[26,26],iconAnchor:[13,13]});
    var txt='<b>'+m.n+'. '+m.name+'</b><br>'+m.km+' km, '+m.ele+' m'+(m.desc?'<br>'+m.desc:'');
    L.marker([m.lat,m.lon],{icon:icon}).addTo(map).bindPopup(txt);
  });
  map.fitBounds(line.getBounds(),{padding:[30,30]});
  var me=null, acc=null, watching=false;
  btn.onclick=function(){
    if(watching){map.stopLocate();watching=false;btn.textContent='Show my location';return;}
    map.locate({watch:true,enableHighAccuracy:true});watching=true;btn.textContent='Stop tracking';
  };
  map.on('locationfound',function(e){
    if(!me){
      me=L.circleMarker(e.latlng,{radius:8,color:'#fff',weight:3,fillColor:'#1a73e8',fillOpacity:1}).addTo(map);
      acc=L.circle(e.latlng,{radius:e.accuracy,weight:1}).addTo(map);
    }else{me.setLatLng(e.latlng);acc.setLatLng(e.latlng);acc.setRadius(e.accuracy);}
  });
  map.on('locationerror',function(e){note.textContent='Could not get your location: '+e.message;});
  note.textContent='Live map. Map tiles need internet; the route line and stages are stored in this page.';
})();
</script></body></html>"""


def _slug(text):
    import re
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "route"


def _json(obj):
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def write_map_html(info, extra_text=""):
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    last = len(info["marks"]) - 1
    rows, marks_js = "", []
    for n, m in enumerate(info["marks"], 1):
        stage = info["stages"][n - 2] if n > 1 else None
        stage_txt = f"+{stage['ascent']:.0f} m, {fmt_time(stage['time'])}" if stage else "-"
        rows += (f"<tr><td>{n}</td><td><b>{escape(m['name'])}</b><br>"
                 f"<small>{escape(m['desc'])}</small></td>"
                 f"<td>{m['km']:.1f} km</td><td>{m['ele']:.0f} m</td><td>{stage_txt}</td></tr>")
        p = info["points"][m["idx"]]
        marks_js.append({"n": n, "name": m["name"], "desc": m["desc"],
                         "lat": round(p["lat"], 5), "lon": round(p["lon"], 5),
                         "km": round(m["km"], 1), "ele": round(m["ele"]),
                         "color": "#2e8b57" if n == 1 else "#b3261e" if n - 1 == last else "#1f4e79"})
    warn = "".join(f'<div class="warn">{escape(w)}</div>' for w in info.get("warnings", []))
    tips = f"<h2>Trail Buddy tips</h2><pre>{escape(extra_text)}</pre>" if extra_text else ""
    page = (PAGE.replace("%%TITLE%%", escape(info["name"]))
            .replace("%%KM%%", f"{info['total_km']:.1f}")
            .replace("%%ASCENT%%", f"{info['ascent']:.0f}")
            .replace("%%MAXELE%%", f"{info['max_ele']:.0f}")
            .replace("%%TUP%%", fmt_time(info["time_up"]))
            .replace("%%TDOWN%%", fmt_time(info["time_down"]))
            .replace("%%WARNINGS%%", warn)
            .replace("%%MAPSVG%%", _map_svg(info))
            .replace("%%PROFILE%%", _profile_svg(info))
            .replace("%%ROWS%%", rows)
            .replace("%%TIPS%%", tips)
            .replace("%%SOURCE%%", escape(info.get("source", "GPX file")))
            .replace("%%ROUTE%%", _json([[round(p["lat"], 5), round(p["lon"], 5)] for p in info["points"]]))
            .replace("%%MARKS%%", _json(marks_js)))
    out = config.OUTPUT_DIR / f"{_slug(info['name'])}_map.html"
    out.write_text(page, encoding="utf-8")
    return out


_server = None


def _serve():
    """Serve output/ on localhost so the browser allows live GPS (needs a secure origin)."""
    global _server
    if _server:
        return _server.server_address[1]
    import functools
    import threading
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(config.OUTPUT_DIR))
    for port in range(config.MAP_PORT, config.MAP_PORT + 10):
        try:
            _server = ThreadingHTTPServer(("127.0.0.1", port), handler)
            threading.Thread(target=_server.serve_forever, daemon=True).start()
            return port
        except OSError:
            continue
    return None


def open_in_browser(path):
    port = _serve()
    url = f"http://localhost:{port}/{path.name}" if port else path.resolve().as_uri()
    webbrowser.open(url)
    return url


def save_gpx(path, name, points, waypoints):
    def esc(t):
        return escape(t or "")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<gpx version="1.1" creator="Trail Buddy" xmlns="http://www.topografix.com/GPX/1/1">']
    for w in waypoints:
        lines.append(f'  <wpt lat="{w["lat"]:.6f}" lon="{w["lon"]:.6f}"><ele>{w["ele"]:.0f}</ele>'
                     f'<name>{esc(w["name"])}</name><desc>{esc(w.get("desc", ""))}</desc></wpt>')
    lines.append(f'  <trk><name>{esc(name)}</name><trkseg>')
    for p in points:
        lines.append(f'    <trkpt lat="{p["lat"]:.6f}" lon="{p["lon"]:.6f}"><ele>{p["ele"]:.0f}</ele></trkpt>')
    lines += ['  </trkseg></trk>', '</gpx>']
    path.write_text("\n".join(lines), encoding="utf-8")


def list_trails():
    return sorted(p.stem for p in config.DATA_DIR.glob("*.gpx"))