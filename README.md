# Trail Buddy

Trekking companion for the hills around Mandi, Himachal Pradesh, powered by a local open-weight LLM (Ollama + qwen2.5:3b).
Plan a route once online, save it as GPX, reuse it offline.

## Setup
pip install ollama
ollama pull qwen2.5:3b
ollama pull nomic-embed-text

## Run
python trail_buddy.py   # terminal chat and route planner
python webapp.py        # web planner at http://localhost:8780/planner.html

Trail notes in data/trails are SAMPLE data. Verify locally before trekking.
Licence: MIT
