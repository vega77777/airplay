"""
飛出台灣 — 本地伺服器（簡化版）
使用：python server.py  或  python3 server.py
開啟：http://localhost:8888
"""
import http.server, socketserver, webbrowser, threading, os, sys

PORT = 8888
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()
    def log_message(self, fmt, *args): pass  # 靜音日誌

print(f"伺服器啟動中... http://localhost:{PORT}")
httpd = socketserver.TCPServer(("", PORT), Handler)
threading.Timer(0.8, lambda: webbrowser.open(f'http://localhost:{PORT}')).start()
print("按 Ctrl+C 停止")
try:
    httpd.serve_forever()
except KeyboardInterrupt:
    print("已停止")
