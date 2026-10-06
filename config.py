import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "trails"
INDEX_FILE = BASE_DIR / "index_cache.json"

# Swap models freely: that's the open-weight advantage.
CHAT_MODEL = os.getenv("TB_CHAT_MODEL", "qwen2.5:3b")
EMBED_MODEL = os.getenv("TB_EMBED_MODEL", "nomic-embed-text")

TOP_K = 3  # how many note chunks to give the model per question

SYSTEM_PROMPT = """You are Trail Buddy, an offline trekking companion for the \
hills around Mandi, Himachal Pradesh.

Rules:
1. Answer ONLY using the trail notes provided in the context.
2. If the notes do not contain the answer, say "I don't have that in my notes" \
and suggest asking a local guide or villagers.
3. Keep answers short and practical: the user is walking, not reading.
4. For safety questions (weather, water, difficulty), remind the user to check \
conditions locally and never trek alone in bad weather.
5. Mention which trail the information comes from."""

# ---- Route / roadmap settings ----
OUTPUT_DIR = BASE_DIR / "output"
WALK_SPEED_KMH = 4.0        # flat walking speed for a beginner group
ASCENT_M_PER_HOUR = 500     # extra hour per this many metres of climbing

# ---- Online planning (any trek, any start and destination) ----
USER_AGENT = "TrailBuddy/1.0 (Hacktoberfest open-source AI challenge demo)"
GEO_COUNTRY = "in"          # limit place search to India; set "" to search worldwide
GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
ROUTE_FOOT_URL = "https://routing.openstreetmap.de/routed-foot/route/v1/foot"
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
MAX_ELEVATION_POINTS = 300  # route is sampled down to this many points
WARN_ROUTE_KM = 30          # warn: long for a day trek
MAX_ROUTE_KM = 150          # refuse: not a realistic walking route
MAP_PORT = 8765             # local page server so live GPS works in the browser

# ---- Interactive web planner (web/planner.html) ----
WEB_DIR = BASE_DIR / "web"
WEB_PORT = 8780