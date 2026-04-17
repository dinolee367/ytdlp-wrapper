from http.server import BaseHTTPRequestHandler
import json
import os
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

        try:
            ydl_opts = {'quiet': True, 'skip_download': True}

            # Use cookies from environment variable if available
            cookie_file = None
            cookies_env = os.environ.get('FB_COOKIES', '')
            if cookies_env:
                cookie_file = tempfile.NamedTemporaryFile(
                    mode='w', suffix='.txt', delete=False
                )
                cookie_file.write(cookies_env)
                cookie_file.close()
                ydl_opts['cookiefile'] = cookie_file.name

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            # Clean up temp cookie file
            if cookie_file:
                os.unlink(cookie_file.name)

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
            # Clean up temp cookie file on error
            if 'cookie_file' in locals() and cookie_file:
                try:
                    os.unlink(cookie_file.name)
                except:
                    pass
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e), 'has_video': False}).encode())
