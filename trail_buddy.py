"""Trail Buddy: trek companion powered by a local open-weight LLM.
Plan a route between ANY two places (online), save it, and reuse it offline.
Run: python trail_buddy.py"""
import re

import ollama

import config
import online
import route
import webapp
from rag import build_index, search

HELP = """Commands:
  /web                     open the interactive map planner (walk, bike or cab, live GPS)
  /plan                    asks where you start and where you want to go
  /plan <from> to <to>     e.g. /plan Mandi bus stand to Prashar Lake
  /roadmap <saved trail>   open a saved route (works offline)
  /trails                  list saved routes
  /sources                 toggle which notes were used for answers
  /quit                    exit
Or just ask: "roadmap from Baggi to Prashar Lake" or "give me the route for Rewalsar".
"""

PLAN_WORDS = ("roadmap", "route", "map", "plan my", "plan a", "directions",
              "how to reach", "how do i get", "how to get")


# ------------------------------------------------------------------- chat
def build_messages(question, hits, history):
    context = "\n\n---\n\n".join(h["text"] for h in hits)
    messages = [{"role": "system", "content": config.SYSTEM_PROMPT}]
    messages += history[-6:]
    messages.append({"role": "user",
                     "content": f"Trail notes:\n{context}\n\nQuestion: {question}"})
    return messages


def stream_chat(messages):
    reply = ""
    for part in ollama.chat(model=config.CHAT_MODEL, messages=messages, stream=True):
        piece = part["message"]["content"]
        reply += piece
        print(piece, end="", flush=True)
    print("\n")
    return reply


def ask(question, index, history, show_sources=False):
    hits = search(question, index)
    if show_sources:
        print("  [sources]", ", ".join(sorted({h["source"] for h in hits})))
    reply = stream_chat(build_messages(question, hits, history))
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": reply})


# --------------------------------------------------------------- planning
def find_trail(text):
    """Return the saved trail whose name appears in text, if any."""
    text = text.lower().replace("_", " ")
    for stem in route.list_trails():
        if stem.replace("_", " ") in text:
            return stem
    return None


def notes_for(text):
    stem = find_trail(text or "")
    notes_file = config.DATA_DIR / f"{stem}.md" if stem else None
    return notes_file.read_text(encoding="utf-8") if notes_file and notes_file.exists() else ""


def present(info, notes=""):
    table = route.roadmap_text(info)
    print(table, "\n")

    prompt = (
        "Using ONLY the route data and trail notes below, write 4 to 6 short practical "
        "tips for this trek in order (before leaving, on the way up, at the top, coming "
        "down). Do not invent facts, times, shops, water points or places. If the notes "
        "are empty, base tips only on the distance, climb and warnings.\n\n"
        f"ROUTE DATA:\n{table}\n\nTRAIL NOTES:\n{notes or '(none)'}"
    )
    print("Buddy tips:\n")
    tips = stream_chat([{"role": "system", "content": config.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}])

    out = route.write_map_html(info, extra_text=tips)
    url = route.open_in_browser(out)
    print(f"Map opened in your browser: {url}\n(file: {out})\n")


def open_saved(stem):
    info = route.analyse(config.DATA_DIR / f"{stem}.gpx")
    present(info, notes_for(stem))


def clean_place(text):
    text = re.sub(r"\s+trek$", "", text.strip(" ?.!,"), flags=re.I)
    return re.sub(r"^(the)\s+", "", text, flags=re.I).strip()


def extract_places(q, bare=False):
    """Pull (start, destination) out of text. bare=True also accepts 'A to B'."""
    m = re.search(r"\bfrom\s+(.+?)\s+to\s+(.+)", q, re.I)
    if not m and bare:
        m = re.match(r"^(.+?)\s+to\s+(.+)$", q.strip(), re.I)
    if m:
        return clean_place(m.group(1)), clean_place(m.group(2))
    m = re.search(r"\b(?:to|for)\s+(.+)", q, re.I)
    if m:
        return None, clean_place(m.group(1))
    return None, None


def plan_flow(start=None, dest=None):
    if not dest:
        dest = input("Where do you want to go? ").strip()
    if not dest:
        print("  Need a destination.\n")
        return
    saved = find_trail(dest)

    if not start:
        hint = " (Enter = use saved route)" if saved else ""
        start = input(f"Where are you starting from?{hint} ").strip()
        if not start and saved:
            open_saved(saved)
            return
        if not start:
            print("  Need a starting point (a place name, or coordinates like 31.70,76.93).\n")
            return

    print(f"Planning walking route: {start} -> {dest} ...")
    try:
        info, saved_path = online.plan_route(start, dest)
    except online.OnlineError as e:
        print(f"  {e}")
        if saved:
            print(f"  Using your saved offline route for '{saved.replace('_', ' ')}' instead.\n")
            open_saved(saved)
        else:
            print("  No saved route for that place. Connect to the internet, or add a GPX file.\n")
        return
    print(f"Saved for offline use: {saved_path.name}\n")
    present(info, notes_for(dest) or notes_for(start))


# ------------------------------------------------------------------- main
def main():
    index = build_index()
    history, show_sources = [], False
    print(f"Trail Buddy ready (model: {config.CHAT_MODEL}).")
    print("Chat works offline. Route planning for new treks needs internet once; "
          "planned routes are saved for offline use.\n")
    print(HELP)

    while True:
        try:
            q = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        low = q.lower()
        if low == "/quit":
            break
        if low == "/help":
            print(HELP)
        elif low == "/web":
            print(f"  Planner opened: {webapp.start()}\n")
        elif low == "/sources":
            show_sources = not show_sources
            print(f"  sources {'on' if show_sources else 'off'}\n")
        elif low == "/trails":
            print("  " + (", ".join(route.list_trails()) or "no saved routes yet") + "\n")
        elif low.startswith("/plan"):
            start, dest = extract_places(q[5:].strip(), bare=True)
            if not dest and q[5:].strip():
                dest = clean_place(q[5:])
            plan_flow(start, dest)
        elif low.startswith("/roadmap"):
            name = q[8:].strip()
            stem = find_trail(name) or name.replace(" ", "_").lower()
            try:
                open_saved(stem)
            except FileNotFoundError:
                print(f"  No saved route '{name}'. Try /trails or /plan\n")
            except ValueError as e:
                print(f"  {e}\n")
        elif any(w in low for w in PLAN_WORDS):
            start, dest = extract_places(q)
            try:
                plan_flow(start, dest)
            except ValueError as e:
                print(f"  {e}\n")
        else:
            print("Buddy: ", end="")
            ask(q, index, history, show_sources)
    print("Happy trekking!")


if __name__ == "__main__":
    main()