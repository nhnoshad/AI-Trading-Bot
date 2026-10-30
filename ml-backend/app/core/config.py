from pydantic_settings import BaseSettings
from typing import Optional
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, 'trading_bot.db').replace('\\', '/')

class Settings(BaseSettings):
    # Server
    HOST: str = '0.0.0.0'
    PORT: int = 8000
    DEBUG: bool = False
    SECRET_KEY: str = 'dev-secret-key-change-in-production'
    ALLOWED_ORIGINS: list = ['*']

    # Database
    DATABASE_URL: str = f'sqlite:///{DEFAULT_DB_PATH}'
    REDIS_URL: str = 'redis://localhost:6379'

    # ML Model
    MODEL_PATH: str = 'models/ensemble_model.pkl'
    SCALER_PATH: str = 'models/scaler.pkl'
    LABEL_ENCODER_PATH: str = 'models/label_encoder.pkl'
    MODEL_VERSION: str = '1.0.0'
    CONFIDENCE_THRESHOLD: float = 0.65

    # Trading Safety
    MAX_TRADES_PER_HOUR: int = 10
    MAX_CONSECUTIVE_LOSSES: int = 3
    DAILY_LOSS_LIMIT: float = 50.0
    DAILY_PROFIT_TARGET: float = 100.0
    COOLDOWN_SECONDS: int = 30
    DEFAULT_TRADE_AMOUNT: float = 10.0

    # Data
    ALPHA_VANTAGE_API_KEY: str = ''
    DATA_REFRESH_INTERVAL: int = 300

    # Retraining
    RETRAIN_INTERVAL_DAYS: int = 7
    MIN_ACCURACY_THRESHOLD: float = 0.52

    class Config:
        env_file = '.env'
        case_sensitive = True

settings = Settings()
