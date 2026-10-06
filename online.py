"""Online trek planner: any start + destination -> walking route + elevation.
Uses free open services: OpenStreetMap Nominatim (search), the OSM foot router,
and Open-Meteo (elevation). Standard library only."""
import bisect
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import config
import route

COORD_RE = re.compile(r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


class OnlineError(Exception):
    pass


def _get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except json.JSONDecodeError:
        raise OnlineError("The online service returned unreadable data. Try again.")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise OnlineError(f"Could not reach the online service ({e}). "
                          "Check your internet connection.")


# ------------------------------------------------------------------ places
def geocode(query, limit=3):
    params = {"q": query, "format": "jsonv2", "limit": limit}
    if config.GEO_COUNTRY:
        params["countrycodes"] = config.GEO_COUNTRY
    data = _get_json(config.GEOCODE_URL + "?" + urllib.parse.urlencode(params))
    return [{"name": r["display_name"], "lat": float(r["lat"]), "lon": float(r["lon"])}
            for r in data]


def short_name(display_name):
    return display_name.split(",")[0].strip()


def choose_place(query):
    m = COORD_RE.match(query)
    if m:  # user typed coordinates, e.g. 31.7545,77.0963
        lat, lon = float(m.group(1)), float(m.group(2))
        return {"name": f"{lat:.4f}, {lon:.4f}", "lat": lat, "lon": lon}
    results = geocode(query)
    if not results:
        raise OnlineError(f"Could not find '{query}'. Add the district or state "
                          "(e.g. 'Prashar Lake, Mandi') or type coordinates like 31.75,77.09")
    if len(results) == 1:
        return results[0]
    print(f"  Matches for '{query}':")
    for i, r in enumerate(results, 1):
        print(f"   {i}. {r['name'][:100]}")
    pick = input("  Which one? (Enter = 1): ").strip()
    idx = int(pick) - 1 if pick.isdigit() and 1 <= int(pick) <= len(results) else 0
    return results[idx]


# ----------------------------------------------------------------- routing
def route_foot(a, b):
    url = (f"{config.ROUTE_FOOT_URL}/{a['lon']},{a['lat']};{b['lon']},{b['lat']}"
           "?overview=full&geometries=geojson")
    data = _get_json(url)
    if data.get("code") != "Ok" or not data.get("routes"):
        raise OnlineError("No walking route found between those two places. "
                          "They may not be connected by mapped paths.")
    return [(lat, lon) for lon, lat in data["routes"][0]["geometry"]["coordinates"]]


def _downsample(coords, limit):
    if len(coords) <= limit:
        return coords
    step = (len(coords) - 1) / (limit - 1)
    return [coords[round(i * step)] for i in range(limit)]


def elevations(coords):
    out = []
    for i in range(0, len(coords), 100):
        chunk = coords[i:i + 100]
        lat = ",".join(f"{c[0]:.5f}" for c in chunk)
        lon = ",".join(f"{c[1]:.5f}" for c in chunk)
        data = _get_json(f"{config.ELEVATION_URL}?latitude={lat}&longitude={lon}")
        out.extend(data["elevation"])
    return out


def _auto_waypoints(points, start_name, dest_name):
    cum = [0.0]
    for i in range(1, len(points)):
        cum.append(cum[-1] + route.haversine_m(points[i - 1], points[i]) / 1000)
    total = cum[-1]
    stages = max(2, min(8, round(total / 2.0)))
    wps = [dict(points[0], name=f"Start: {start_name}", desc="")]
    for k in range(1, stages):
        idx = min(bisect.bisect_left(cum, total * k / stages), len(points) - 1)
        wps.append(dict(points[idx], name=f"Checkpoint {k}",
                        desc=f"About {cum[idx]:.1f} km from the start."))
    wps.append(dict(points[-1], name=dest_name, desc="Destination."))
    return wps, total


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "route"


def plan_route(start_query, dest_query):
    """Returns (info, saved_gpx_path). Raises OnlineError with a friendly message."""
    a = choose_place(start_query)
    time.sleep(1.1)  # Nominatim fair-use: max 1 request per second
    b = choose_place(dest_query)

    coords = route_foot(a, b)
    coords = _downsample(coords, config.MAX_ELEVATION_POINTS)

    warnings = []
    try:
        eles = elevations(coords)
    except (OnlineError, KeyError):
        eles = [0.0] * len(coords)
        warnings.append("Elevation data was unavailable, so climb and time use "
                        "distance only. Treat times as a minimum.")
    points = [{"lat": la, "lon": lo, "ele": float(e)}
              for (la, lo), e in zip(coords, eles)]

    start_name, dest_name = short_name(a["name"]), short_name(b["name"])
    wps, total_km = _auto_waypoints(points, start_name, dest_name)
    if total_km > config.MAX_ROUTE_KM:
        raise OnlineError(f"That route is {total_km:.0f} km, which is too far to plan as "
                          "a walk. Pick a closer start point (e.g. the trailhead).")
    if total_km > config.WARN_ROUTE_KM:
        warnings.append(f"{total_km:.0f} km is long for a day trek. Consider a closer "
                        "start point or splitting it over several days.")

    name = f"{start_name} to {dest_name}"
    info = route.analyse_track(name, points, wps)
    info["warnings"] += warnings
    info["source"] = "OpenStreetMap walking route (online)"

    saved = config.DATA_DIR / f"{_slug(name)}.gpx"
    route.save_gpx(saved, name, points, wps)
    return info, saved