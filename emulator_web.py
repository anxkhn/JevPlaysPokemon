"""Loopback dashboard server. ROM and credentials are never served."""
import json
import mimetypes
import re
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "emulator-data"


def serve(session, port):
    from modules.pokemon import _species_by_index, _moves_by_index, _natures_by_index
    from modules.items import _items_by_index
    from emulator import validate_config

    catalog = {
        "species": [{"name": p.name, "id": p.national_dex_number, "abilities": [a.name for a in p.abilities]}
            for p in _species_by_index if 1 <= p.national_dex_number <= 386],
        "moves": [m.name for m in _moves_by_index if m.index],
        "natures": [n.name for n in _natures_by_index],
        "items": [i.name for i in _items_by_index if i.index],
    }
    (DATA / "sprites").mkdir(exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, data, content_type="application/json", status=200):
            if not isinstance(data, bytes):
                data = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                return self.respond((ROOT / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/api/status":
                return self.respond({**session.status, "paused": session.paused.is_set()})
            if path == "/api/config":
                return self.respond(json.loads((ROOT / "emulator-config.json").read_text()))
            if path == "/api/catalog":
                return self.respond(catalog)
            if path == "/frame.jpg":
                return self.respond(session.jpeg, "image/png" if session.jpeg.startswith(b"\x89PNG") else "image/jpeg")
            if path == "/api/recordings":
                records = []
                for file in sorted((DATA / "recordings").glob("*/summary.json"), reverse=True):
                    summary = json.loads(file.read_text())
                    if (file.parent / "replay.mp4").exists():
                        records.append({"id": file.parent.name, "summary": {k: v for k, v in summary.items() if k not in ("battle", "last_decision")}})
                return self.respond(records)
            if match := re.fullmatch(r"/sprites/(\d{1,3})\.png", path):
                number = int(match[1])
                if not 1 <= number <= 386:
                    return self.respond({"error": "Unknown species"}, status=404)
                target = DATA / "sprites" / f"{number}.png"
                if not target.exists():
                    try:
                        url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{number}.png"
                        with urllib.request.urlopen(url, timeout=10) as response:
                            target.write_bytes(response.read())
                    except Exception:
                        return self.respond({"error": "Sprite unavailable"}, status=404)
                return self.respond(target.read_bytes(), "image/png")
            if match := re.fullmatch(r"/recordings/([0-9-]+)/(replay\.mp4|decisions\.jsonl|summary\.json|config\.json)", path):
                file = DATA / "recordings" / match[1] / match[2]
                if not file.is_file():
                    return self.respond({"error": "Recording not found"}, status=404)
                size = file.stat().st_size
                start, end = 0, size - 1
                partial = self.headers.get("Range")
                if partial:
                    range_match = re.fullmatch(r"bytes=(\d+)-(\d*)", partial)
                    if not range_match:
                        return self.respond({"error": "Invalid range"}, status=416)
                    start = int(range_match[1])
                    end = min(int(range_match[2]), end) if range_match[2] else end
                    if start > end:
                        return self.respond({"error": "Range exceeds file"}, status=416)
                self.send_response(206 if partial else 200)
                self.send_header("Content-Type", mimetypes.guess_type(str(file))[0] or "application/octet-stream")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start + 1))
                if partial:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                try:
                    with file.open("rb") as stream:
                        stream.seek(start)
                        remaining = end - start + 1
                        while remaining:
                            chunk = stream.read(min(65536, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            self.respond({"error": "Not found"}, status=404)

        def do_POST(self):
            origin = self.headers.get("Origin")
            if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return self.respond({"error": "Invalid origin"}, status=403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 65536:
                    raise ValueError("Request too large")
                data = json.loads(self.rfile.read(length)) if length else {}
                path = urlparse(self.path).path
                if path == "/api/start":
                    session.start(data)
                elif path == "/api/stop":
                    session.stop.set()
                elif path == "/api/pause":
                    if session.paused.is_set():
                        session.paused.clear()
                    else:
                        session.paused.set()
                elif path == "/api/config":
                    validate_config(data)
                    temporary = ROOT / "emulator-config.json.tmp"
                    temporary.write_text(json.dumps(data, indent=2) + "\n")
                    temporary.replace(ROOT / "emulator-config.json")
                else:
                    return self.respond({"error": "Not found"}, status=404)
                self.respond({"ok": True, "paused": session.paused.is_set()})
            except (ValueError, KeyError, TypeError, OSError) as error:
                self.respond({"error": str(error)}, status=400)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Dashboard ready at http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        session.stop.set()
        if session.thread:
            session.thread.join(timeout=50)
    finally:
        server.server_close()
