"""
Continuous Learning Pipeline
============================
- Loads new trade results from the database
- Collects recent OHLCV data via yfinance
- Retrains the ensemble model if enough new data exists
- Evaluates new model vs old model
- Deploys new model only if accuracy improves
- Retains 30-day rolling history of live trade data

Schedule: Run weekly (or trigger via /api/retrain)
Usage:    python scripts/training/continuous_learning.py
"""

import os
import sys
import json
import joblib
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sklearn.metrics import accuracy_score
from sklearn.preprocessing import StandardScaler

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from app.core.config import settings
from app.services.indicators import calculate_indicators, FEATURE_COLUMNS
from scripts.data.download_data import download_yfinance, create_labels
from scripts.training.train_model import train_models

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join(os.path.dirname(__file__), '../../models')
DATA_DIR = os.path.join(os.path.dirname(__file__), '../../data')
LIVE_DATA_PATH = os.path.join(DATA_DIR, 'live_trade_history.csv')
META_PATH = os.path.join(MODELS_DIR, 'model_meta.json')

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)


# ── Load current model metadata ────────────────────────────────────────────────

def load_meta() -> dict:
    if os.path.exists(META_PATH):
        with open(META_PATH) as f:
            return json.load(f)
    return {'accuracy': 0.0, 'version': '0.0.0', 'trained_at': None}


def save_meta(meta: dict):
    with open(META_PATH, 'w') as f:
        json.dump(meta, f, indent=2)


# ── Collect fresh market data (last 30 days, 1-minute) ─────────────────────────

def collect_fresh_data(pairs: list = None, interval: str = '1m') -> pd.DataFrame:
    if pairs is None:
        pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD']

    frames = []
    for pair in pairs:
        logger.info(f'Collecting fresh data for {pair} ({interval})...')
        # yfinance max for 1m is 7 days; use 5m for 30 days
        period = '7d' if interval == '1m' else '60d'
        df = download_yfinance(pair, interval, period)
        if not df.empty:
            df['pair'] = pair
            df = create_labels(df)
            frames.append(df)

    if not frames:
        logger.warning('No fresh data collected.')
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    logger.info(f'Collected {len(combined)} fresh candles from {len(frames)} pairs')
    return combined


# ── Merge with existing live history (rolling 30-day window) ───────────────────

def merge_with_live_history(fresh_df: pd.DataFrame) -> pd.DataFrame:
    if os.path.exists(LIVE_DATA_PATH):
        existing = pd.read_csv(LIVE_DATA_PATH)
        logger.info(f'Existing live history: {len(existing)} rows')
        combined = pd.concat([existing, fresh_df], ignore_index=True)
    else:
        combined = fresh_df

    # Keep only last 30 days
    cutoff = datetime.now() - timedelta(days=30)
    if 'timestamp' in combined.columns:
        combined['timestamp'] = pd.to_datetime(combined['timestamp'], errors='coerce')
        combined = combined[combined['timestamp'] >= cutoff]

    combined.drop_duplicates(subset=['timestamp', 'pair'] if 'pair' in combined.columns else ['timestamp'],
                             keep='last', inplace=True)
    combined.reset_index(drop=True, inplace=True)

    # Persist updated history
    combined.to_csv(LIVE_DATA_PATH, index=False)
    logger.info(f'Live history saved: {len(combined)} rows (30-day window)')
    return combined


# ── Feature engineering ────────────────────────────────────────────────────────

def engineer_features(df: pd.DataFrame):
    logger.info('Engineering features...')
    try:
        df_features = calculate_indicators(df.to_dict('records'))
    except Exception as e:
        logger.error(f'Feature engineering failed: {e}')
        return None, None, None

    if 'label' not in df.columns:
        df['label'] = (df['close'].shift(-1) > df['close']).astype(int)

    df_features['label'] = df['label'].values[:len(df_features)]
    df_features.dropna(inplace=True)

    available = [f for f in FEATURE_COLUMNS if f in df_features.columns]
    X = df_features[available].values
    y = df_features['label'].values
    return X, y, available


# ── Evaluate existing model ─────────────────────────────────────────────────────

