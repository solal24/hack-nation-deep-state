"""Live API for the app: any address -> the same answer the pipeline gives (pipeline.answer.answer).

No new dependency (standard library server). No LLM call, no key needed: geocoding (Census) + public parcel
data + the deterministic engine on outputs/rules.json.

  GET /health                                   -> {"ok": true, "rules": 88, ...}
  GET /answer?q=<address or A0001>&as_of=YYYY-MM-DD[&year_built=1965][&units=6]
        -> answer() as JSON: status "ok" (address, verdicts, whats_coming, warnings) or "out_of_scope"
           (reason + message). Errors come back as {"status": "error", "message": ...} with HTTP 200 so the
           app can always show something and fall back to its own engine.

Run:  python -m pipeline.api            (PORT env var, default 8000)
"""
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from pipeline import engine
from pipeline.answer import answer

STARTED = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
LOCK = threading.Lock()   # answer() writes a small cache/CSV: one lookup at a time keeps the files consistent
CACHE = {}                # (q, as_of, year_built, units) -> response, for repeated demo lookups


def _int(v):
    return int(v) if v and re.fullmatch(r"\d{1,4}", v) else None


def handle_answer(params):
    q = (params.get("q") or [""])[0].strip()
    as_of = (params.get("as_of") or [engine.DEFAULT_AS_OF])[0]
    if not q:
        return {"status": "error", "message": "Missing q (an address, or a sample id like A0001)."}
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        return {"status": "error", "message": "as_of must be YYYY-MM-DD."}
    year, units = _int((params.get("year_built") or [""])[0]), _int((params.get("units") or [""])[0])
    key = (q.lower(), as_of, year, units)
    if key not in CACHE:
        with LOCK:
            CACHE[key] = answer(q, as_of, year, units)
    return CACHE[key]


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send({})

    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path in ("/", "/health"):
                self._send({"ok": True, "started": STARTED, "rules": len(engine.load_rules()),
                            "default_as_of": engine.DEFAULT_AS_OF, "disclaimer": engine.DISCLAIMER})
            elif url.path == "/answer":
                self._send(handle_answer(parse_qs(url.query)))
            else:
                self._send({"status": "error", "message": "Unknown path. Use /health or /answer?q=..."}, 404)
        except Exception as e:  # never crash the demo: the app falls back to its own engine
            self._send({"status": "error", "message": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}", flush=True)


def main():
    port = int(os.environ.get("PORT", "8000"))
    print(f"Covenant API on :{port} · {len(engine.load_rules())} rules", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
