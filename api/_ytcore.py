# ---------------------------------------------------------------------------
# Shared core for the carousel YouTube-link path. Imported by api/frame.py and
# api/captions.py. Underscore prefix => Vercel does NOT route this as an endpoint.
#
#   resolve_stream_url(url)        -> a single seekable video URL
#   grab_frames(stream_url, [t..]) -> JPEG bytes at each timecode (one resolve, many seeks)
#   fetch_captions(url, langs)     -> { language, kind, cues:[{t,text}] }
#       real caption track first (yt-dlp); OpenAI Whisper fallback for caption-less clips.
#
# ENV (all optional):
#   YT_COOKIES_B64  base64 of a logged-in YouTube cookies.txt (SAME var api/extract.py uses).
#                   This is what un-blocks YouTube on Vercel's datacenter IP. If it is already
#                   set for /api/extract, these endpoints inherit it automatically.
#   YT_COOKIES      raw (un-encoded) cookies.txt contents — fallback if _B64 is not set.
#   YT_PROXY        proxy URL for yt-dlp + ffmpeg (sticky residential session). Alternative to
#                   cookies on a datacenter IP; resolve IP must == frame-fetch IP.
#   OPENAI_API_KEY  enables the Whisper transcript fallback for caption-less clips.
#   OPENAI_TRANSCRIBE_MODEL  default "whisper-1".
# ---------------------------------------------------------------------------
import os, base64, subprocess, tempfile, re, urllib.request

# Prefer 720p mp4 (video-only DASH is fine — we only need stills); fall back to
# progressive 360p (itag 18), then to whatever single best format exists.
_FORMAT = "bestvideo[ext=mp4][height<=720]/best[ext=mp4][height<=720]/18/best"


def _proxy():
    return os.environ.get("YT_PROXY") or None


def _cookiefile(url=""):
    """Write the YouTube cookies to a temp file for yt-dlp. Accepts raw cookies.txt
    in YT_COOKIES (simplest — paste the file as-is); else base64 in YT_COOKIES_B64
    (the var api/extract.py uses). Raw wins so a fresh YT_COOKIES overrides a stale _B64."""
    raw = os.environ.get("YT_COOKIES", "")
    if not raw:
        b64 = os.environ.get("YT_COOKIES_B64", "")
        if b64:
            try:
                raw = base64.b64decode(b64).decode("utf-8")
            except Exception:
                raw = ""
    if not raw:
        return None
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as f:
        f.write(raw)
    return path


def _ydl_opts(extra=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        # With valid cookies the default web client is authenticated and most reliable.
        # (The old android-client trick now triggers "Requested format is not available".)
    }
    cf = _cookiefile()
    if cf:
        opts["cookiefile"] = cf
    px = _proxy()
    if px:
        opts["proxy"] = px
    if extra:
        opts.update(extra)
    return opts


def resolve_stream_url(video_url):
    """Resolve a YouTube page URL to one seekable media URL. Resolve + frame read
    must exit on the SAME IP (sticky proxy) or YouTube rejects the signed media URL."""
    import yt_dlp
    with yt_dlp.YoutubeDL(_ydl_opts({"format": _FORMAT})) as ydl:
        info = ydl.extract_info(video_url, download=False)
    if info.get("url"):
        return info["url"]
    reqs = info.get("requested_formats") or []
    if reqs:
        return reqs[0]["url"]
    raise RuntimeError("could not resolve a stream URL")


def _grab_one(ffmpeg, stream_url, t):
    # -ss BEFORE -i = fast seek via HTTP range (only bytes near t are fetched).
    cmd = [ffmpeg, "-y", "-ss", str(t), "-i", stream_url,
           "-frames:v", "1", "-q:v", "2", "-f", "image2", "pipe:1"]
    env = os.environ.copy()
    px = _proxy()
    if px:  # ffmpeg reads the http(s) input through these
        env["http_proxy"] = px
        env["https_proxy"] = px
    proc = subprocess.run(cmd, capture_output=True, timeout=45, env=env)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError("ffmpeg failed at t=%s: %s" % (t, proc.stderr.decode("utf-8", "ignore")[-300:]))
    return proc.stdout


def grab_frames(stream_url, ts):
    """Grab a JPEG at each timecode (seconds). One resolved URL, many seeks."""
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    return [{"t": t, "image_base64": base64.b64encode(_grab_one(ffmpeg, stream_url, t)).decode("ascii")} for t in ts]


# ---- captions ----------------------------------------------------------------

