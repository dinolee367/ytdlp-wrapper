from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

@app.route('/api/extract', methods=['POST'])
def extract():
    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'url is required'}), 400
    try:
        ydl_opts = {'quiet': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        formats = info.get('formats') or []
        video_url = info.get('url') or (formats[-1].get('url') if formats else '')
        return jsonify({
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
        })
    except Exception as e:
        return jsonify({'error': str(e), 'has_video': False}), 200

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})
