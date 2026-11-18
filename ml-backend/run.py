"""
Unified Quick-Start Launcher for AI Trading Signal Bot
Starts BOTH:
  1. FastAPI ML Backend Server on http://localhost:8000
  2. Interactive Web Dashboard on http://localhost:3000 (and http://localhost:8000/dashboard)
No Node.js or npm installation required!
"""

import os
import sys
import threading
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
        print('============================================================')
        print('  [*] Web Dashboard Live at : http://localhost:3000')
        print('  [*] ML Backend API Live at: http://localhost:8000')
        print('  [*] Swagger API Docs at   : http://localhost:8000/docs')
        print('============================================================')
        server.serve_forever()
    except OSError:
        print('  [i] Port 3000 already in use; Dashboard also available at http://localhost:8000/dashboard')


import time
import subprocess


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
                        print(f'[*] Freeing occupied port {port} (PID {pid})...')
                        subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                        killed = True
        except Exception:
            pass
    if killed:
        time.sleep(1.2)


if __name__ == '__main__':
    free_ports(8000, 3000)

    uvicorn.run(
        'app.main:app',
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level='debug' if settings.DEBUG else 'info'
    )
