"""Lokales Web-Dashboard: serviert die UI + einen JSON-Zustand.

Nur Python-Standardbibliothek (kein Flask noetig -> leichter als .exe zu
packen). Laeuft in einem Thread neben dem UDP-Loop.

Endpunkte:
    GET /api/state   -> kompletter Zustand (siehe snapshot.build_state)
    GET /            -> web/index.html (die in Claude Design entworfene UI)
    GET /<datei>     -> statische Datei aus dem web/-Ordner
"""
from __future__ import annotations

import json
import os
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
WEB_DIR = os.path.abspath(WEB_DIR)

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml", ".webp": "image/webp", ".ico": "image/x-icon",
}


class _Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, snapshot_fn: Callable[[], dict], web_dir: str,
                 lap_fn: Callable[[str], dict | None] | None = None,
                 delete_fn: Callable[[str], bool] | None = None,
                 cars_dir: str | None = None,
                 update_fn: Callable[[], dict | None] | None = None,
                 export_fn: Callable[[], bytes] | None = None,
                 import_fn: Callable[[bytes], bool] | None = None, **kwargs):
        self._snapshot_fn = snapshot_fn
        self._web_dir = web_dir
        self._lap_fn = lap_fn
        self._delete_fn = delete_fn
        self._cars_dir = cars_dir
        self._update_fn = update_fn
        self._export_fn = export_fn
        self._import_fn = import_fn
        super().__init__(*args, **kwargs)

    def log_message(self, *args):  # still: keine Konsolen-Spam
        pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/state":
            self._send_json(self._snapshot_fn())
            return
        if path.startswith("/api/lap/") and self._lap_fn is not None:
            lap_id = path[len("/api/lap/"):]
            data = self._lap_fn(lap_id)
            if data is None:
                self.send_error(404)
            else:
                self._send_json(data)
            return
        if path == "/api/update":
            # On-Demand-Versionscheck (nur wenn das Dashboard ihn anfordert).
            info = self._update_fn() if self._update_fn is not None else None
            self._send_json(info or {})
            return
        if path == "/api/export" and self._export_fn is not None:
            body = self._export_fn()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition",
                             'attachment; filename="fh6laptracker-backup.zip"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in ("/", ""):
            path = "/index.html"
        self._send_static(path)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/import" and self._import_fn is not None:
            length = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(length) if length > 0 else b""
            if self._import_fn(data):
                self._send_json({"ok": True})
            else:
                self.send_error(400)
            return
        self.send_error(405)

    def do_DELETE(self):
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/lap/") and self._delete_fn is not None:
            ok = self._delete_fn(path[len("/api/lap/"):])
            if ok:
                self._send_json({"deleted": True})
            else:
                self.send_error(404)
            return
        self.send_error(405)

    def _send_json(self, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, path: str):
        # Pfad-Traversal verhindern
        rel = os.path.normpath(path.lstrip("/")).replace("\\", "/")
        if rel.startswith("..") or os.path.isabs(rel):
            self.send_error(403)
            return
        # Fahrzeugbilder: zuerst aus dem cars/-Ordner neben der App (optional,
        # nicht mitgebuendelt), sonst normaler web/-Ordner.
        full = None
        if rel.startswith("cars/") and self._cars_dir:
            cand = os.path.join(self._cars_dir, rel[len("cars/"):])
            if os.path.isfile(cand):
                full = cand
        if full is None:
            full = os.path.join(self._web_dir, rel)
        if not os.path.isfile(full):
            self.send_error(404)
            return
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", _CONTENT_TYPES.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_web_server(
    snapshot_fn: Callable[[], dict],
    host: str = "127.0.0.1",
    port: int = 8770,
    web_dir: str = WEB_DIR,
    lap_fn: Callable[[str], dict | None] | None = None,
    delete_fn: Callable[[str], bool] | None = None,
    cars_dir: str | None = None,
    update_fn: Callable[[], dict | None] | None = None,
    export_fn: Callable[[], bytes] | None = None,
    import_fn: Callable[[bytes], bool] | None = None,
) -> ThreadingHTTPServer:
    """Startet den Server in einem Daemon-Thread und gibt ihn zurueck."""
    handler = partial(_Handler, snapshot_fn=snapshot_fn, web_dir=web_dir,
                      lap_fn=lap_fn, delete_fn=delete_fn, cars_dir=cars_dir,
                      update_fn=update_fn, export_fn=export_fn, import_fn=import_fn)
    httpd = ThreadingHTTPServer((host, port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
