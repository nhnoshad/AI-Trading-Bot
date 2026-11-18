"""
Unified Quick-Start Launcher for AI Trading Signal Bot
Starts BOTH:
  1. FastAPI ML Backend Server on http://localhost:8000
  2. Interactive Web Dashboard on http://localhost:8000/dashboard (and http://localhost:3000)
No Node.js or npm installation required!
"""

import os
import sys
import threading
import time
import subprocess
import webbrowser
import uvicorn
from http.server import HTTPServer, SimpleHTTPRequestHandler
from app.core.config import settings

DASHBOARD_HTML = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../web-dashboard/standalone_dashboard.html')
)


class _DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if os.path.exists(DASHBOARD_HTML):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            with open(DASHBOARD_HTML, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def _start_port_3000_dashboard():
    try:
        server = HTTPServer(('0.0.0.0', 3000), _DashboardHandler)
        server.serve_forever()
    except OSError:
        pass


def free_ports(*ports):
    """Automatically terminates any existing zombie or orphan process holding ports 8000 or 3000."""
    current_pid = os.getpid()
    killed = False
    for port in ports:
        try:
            output = subprocess.check_output(f'netstat -ano | findstr :{port}', shell=True).decode()
            for line in output.splitlines():
                if 'LISTENING' in line:
                    parts = line.strip().split()
                    pid = int(parts[-1])
                    if pid != current_pid and pid > 0:
                        print(f'[*] Freeing occupied port {port} (PID {pid})...', flush=True)
                        subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                        killed = True
        except Exception:
            pass
    if killed:
        time.sleep(1.0)


def _auto_open_browser():
    """Waits for server to start, then automatically opens the dashboard in the default browser."""
    time.sleep(2.0)
    try:
        webbrowser.open('http://localhost:8000/dashboard')
    except Exception:
        pass


if __name__ == '__main__':
    free_ports(8000, 3000)

    print('============================================================', flush=True)
    print('  [*] Starting AI Trading Bot ML Backend Server...', flush=True)
    print('  [*] ML Backend API : http://localhost:8000', flush=True)
    print('  [*] Web Dashboard  : http://localhost:8000/dashboard', flush=True)
    print('  [*] Swagger Docs   : http://localhost:8000/docs', flush=True)
    print('  [*] Opening Dashboard in your browser...', flush=True)
    print('============================================================', flush=True)

    threading.Thread(target=_auto_open_browser, daemon=True).start()

    uvicorn.run(
        'app.main:app',
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level='info'
    )