def _hms(s):
    s = s.replace(",", ".")
    h, m, rest = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


_TC = re.compile(r"(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3})")


def parse_vtt(text):
    """Parse a WEBVTT/SRT blob into [{t, text}], stripping tags + de-duping the
    rolling repeats that auto-captions produce."""
    text = text.replace("\r", "")
    cues = []
    for block in re.split(r"\n\n+", text):
        m = _TC.search(block)
        if not m:
            continue
        start = _hms(m.group(1))
        lines = block.split("\n")
        ti = next((i for i, l in enumerate(lines) if "-->" in l), 0)
        txt = " ".join(lines[ti + 1:])
        txt = re.sub(r"<[^>]+>", "", txt)      # strip <c>/<00:00:00.000> inline tags
        txt = re.sub(r"\[[^\]]*\]", "", txt)   # strip [Music] / [Applause]
        txt = re.sub(r"\s+", " ", txt).strip()
        if not txt:
            continue
        if cues and cues[-1]["text"] == txt:   # auto-captions repeat the prior line
            continue
        cues.append({"t": round(start, 2), "text": txt})
    return cues


def fetch_captions(video_url, preferred_langs=None):
    """Real caption track first (manual > auto, via yt-dlp). Falls back to OpenAI
    Whisper transcription when the video has no caption track at all."""
    import yt_dlp
    with yt_dlp.YoutubeDL(_ydl_opts()) as ydl:
        info = ydl.extract_info(video_url, download=False)

    def pick(tracks):
        if not tracks:
            return None, None
        langs = list(tracks.keys())
        chosen = None
        for want in (preferred_langs or []):
            for k in langs:
                if k == want or k.startswith(want):
                    chosen = k
                    break
            if chosen:
                break
        chosen = chosen or langs[0]
        fmts = tracks[chosen]
        vtt = next((f for f in fmts if f.get("ext") == "vtt"), None) or (fmts[0] if fmts else None)
        return chosen, (vtt.get("url") if vtt else None)

    lang, url = pick(info.get("subtitles"))
    kind = "manual"
    if not url:
        lang, url = pick(info.get("automatic_captions"))
        kind = "auto"
    if url:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        cues = parse_vtt(raw)
        if cues:
            return {"language": lang, "kind": kind, "cues": cues}
    return fetch_captions_whisper(video_url)


def fetch_captions_whisper(video_url):
    """Fallback for caption-less clips: download the audio (proxy/cookie-aware), downsample it,
    and transcribe with OpenAI Whisper. OpenAI can't read a YouTube URL directly, so we fetch the
    audio first. Needs OPENAI_API_KEY. Empty cues if unavailable.
    NOTE: on Vercel this path can exceed the function time limit for long clips; with cookies the
    real caption track above almost always wins, so this rarely fires."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return {"language": None, "kind": None, "cues": []}
    import yt_dlp, imageio_ffmpeg

    tmpdir = tempfile.mkdtemp()
    opts = _ydl_opts({"format": "bestaudio/best", "outtmpl": os.path.join(tmpdir, "audio.%(ext)s")})
    opts["skip_download"] = False
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([video_url])
    src = next((os.path.join(tmpdir, f) for f in os.listdir(tmpdir)), None)
    if not src:
        return {"language": None, "kind": "whisper", "cues": []}

    # mono 16 kHz 32 kbps mp3 keeps even a long podcast under the 25 MB transcription limit
    mp3 = os.path.join(tmpdir, "audio16.mp3")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ffmpeg, "-y", "-i", src, "-ac", "1", "-ar", "16000", "-b:a", "32k", mp3],
                   capture_output=True, timeout=300)

    from openai import OpenAI
    client = OpenAI(api_key=key)
    model = os.environ.get("OPENAI_TRANSCRIBE_MODEL", "whisper-1")
    with open(mp3, "rb") as f:
        tr = client.audio.transcriptions.create(model=model, file=f, response_format="verbose_json")

    segs = getattr(tr, "segments", None) or (tr.get("segments") if isinstance(tr, dict) else []) or []
    cues = []
    for s in segs:
        start = s.get("start") if isinstance(s, dict) else getattr(s, "start", 0)
        txt = (s.get("text") if isinstance(s, dict) else getattr(s, "text", "")) or ""
        txt = txt.strip()
        if txt:
            cues.append({"t": round(float(start), 2), "text": txt})
    lang = tr.get("language") if isinstance(tr, dict) else getattr(tr, "language", None)
    return {"language": lang, "kind": "whisper", "cues": cues}