def evaluate_existing_model(X_test, y_test) -> float:
    model_path = os.path.join(MODELS_DIR, 'ensemble_model.pkl')
    scaler_path = os.path.join(MODELS_DIR, 'scaler.pkl')
    if not (os.path.exists(model_path) and os.path.exists(scaler_path)):
        return 0.0
    try:
        model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)
        X_scaled = scaler.transform(X_test)
        y_pred = model.predict(X_scaled)
        acc = accuracy_score(y_test, y_pred)
        logger.info(f'Existing model accuracy on new data: {acc:.4f}')
        return acc
    except Exception as e:
        logger.error(f'Existing model evaluation failed: {e}')
        return 0.0


# ── Retrain and deploy if improved ─────────────────────────────────────────────

def retrain_and_deploy(X, y) -> dict:
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    logger.info('Training new models...')
    new_ensemble, *other_models = train_models(X_train_s, y_train)
    new_acc = accuracy_score(y_test, new_ensemble.predict(X_test_s))
    logger.info(f'New ensemble accuracy: {new_acc:.4f}')

    old_acc = evaluate_existing_model(X_test, y_test)
    meta = load_meta()

    result = {
        'new_accuracy': new_acc,
        'old_accuracy': old_acc,
        'deployed': False,
        'timestamp': datetime.utcnow().isoformat()
    }

    min_thresh = settings.MIN_ACCURACY_THRESHOLD
    if new_acc >= old_acc and new_acc >= min_thresh:
        # Deploy new model
        joblib.dump(new_ensemble, os.path.join(MODELS_DIR, 'ensemble_model.pkl'))
        joblib.dump(scaler, os.path.join(MODELS_DIR, 'scaler.pkl'))

        # Bump version
        parts = meta.get('version', '1.0.0').split('.')
        parts[-1] = str(int(parts[-1]) + 1)
        new_version = '.'.join(parts)

        new_meta = {
            'version': new_version,
            'trained_at': datetime.utcnow().isoformat(),
            'accuracy': new_acc,
            'n_samples': len(X),
            'retrain_reason': 'continuous_learning',
            'old_accuracy': old_acc
        }
        save_meta(new_meta)
        result['deployed'] = True
        result['version'] = new_version
        logger.info(f'✅ New model deployed! v{new_version} (accuracy: {new_acc:.4f})')
    else:
        logger.warning(
            f'⚠️ New model NOT deployed. New acc={new_acc:.4f}, Old acc={old_acc:.4f}, '
            f'Min threshold={min_thresh}'
        )

    return result


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run_continuous_learning(pairs=None, interval='1m', min_samples=500):
    logger.info('=' * 60)
    logger.info('CONTINUOUS LEARNING PIPELINE STARTED')
    logger.info('=' * 60)

    # Step 1: Collect fresh data
    fresh_df = collect_fresh_data(pairs, interval)
    if fresh_df.empty:
        logger.error('No data collected. Aborting.')
        return {'status': 'error', 'reason': 'no_data'}

    # Step 2: Merge with rolling 30-day history
    full_df = merge_with_live_history(fresh_df)

    if len(full_df) < min_samples:
        logger.warning(f'Not enough data ({len(full_df)} < {min_samples}). Skipping retrain.')
        return {'status': 'skipped', 'reason': 'insufficient_data', 'samples': len(full_df)}

    # Step 3: Feature engineering
    X, y, features = engineer_features(full_df)
    if X is None:
        return {'status': 'error', 'reason': 'feature_engineering_failed'}

    logger.info(f'Training set: {len(X)} samples, {len(features)} features')

    # Step 4: Retrain + deploy if better
    result = retrain_and_deploy(X, y)

    logger.info('CONTINUOUS LEARNING PIPELINE COMPLETE')
    logger.info(f'Result: {json.dumps(result, indent=2)}')

    # Reload predictor if running in server context
    try:
        from app.services.predictor import get_predictor
        get_predictor().reload_models()
        logger.info('Predictor reloaded with new model.')
    except Exception:
        pass

    return result


if __name__ == '__main__':
    result = run_continuous_learning()
    print(json.dumps(result, indent=2))
