"""
Python Web Dashboard Server (Port 3000)
Runs the full interactive AI Trading Bot Web Dashboard without requiring Node.js or npm.
Usage:
    python run_dashboard.py
"""

import os
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler

DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(DASHBOARD_DIR, 'standalone_dashboard.html')


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/', '/index.html', '/dashboard', '/history', '/backtest', '/model', '/settings', '/login'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            with open(HTML_FILE, 'rb') as f:
                self.wfile.write(f.read())
        else:
            super().do_GET()

    def log_message(self, format, *args):
        pass  # Keep console clean


def start_dashboard_server(port: int = 3000, open_browser: bool = False):
    os.chdir(DASHBOARD_DIR)
    server = HTTPServer(('0.0.0.0', port), DashboardHandler)
    print(f'==========================================================')
    print(f'  📈 AI Trading Web Dashboard running at: http://localhost:{port}')
    print(f'==========================================================')
    if open_browser:
        try:
            webbrowser.open(f'http://localhost:{port}')
        except Exception:
            pass
    server.serve_forever()


if __name__ == '__main__':
    start_dashboard_server(port=3000, open_browser=True)
