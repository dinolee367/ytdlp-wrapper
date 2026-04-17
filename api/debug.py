from http.server import BaseHTTPRequestHandler
import json
import os
import base64

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        yt = os.environ.get('YT_COOKIES_B64', '')
        fb = os.environ.get('FB_COOKIES_B64', '')

        # Decode first 50 chars to verify format (don't expose full cookies)
        yt_preview = ''
        if yt:
            try:
                decoded = base64.b64decode(yt).decode('utf-8')
                yt_preview = decoded[:80] + '...'
            except:
                yt_preview = 'DECODE_ERROR'

        fb_preview = ''
        if fb:
            try:
                decoded = base64.b64decode(fb).decode('utf-8')
                fb_preview = decoded[:80] + '...'
            except:
                fb_preview = 'DECODE_ERROR'

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            'YT_COOKIES_B64': f'SET ({len(yt)} chars)' if yt else 'NOT SET',
            'FB_COOKIES_B64': f'SET ({len(fb)} chars)' if fb else 'NOT SET',
            'yt_preview': yt_preview,
            'fb_preview': fb_preview,
        }).encode())
