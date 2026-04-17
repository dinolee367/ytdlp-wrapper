from http.server import BaseHTTPRequestHandler
import json
import os
import base64
import tempfile
import yt_dlp

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        url = body.get('url', '')

        if not url:
            self.send_response(400)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'url is required'}).encode())
            return

        cookie_file_path = None
        try:
            ydl_opts = {'quiet': True, 'skip_download': True}

            # Use base64-encoded cookies from environment variable
            cookies_b64 = os.environ.get('FB_COOKIES_B64', '')
            if cookies_b64:
                cookie_content = base64.b64decode(cookies_b64).decode('utf-8')
                fd, cookie_file_path = tempfile.mkstemp(suffix='.txt')
                with os.fdopen(fd, 'w') as f:
                    f.write(cookie_content)
                ydl_opts['cookiefile'] = cookie_file_path

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            formats = info.get('formats') or []
            video_url = info.get('url') or (formats[-1].get('url') if formats else '')
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'video_url': video_url,
                'thumbnail_url': info.get('thumbnail', ''),
                'title': info.get('title', ''),
                'description': (info.get('description') or '')[:500],
                'duration': info.get('duration'),
                'view_count': info.get('view_count') or 0,
                'like_count': info.get('like_count') or 0,
                'comment_count': info.get('comment_count') or 0,
                'uploader': info.get('uploader', ''),
                'upload_date': info.get('upload_date', ''),
                'has_video': bool(video_url),
            }).encode())
        except Exception as e:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e), 'has_video': False}).encode())
        finally:
            if cookie_file_path and os.path.exists(cookie_file_path):
                os.unlink(cookie_file_path)
