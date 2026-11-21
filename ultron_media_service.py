#!/usr/bin/env python3
"""ULTRON Creative Services — loopback-only Agnes AI media gateway.

Agnes credentials remain in the local .env file and are never returned to the HUD.
The service exposes only fixed image, video, health, and local presentation routes.
"""
from __future__ import annotations
import base64
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

HOST = "127.0.0.1"
ROOT = Path(__file__).resolve().parent

def load_local_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value

load_local_env()
PORT = int(os.getenv("ULTRON_MEDIA_PORT", "8766"))
OUT = ROOT / "generated"
OUT.mkdir(exist_ok=True)
KEY = os.getenv("AGNES_API_KEY", "").strip()
API_BASE = os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1").rstrip("/")
IMAGE_MODEL = os.getenv("AGNES_IMAGE_MODEL", "agnes-image-2.5-flash").strip()
VIDEO_MODEL = os.getenv("AGNES_VIDEO_MODEL", "agnes-video-2.5-flash").strip()
ALLOWED_IMAGE_MODELS = {"agnes-image-2.5-flash"}
ALLOWED_VIDEO_MODELS = {"agnes-video-2.5-flash", "agnes-video-2.5"}
MAX_BODY = 1_000_000

class AgnesAPIError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code

# Reject accidental non-HTTPS or unexpected provider hosts in configuration.
def validate_api_base(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
        raise RuntimeError("AGNES_BASE_URL must be a valid HTTPS URL.")
    return value.rstrip("/")

API_BASE = validate_api_base(API_BASE)
API_ROOT = API_BASE[:-3] if API_BASE.endswith("/v1") else API_BASE

def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length < 2 or length > MAX_BODY:
        raise ValueError("Request body is missing or too large.")
    data = json.loads(handler.rfile.read(length).decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object.")
    return data

def api_json(url, method="POST", payload=None, timeout=180):
    if not KEY:
        raise RuntimeError("Set AGNES_API_KEY in your local .env file to enable image/video generation.")
    headers = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "Accept": "application/json"}
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Agnes AI returned a response that was not valid JSON.") from exc
    except HTTPError as exc:
        detail = exc.read(1800).decode("utf-8", "replace")
        # Avoid echoing request headers or secrets; provider body is useful for diagnostics.
        raise AgnesAPIError(exc.code, f"Agnes AI returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Agnes AI: {exc.reason}") from exc

class Handler(BaseHTTPRequestHandler):
    server_version = "ULTRON-Creative/2.0"

    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin", "")
        if origin in ("http://127.0.0.1:8000", "http://localhost:8000"):
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        origin = self.headers.get("Origin", "")
        if origin not in ("http://127.0.0.1:8000", "http://localhost:8000"):
            return self._send(403, {"ok": False, "error": "Origin rejected."})
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            configured = bool(KEY)
            return self._send(200, {"ok": True, "service": "creative", "provider": "Agnes AI",
                                    "image_configured": configured, "video_configured": configured,
                                    "image_model": IMAGE_MODEL, "video_model": VIDEO_MODEL})
        match = re.fullmatch(r"/api/video/([A-Za-z0-9_-]{4,160})", urlsplit(self.path).path)
        if match:
            from urllib.parse import parse_qs
            query = parse_qs(urlsplit(self.path).query)
            model = query.get("model_name", [VIDEO_MODEL])[0]
            if model not in ALLOWED_VIDEO_MODELS:
                return self._send(400, {"ok": False, "error": "Unsupported Agnes video model."})
            try:
                params = urlencode({"video_id": match.group(1), "model_name": model})
                result = api_json(f"{API_ROOT}/agnesapi?{params}", method="GET", timeout=60)
                # Agnes 2.5 responses have used both top-level `url` and
                # `metadata.url`; accept both, plus common compatibility shapes.
                status = str(result.get("status", "")).strip().lower()
                metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
                data_block = result.get("data") if isinstance(result.get("data"), dict) else {}
                video_url = (result.get("url") or result.get("video_url") or
                             metadata.get("url") or data_block.get("url"))
                error = result.get("error") or result.get("message")
                return self._send(200, {"ok": True, "status": status or "queued",
                                        "video_url": video_url,
                                        "error": error, "provider": "Agnes AI"})
            except AgnesAPIError as exc:
                return self._send(exc.status_code, {"ok": False, "error": str(exc), "provider_status": exc.status_code})
            except Exception as exc:
                return self._send(502, {"ok": False, "error": str(exc)})
        return self._send(404, {"ok": False, "error": "Not found."})

    def do_POST(self):
        origin = self.headers.get("Origin", "")
        if origin not in ("http://127.0.0.1:8000", "http://localhost:8000", ""):
            return self._send(403, {"ok": False, "error": "Origin rejected."})
        try:
            data = read_json(self)
            if self.path == "/api/image":
                if not KEY:
                    return self._send(503, {"ok": False, "error": "Set AGNES_API_KEY in your local .env file to enable image generation."})
                prompt = str(data.get("prompt", "")).strip()
                if not prompt or len(prompt) > 4000:
                    return self._send(400, {"ok": False, "error": "Prompt must be 1–4000 characters."})
                ratio = data.get("aspect_ratio", "1:1")
                allowed_ratios = ("1:1", "16:9", "4:3", "3:2", "2:3", "3:4", "9:16", "21:9")
                if ratio not in allowed_ratios:
                    return self._send(400, {"ok": False, "error": "Unsupported aspect ratio."})
                if IMAGE_MODEL not in ALLOWED_IMAGE_MODELS:
                    return self._send(503, {"ok": False, "error": "Unsupported Agnes image model configured in .env."})
                size = str(data.get("size", "2K"))
                if size not in ("1K", "2K", "3K", "4K"):
                    return self._send(400, {"ok": False, "error": "Image size must be 1K, 2K, 3K, or 4K."})
                payload = {"model": IMAGE_MODEL, "prompt": prompt, "n": 1, "size": size,
                           "extra_body": {"ratio": ratio, "response_format": "url"}}
                result = api_json(f"{API_BASE}/images/generations", payload=payload, timeout=240)
                item = (result.get("data") or [{}])[0]
                if item.get("url"):
                    return self._send(200, {"ok": True, "image_url": item["url"], "provider": "Agnes AI", "model": IMAGE_MODEL})
                if item.get("b64_json"):
                    filename = f"image_{int(time.time())}_{os.getpid()}.png"
                    target = OUT / filename
                    target.write_bytes(base64.b64decode(item["b64_json"], validate=True))
                    return self._send(200, {"ok": True, "file": f"generated/{filename}", "provider": "Agnes AI", "model": IMAGE_MODEL})
                return self._send(502, {"ok": False, "error": "Agnes AI returned no image URL or image data."})

            if self.path == "/api/video":
                if not KEY:
                    return self._send(503, {"ok": False, "error": "Set AGNES_API_KEY in your local .env file to enable video generation."})
                prompt = str(data.get("prompt", "")).strip()
                if not prompt or len(prompt) > 4000:
                    return self._send(400, {"ok": False, "error": "Prompt must be 1–4000 characters."})
                model = str(data.get("model", VIDEO_MODEL))
                if model not in ALLOWED_VIDEO_MODELS:
                    return self._send(400, {"ok": False, "error": "Choose an available Agnes video model."})
                seconds = int(data.get("duration", 5))
                if seconds < 4 or seconds > 12:
                    return self._send(400, {"ok": False, "error": "Video duration must be between 4 and 12 seconds."})
                size = str(data.get("resolution", "720P"))
                allowed_sizes = ("720P",) if model == "agnes-video-2.5-flash" else ("720P", "1080P", "1K", "2K")
                if size not in allowed_sizes:
                    return self._send(400, {"ok": False, "error": f"{model} supports: {', '.join(allowed_sizes)}."})
                payload = {"model": model, "prompt": prompt, "mode": "text", "seconds": str(seconds),
                           "size": size, "aspect_ratio": str(data.get("aspect_ratio", "16:9")), "n": 1}
                if payload["aspect_ratio"] not in ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9"):
                    return self._send(400, {"ok": False, "error": "Unsupported video aspect ratio."})
                result = api_json(f"{API_BASE}/videos", payload=payload, timeout=90)
                # Current Agnes 2.5 returns video_id. Keep id/task_id fallbacks
                # for compatible gateway responses, but always poll by video_id.
                video_id = result.get("video_id") or result.get("id") or result.get("task_id")
                if not video_id:
                    return self._send(502, {"ok": False, "error": "Agnes AI did not return a video_id.",
                                            "response_fields": list(result.keys())[:20]})
                return self._send(202, {"ok": True, "video_id": str(video_id), "status": result.get("status", "queued"),
                                        "model": model, "provider": "Agnes AI"})

            if self.path == "/api/presentation":
                title = str(data.get("title", "ULTRON Presentation")).strip()[:120]
                slides = data.get("slides")
                if not isinstance(slides, list) or not slides or len(slides) > 20:
                    return self._send(400, {"ok": False, "error": "Provide 1–20 slides."})
                try:
                    from pptx import Presentation
                    from pptx.util import Pt
                except ImportError:
                    return self._send(503, {"ok": False, "error": "Install presentation support: pip install -r requirements-media.txt"})
                prs = Presentation()
                cover = prs.slides.add_slide(prs.slide_layouts[0])
                cover.shapes.title.text = title
                cover.placeholders[1].text = "Created locally by ULTRON"
                for entry in slides:
                    if not isinstance(entry, dict):
                        continue
                    heading = str(entry.get("title", "Key points")).strip()[:120]
                    bullets = entry.get("bullets", [])
                    if not isinstance(bullets, list):
                        bullets = [str(bullets)]
                    slide = prs.slides.add_slide(prs.slide_layouts[1])
                    slide.shapes.title.text = heading
                    frame = slide.placeholders[1].text_frame
                    frame.clear()
                    for idx, bullet in enumerate(bullets[:8]):
                        para = frame.paragraphs[0] if idx == 0 else frame.add_paragraph()
                        para.text = str(bullet)[:500]
                        para.level = 0
                        para.font.size = Pt(22)
                filename = f"presentation_{int(time.time())}_{os.getpid()}.pptx"
                target = OUT / filename
                prs.save(str(target))
                return self._send(200, {"ok": True, "file": f"generated/{filename}", "slides": len(prs.slides)})
            return self._send(404, {"ok": False, "error": "Not found."})
        except ValueError as exc:
            return self._send(400, {"ok": False, "error": str(exc)})
        except AgnesAPIError as exc:
            return self._send(exc.status_code, {"ok": False, "error": str(exc), "provider_status": exc.status_code})
        except Exception as exc:
            return self._send(502, {"ok": False, "error": str(exc)})

    def log_message(self, fmt, *args):
        print("[Creative] " + fmt % args)

if __name__ == "__main__":
    print(f"ULTRON Creative Services listening on http://{HOST}:{PORT}")
    if not KEY:
        print("AGNES_API_KEY is not set. Image/video generation will report unavailable.")
    print(f"Image model: {IMAGE_MODEL} | Video model: {VIDEO_MODEL}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
