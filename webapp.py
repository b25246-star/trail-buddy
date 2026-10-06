"""Serves the interactive route planner at http://localhost:8780/planner.html
Run on its own:  python webapp.py      (or type /web inside Trail Buddy)

It is served from localhost on purpose: browsers only allow live GPS on secure
origins, and localhost counts as secure."""
import functools
import json
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import config

_server = None


class _Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep the terminal clean
        pass

    def do_GET(self):
        if self.path.split("?")[0] == "/config.json":
            body = json.dumps({"chat_model": config.CHAT_MODEL}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def start(open_browser=True):
    """Start the server in a background thread. Returns the page URL."""
    global _server
    if _server is None:
        handler = functools.partial(_Handler, directory=str(config.WEB_DIR))
        for port in range(config.WEB_PORT, config.WEB_PORT + 10):
            try:
                _server = ThreadingHTTPServer(("127.0.0.1", port), handler)
                break
            except OSError:
                continue
        else:
            raise OSError("No free port found for the web planner.")
        threading.Thread(target=_server.serve_forever, daemon=True).start()
    url = f"http://localhost:{_server.server_address[1]}/planner.html"
    if open_browser:
        webbrowser.open(url)
    return url


if __name__ == "__main__":
    page = start()
    print(f"Trail Buddy planner running at {page}\nPress Ctrl+C to stop.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nStopped.")