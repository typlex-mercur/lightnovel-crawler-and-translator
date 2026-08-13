"""
serve.py – Simple HTTP server cho reader interface.
Chạy: python serve.py
Truy cập: http://localhost:8080
"""
import http.server
import os
import sys

PORT = int(os.environ.get("PORT", 8080))
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler không log mỗi request ra console."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        # CORS headers cho local dev
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

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
        print(f"  Nhấn Ctrl+C để dừng                           ")
        print(f"==================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[*] Đã dừng server.")
