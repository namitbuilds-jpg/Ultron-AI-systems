#!/usr/bin/env python3
"""Safe loopback-only static server for the ULTRON HUD and Creative Studio.
Only the two HTML apps and generated media files are served; dotfiles, source,
configuration, Python files, and project documentation are never exposed.
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
import mimetypes
import re

ROOT = Path(__file__).resolve().parent
HOST, PORT = "127.0.0.1", 8000
GENERATED_NAME = re.compile(r"^[A-Za-z0-9_-]+\.(?:png|jpe?g|webp|mp4|pptx)$", re.I)

class SafeHUDHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        return str(ROOT / "__blocked__")

    def _resolve(self):
        path = unquote(urlsplit(self.path).path)
        if path in ("/", "/ultron.html"):
            return ROOT / "ultron.html"
        if path == "/studio.html":
            return ROOT / "studio.html"
        if path.startswith("/generated/"):
            name = path[len("/generated/"):]
            if "/" not in name and GENERATED_NAME.fullmatch(name):
                candidate = (ROOT / "generated" / name).resolve()
                generated_root = (ROOT / "generated").resolve()
                if candidate.parent == generated_root and candidate.is_file():
                    return candidate
        return None

    def do_GET(self):
        target = self._resolve()
        if target is None:
            self.send_error(404, "Not found")
            return
        content = target.read_bytes()
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_HEAD(self):
        target = self._resolve()
        if target is None:
            self.send_error(404, "Not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(target.stat().st_size))
        self.end_headers()

    def log_message(self, fmt, *args):
        print("[HUD] " + fmt % args)

if __name__ == "__main__":
    print(f"ULTRON safe HUD server: http://localhost:{PORT}/ultron.html")
    print("Only ultron.html, studio.html, and generated media are served.")
    ThreadingHTTPServer((HOST, PORT), SafeHUDHandler).serve_forever()
