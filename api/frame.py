# Vercel:  POST /api/frame  — grab full-res frame(s) from a YouTube video at timecodes.
#
# Request (POST JSON):
#   { "url": "https://youtu.be/ID", "t": 412 }                 # single
#   { "url": "https://youtu.be/ID", "ts": [354, 358, 372] }    # batch (one resolve, many seeks)
#   t / ts are seconds (numbers).
# Response:
#   { "ok": true, "frames": [ { "t": 354, "image_base64": "<jpeg b64>" }, ... ] }
#
# Needs YouTube reachable from Vercel's datacenter IP -> set YT_COOKIES_B64 (see _ytcore.py).
import os, sys, json
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ytcore import resolve_stream_url, grab_frames


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Build", "4")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
            url = data.get("url")
            if not url:
                return self._send(400, {"ok": False, "error": "missing 'url'"})
            ts = data.get("ts")
            if ts is None:
                ts = [data.get("t", 0)]
            stream_url = resolve_stream_url(url)
            frames = grab_frames(stream_url, ts)
            self._send(200, {"ok": True, "frames": frames})
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)[-500:]})
