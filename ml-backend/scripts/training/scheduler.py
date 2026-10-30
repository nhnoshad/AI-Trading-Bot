"""
Automated Retraining Scheduler
================================
Uses APScheduler to run the continuous learning pipeline every 7 days.
Can be run as a standalone process alongside the FastAPI server,
or triggered manually via POST /api/retrain.

Usage:
    python scripts/training/scheduler.py
"""

import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime

from app.core.config import settings
from scripts.training.continuous_learning import run_continuous_learning

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

scheduler = BlockingScheduler(timezone='UTC')


def scheduled_retrain():
    logger.info(f'[Scheduler] Starting weekly retrain at {datetime.utcnow().isoformat()}')
    result = run_continuous_learning(
        pairs=['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD'],
        interval='5m',
        min_samples=300
    )
    logger.info(f'[Scheduler] Retrain result: {result}')


@scheduler.scheduled_job(
    trigger=IntervalTrigger(days=settings.RETRAIN_INTERVAL_DAYS),
    id='weekly_retrain',
    name='Weekly Model Retraining',
    replace_existing=True
)
def weekly_retrain_job():
    scheduled_retrain()


if __name__ == '__main__':
    logger.info(f'Retraining scheduler started. Interval: every {settings.RETRAIN_INTERVAL_DAYS} day(s)')
    logger.info('Running initial retrain on startup...')
    try:
        scheduled_retrain()
    except Exception as e:
        logger.warning(f'Initial retrain failed (may not have data yet): {e}')

    logger.info('Scheduler is running...')
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info('Scheduler stopped.')
