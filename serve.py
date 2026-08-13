"""
serve.py – Simple HTTP server cho reader interface.
Chạy: python serve.py
Truy cập: http://localhost:8080
"""
import http.server
import os
import sys
import json
import asyncio
import io

PORT = int(os.environ.get("PORT", 8080))
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

try:
    import edge_tts
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    print("[!] edge-tts chưa cài. Chạy: pip install edge-tts")
    print("[!] Chức năng đọc truyện sẽ không hoạt động.")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler không log mỗi request ra console."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        # CORS headers cho local dev
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/tts":
            self._handle_tts()
        else:
            self.send_error(404)

    def _handle_tts(self):
        if not TTS_AVAILABLE:
            self.send_error(503, "edge-tts not installed. Run: pip install edge-tts")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            self.send_error(400, "Invalid JSON")
            return

        text = data.get("text", "").strip()
        if not text:
            self.send_error(400, "Empty text")
            return

        voice = data.get("voice", "vi-VN-HoaiMyNeural")
        rate = data.get("rate", "+0%")

        try:
            audio_bytes = asyncio.run(self._generate_tts(text, voice, rate))
        except Exception as e:
            self.send_error(500, f"TTS error: {e}")
            return

        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio_bytes)))
        self.end_headers()
        self.wfile.write(audio_bytes)

    async def _generate_tts(self, text, voice, rate):
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()

    def log_message(self, format, *args):
        # Chỉ log errors
        if args and "404" in str(args):
            super().log_message(format, *args)


if __name__ == "__main__":
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.chdir(DIRECTORY)
    with http.server.ThreadingHTTPServer(("", PORT), QuietHandler) as httpd:
        print(f"==================================================")
        print(f"  Light Novel Reader đang chạy!                 ")
        print(f"  -> http://localhost:{PORT}                       ")
        tts_msg = "✓ Edge TTS sẵn sàng" if TTS_AVAILABLE else "✗ Chưa cài (pip install edge-tts)"
        print(f"  TTS: {tts_msg}")
        print(f"  Nhấn Ctrl+C để dừng                           ")
        print(f"==================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[*] Đã dừng server.")
