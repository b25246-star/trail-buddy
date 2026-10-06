# Trail Buddy 🥾

**An offline-first trekking companion for the hills around Mandi, Himachal Pradesh, powered by a local open-weight LLM.**

Plan a route between any two places while you have internet, save it, and reuse it later with no signal. The chat assistant runs entirely on your own machine through [Ollama](https://ollama.com), so nothing about your trip is sent to a cloud AI.

Built for the [Hacktoberfest Open-Source AI Challenge, Week 1: Touch Grass](https://dev.to/challenges/hacktoberfest-week1-2026-10-05).

<!-- Add a screenshot or GIF here, e.g. ![Trail Buddy planner](docs/planner.png) -->

---

## Why this exists

The best trails are exactly where mobile signal disappears. Most trip planners need a connection at the moment you are standing at a fork with no bars. Trail Buddy does the internet-dependent part once, at home or at the bus stand, saves the route as a plain GPX file, and everything else (roadmap, notes, AI chat) keeps working offline.

## Features

- **Stage-by-stage roadmap** with distance, climb, high point and estimated up/down times.
- **Plan any route** between two places or coordinates using free OpenStreetMap services, then save it as GPX.
- **Offline reuse**: saved routes open from disk with no internet.
- **Grounded AI chat** (RAG): answers come only from your own Markdown trail notes. If the notes don't have it, the model says so instead of guessing.
- **Buddy tips**: the local model turns the calculated route facts and your notes into short, practical tips.
- **Interactive web planner** with walk, bike and cab modes, alternative routes, an elevation profile you can scrub, turn-by-turn directions and live GPS tracking with off-route warnings.
- **Map export**: a self-contained HTML page with a live topographic map when online, and a built-in SVG sketch when offline.
- **Swap models freely**: change one environment variable to try a different open-weight model.

## What needs internet and what doesn't

| Feature | Internet needed? |
| --- | --- |
| AI chat over your trail notes | No |
| Opening a saved route (`/roadmap`) | No |
| Roadmap table, elevation profile, SVG route sketch | No |
| Planning a **new** route (`/plan`) | Yes, once |
| Live map tiles | Yes |
| Web planner (place search, routing, tiles, elevation) | Yes |

## Requirements

- Python 3.9 or newer
- [Ollama](https://ollama.com/download) installed and running
- About 3 GB of free disk space for the models
- A modern browser (for the map and web planner)

The only Python dependency is the `ollama` package. Everything else uses the standard library.

## Setup

```bash
# 1. Get the code
git clone https://github.com/YOUR-USERNAME/trail-buddy.git
cd trail-buddy

# 2. Install the Python client
pip install ollama

# 3. Download the open-weight models (one time)
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
```

Make sure the Ollama app is running before you start Trail Buddy.

## Usage

### Terminal chat and route planner

```bash
python trail_buddy.py
```

| Command | What it does |
| --- | --- |
| `/plan` | Asks where you start and where you want to go |
| `/plan <from> to <to>` | Plans a walking route, e.g. `/plan Mandi bus stand to Prashar Lake` |
| `/roadmap <saved trail>` | Opens a saved route (works offline) |
| `/trails` | Lists saved routes |
| `/web` | Opens the interactive map planner |
| `/sources` | Toggles showing which notes were used for each answer |
| `/help` | Shows the command list |
| `/quit` | Exits |

You can also just type naturally:

```
roadmap from Baggi to Prashar Lake
What should I carry for Prashar Lake?
Is it safe to go in the afternoon?
```

Place names are searched across India by default. Add the district or state if a name is ambiguous (for example `Prashar Lake, Mandi`), or type coordinates like `31.75,77.09`.

### Web planner

```bash
python webapp.py
```

Opens <http://localhost:8780/planner.html>. You can also start it from inside the chat with `/web`.

In the planner you can:

- Search for places, use your current location, or drop pins on the map (tap the pin button, or right-click the map for "Start here" / "Go here").
- Choose **Walk**, **Bike** or **Cab** and compare up to three route options.
- Slide along the elevation profile to see each point on the map.
- Press **Track me** for live GPS, distance left and an off-route warning.
- Open the route in Google Maps, or ask the local model for tips.

It is served from `localhost` on purpose: browsers only allow live GPS on secure origins, and `localhost` counts as secure.

## Add your own trail

A trail is two plain files in `data/trails/` that share a name:

```
data/trails/rewalsar.gpx   # the route (track points and optional waypoints)
data/trails/rewalsar.md    # your notes, used by the chat and tips
```

**Notes format:** one `# Title` line, then `## Section` headings. Each section becomes one searchable chunk.

```markdown
# Rewalsar Lake

## Overview
...

## Water and Food
...

## Safety Notes
...
```

**GPX:** any GPX with `trkpt` (or `rtept`) points and elevation works. `wpt` waypoints become the named stages of the roadmap. You can also let `/plan` generate and save one for you.

The notes index is cached in `index_cache.json` and rebuilt automatically when your notes change.

## Configuration

Settings live in `config.py`. The most useful ones:

| Setting | Default | Purpose |
| --- | --- | --- |
| `TB_CHAT_MODEL` (env var) | `qwen2.5:3b` | Chat model served by Ollama |
| `TB_EMBED_MODEL` (env var) | `nomic-embed-text` | Embedding model for note search |
| `TOP_K` | `3` | Note chunks given to the model per question |
| `WALK_SPEED_KMH` | `4.0` | Flat walking speed for time estimates |
| `ASCENT_M_PER_HOUR` | `500` | Extra hour per this many metres climbed |
| `GEO_COUNTRY` | `"in"` | Limit place search to a country; `""` searches worldwide |
| `WARN_ROUTE_KM` / `MAX_ROUTE_KM` | `30` / `150` | Warn on, or refuse, unrealistically long walks |
| `MAP_PORT` / `WEB_PORT` | `8765` / `8780` | Local server ports (next 10 are tried if busy) |

Try a different model:

```bash
# macOS / Linux
TB_CHAT_MODEL=llama3.2:3b python trail_buddy.py

# Windows PowerShell
$env:TB_CHAT_MODEL = "llama3.2:3b"; python trail_buddy.py
```

## How it works

```
                 +--------------------+
  your notes --> | rag.py             |--> top matching sections --+
  (Markdown)     | embed + cosine     |                            |
                 +--------------------+                            v
                                                       +---------------------+
  GPX file  ---> +--------------------+                | Ollama (local LLM)  |--> short answers
  or /plan       | route.py           |-- route facts->| strict system prompt|    and trail tips
                 | stages, climb,     |                +---------------------+
                 | time, SVG, HTML    |
                 +--------------------+
                          ^
                          | one-time online step
                 +--------------------+
                 | online.py          |  Nominatim (search), OSM foot router,
                 | place -> route ->  |  Open-Meteo (elevation) -> saved as GPX
                 | elevation          |
                 +--------------------+
```

A few design choices worth knowing:

- **The AI never invents the route.** Distances, climbs and times are calculated by code. The model only turns those facts and your notes into advice.
- **Grounded by design.** A small model will happily invent a tea stall, which is dangerous on a mountain. The system prompt restricts answers to the retrieved notes, and the model is told to say "I don't have that in my notes" otherwise.
- **No vector database.** A handful of trails fit in a JSON file with cosine search.
- **Time estimates are a rule of thumb:** 4 km/h on the flat plus one extra hour per 500 m climbed.

## Project structure

```
trail-buddy/
├── trail_buddy.py      # terminal chat and planner
├── rag.py              # local retrieval over Markdown notes
├── route.py            # GPX -> roadmap, SVG map, HTML export
├── online.py           # one-time online route planning
├── webapp.py           # serves the web planner on localhost
├── config.py           # settings
├── web/
│   └── planner.html    # interactive map planner
├── data/trails/        # your trail notes (.md) and routes (.gpx)
├── output/             # generated map pages (git-ignored)
└── index_cache.json    # generated notes index (git-ignored)
```

## Troubleshooting

- **"Could not reach Ollama"**: open the Ollama app and check the model name matches `ollama list`.
- **Model not found**: run `ollama pull qwen2.5:3b` and `ollama pull nomic-embed-text`.
- **Blank map or no search results**: the map, place search and routing need internet. Offline, use `/roadmap` on a saved route.
- **"No walking route found"**: the two places may not be joined by mapped paths. Start from the trailhead, drop a pin on the trail, or try Cab for the road section.
- **Location blocked**: allow location access in the browser address bar, then press **Track me** again. Make sure you opened the page via `localhost`, not by double-clicking the file.
- **Port already in use**: the servers try the next 10 ports. Use the URL printed in the terminal.

## Safety

The sample notes in `data/trails/` are **placeholder data**. Verify water points, timings and conditions with locals before relying on them. Time estimates are rough and do not account for rest stops, weather or fitness. Check conditions locally, tell someone your plan, carry water and a torch, and turn back if clouds build up. Never trek alone in bad weather.

## Open-source pieces and credits

- [Ollama](https://ollama.com), [Qwen2.5](https://github.com/QwenLM/Qwen2.5) and [nomic-embed-text](https://www.nomic.ai) for local inference
- [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors for map data, place search and walking, bike and road routing
- [OpenTopoMap](https://opentopomap.org) for topographic tiles
- [Open-Meteo](https://open-meteo.com) for elevation data
- [Photon](https://photon.komoot.io) for place suggestions in the web planner
- [Leaflet](https://leafletjs.com) for the interactive map

Please respect the usage policies of the free public services (Nominatim in particular allows about one request per second).

## Contributing

Contributions are welcome, especially **verified trail notes and GPX files** for treks around Mandi and beyond. Open an issue or a pull request.

## Licence

MIT. See [LICENSE](LICENSE).