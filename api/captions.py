# Vercel:  POST /api/captions  — fetch a YouTube video's transcript as [{t,text}].
# Prefers a manual (creator) caption track; falls back to auto-captions; then to OpenAI
# Whisper for caption-less clips (needs OPENAI_API_KEY). Empty transcript => UI asks for upload.
#
# Request (POST JSON):  { "url": "https://youtu.be/ID", "langs": ["ms","en"] }   # langs optional
# Response:             { "ok": true, "language": "ms", "kind": "manual",
#                         "transcript": [ { "t": 12.5, "text": "..." }, ... ] }
import os, sys, json
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ytcore import fetch_captions


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
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
            res = fetch_captions(url, data.get("langs"))
            self._send(200, {
                "ok": True,
                "language": res["language"],
                "kind": res["kind"],
                "transcript": res["cues"],
            })
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)[-500:]})
