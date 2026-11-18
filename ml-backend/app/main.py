from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from contextlib import asynccontextmanager
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


def _warmup_predictor():
    try:
        from app.services.predictor import get_predictor
        p = get_predictor()
        logger.info('>>> ML Ensemble Models Fully Loaded & Online! <<<')
    except Exception as e:
        logger.error(f'Error during predictor warmup: {e}')


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info('Starting AI Trading Bot API...')
    init_db()
    # Start dashboard on port 3000
    t3000 = threading.Thread(target=_start_port_3000_server, daemon=True)
    t3000.start()
    # Warm up ML predictor models in background so port 8000 opens in <2 seconds!
    t_warmup = threading.Thread(target=_warmup_predictor, daemon=True)
    t_warmup.start()
    logger.info('API Server Live on http://localhost:8000 & Web Dashboard at http://localhost:8000/dashboard')
    yield
    # Shutdown (nothing to clean up)


app = FastAPI(
    title='AI Trading Signal Bot API',
    description='ML-powered trading signal generator for binary options with 35-day continuous learning',
    version='1.0.2',
    docs_url='/docs',
    redoc_url='/redoc',
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

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
