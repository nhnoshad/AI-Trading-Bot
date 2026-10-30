from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
import logging
import os
import sys
from app.core.config import settings
from app.core.database import init_db
from app.api.routes import router

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title='AI Trading Signal Bot API',
    description='ML-powered trading signal generator for binary options with 35-day continuous learning',
    version='1.0.1',
    docs_url='/docs',
    redoc_url='/redoc'
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

DASHBOARD_HTML_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../web-dashboard/standalone_dashboard.html')
)


class _Port3000DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if os.path.exists(DASHBOARD_HTML_PATH):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            with open(DASHBOARD_HTML_PATH, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def _start_port_3000_server():
    try:
        httpd = HTTPServer(('0.0.0.0', 3000), _Port3000DashboardHandler)
        logger.info('Web Dashboard running at http://localhost:3000')
        httpd.serve_forever()
    except OSError:
        logger.info('Port 3000 already in use; dashboard also available at http://localhost:8000/dashboard')


@app.on_event('startup')
async def startup_event():
    logger.info('Starting AI Trading Bot API...')
    init_db()
    from app.services.predictor import get_predictor
    get_predictor()

    # Start dashboard on port 3000
    t = threading.Thread(target=_start_port_3000_server, daemon=True)
    t.start()
    logger.info('API and Web Dashboard ready.')


app.include_router(router, prefix='/api')

@app.get('/dashboard', response_class=HTMLResponse)
async def serve_dashboard():
    if os.path.exists(DASHBOARD_HTML_PATH):
        return FileResponse(DASHBOARD_HTML_PATH, media_type='text/html')
    return HTMLResponse('<h1>Dashboard file not found</h1>', status_code=404)

@app.get('/')
async def root():
    return {
        'message': 'AI Trading Signal Bot API',
        'dashboard_url': 'http://localhost:3000',
        'builtin_dashboard': 'http://localhost:8000/dashboard',
        'docs': 'http://localhost:8000/docs',
        'version': '1.0.1'
    }
