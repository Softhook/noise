"""The survey app's web server: every source's tracks, heights and noise for a day, on one page.

    python3 -m survey serve            then open http://127.0.0.1:8766

It only listens on this computer, and reads only built deployments (python3 -m survey build), so
it never touches a source's own files. Rebuild from the page, or on the command line, after
fetching more data. Downloads stay in each tool: the WebTrak app (python3 -m webtrak serve) and
`make viewer` in tools/opensky.

This module is only HTTP: the page's files come from ui/, and the answers from app.App.
"""

from __future__ import annotations

import http.server
import json
import os
import threading
import urllib.parse

from .app import App, BadRequest

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8"}
# path -> what answers it, given the App and the request's query (GET) or JSON body (POST)
GET_ROUTES = {"/api/deployments": lambda app, query: app.deployments(),
              "/api/day": lambda app, query: app.day(query)}
POST_ROUTES = {"/api/build": lambda app, body: app.rebuild(body)}


def ui_file(path):
    """The ui/ file a page path names, or None. Only files directly in ui/, of a known type."""
    name = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
    if "/" in name or "\\" in name or os.path.splitext(name)[1] not in CONTENT_TYPES:
        return None
    full = os.path.join(UI_DIR, name)
    return full if os.path.isfile(full) else None


class Handler(http.server.BaseHTTPRequestHandler):
    app: App = None
    server_version = "survey"

    def log_message(self, fmt, *args):
        pass

    def _local_host(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ("127.0.0.1", "localhost", "[::1]")

    def _send(self, code, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _run(self, route, arg):
        try:
            self._send(200, route(self.app, arg))
        except BadRequest as error:
            self._send(400, {"error": str(error)})
        except Exception as error:  # report it to the page rather than drop the connection
            self._send(500, {"error": f"{type(error).__name__}: {error}"})

    def do_GET(self):
        if not self._local_host():  # refuse pages reached through another host name (DNS rebinding)
            return self._send(403, {"error": "local use only"})
        url = urllib.parse.urlsplit(self.path)
        if url.path in GET_ROUTES:
            return self._run(GET_ROUTES[url.path], dict(urllib.parse.parse_qsl(url.query)))
        path = ui_file(url.path)
        if path:
            with open(path, "rb") as f:
                return self._send(200, f.read(), CONTENT_TYPES[os.path.splitext(path)[1]])
        self._send(404, {"error": "not found"})

    def do_POST(self):
        # JSON only: a page on another site can't send that without the browser asking first.
        if not self._local_host() or not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._send(403, {"error": "local use only"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad JSON"})
        if self.path in POST_ROUTES:
            return self._run(POST_ROUTES[self.path], body)
        self._send(404, {"error": "not found"})


def serve(port=8766, open_browser=True, deployments_dir=None):
    Handler.app = App(deployments_dir)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Survey app at {url}  (Ctrl-C to close it)", flush=True)
    if open_browser:
        import webbrowser
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


def main(args):
    return serve(args.port, not args.no_browser)
