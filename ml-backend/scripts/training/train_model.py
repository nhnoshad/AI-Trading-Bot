"""
ML Model Training Script
Trains XGBoost, LightGBM, and Random Forest models on OHLCV data.
Saves the best ensemble model to disk.
Usage: python scripts/training/train_model.py --data data/EURUSD_1m_yfinance.csv
"""
import os
import sys
import argparse
import json
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
try:
    from catboost import CatBoostClassifier
    CATBOOST_AVAILABLE = True
except ImportError:
    CATBOOST_AVAILABLE = False
import warnings
warnings.filterwarnings('ignore')

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from app.services.indicators import calculate_indicators, FEATURE_COLUMNS

MODELS_DIR = os.path.join(os.path.dirname(__file__), '../../models')
os.makedirs(MODELS_DIR, exist_ok=True)


def load_and_process_data(csv_path: str) -> tuple:
    print(f'Loading data from {csv_path}...')
    df = pd.read_csv(csv_path)
    print(f'Raw rows: {len(df)}')

    # Check if indicators are already pre-calculated in the dataset
    has_features = all(f in df.columns for f in FEATURE_COLUMNS)
    if has_features:
        print('Using pre-calculated technical indicator features from dataset...')
        df_features = df.copy()
    else:
        # Calculate indicators from raw OHLCV
        print('Calculating technical indicators from OHLCV candles...')
        df_features = calculate_indicators(df.to_dict('records'))

    # Label column
    if 'label' not in df_features.columns:
        if 'label' in df.columns:
            df_features['label'] = df['label'].values[:len(df_features)]
        elif 'close' in df_features.columns:
            df_features['label'] = (df_features['close'].shift(-1) > df_features['close']).astype(int)
        else:
            raise ValueError("No 'label' or 'close' column available to compute targets")

    df_features.dropna(subset=['label'], inplace=True)

    # Features and target
    available_features = [f for f in FEATURE_COLUMNS if f in df_features.columns]
    X = df_features[available_features].values
    y = df_features['label'].values.astype(int)

    print(f'Features: {len(available_features)}, Samples: {len(X)}')
    print(f'Label distribution: BUY={int(y.sum())}, SELL={int((1-y).sum())}')
    return X, y, available_features


def train_models(X_train, y_train):
    print('\nTraining XGBoost...')
    xgb = XGBClassifier(
        n_estimators=300, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
        gamma=0.1, reg_alpha=0.1, reg_lambda=1.0,
        scale_pos_weight=1, random_state=42,
        eval_metric='logloss', verbosity=0
    )
    xgb.fit(X_train, y_train)

    print('Training LightGBM...')
    lgbm = LGBMClassifier(
        n_estimators=300, max_depth=6, learning_rate=0.05,
        num_leaves=31, subsample=0.8, colsample_bytree=0.8,
        min_child_samples=20, reg_alpha=0.1, reg_lambda=0.1,
        random_state=42, verbosity=-1
    )
    lgbm.fit(X_train, y_train)

    cb = None
    if CATBOOST_AVAILABLE:
        print('Training CatBoost...')
        cb = CatBoostClassifier(
            iterations=300, depth=6, learning_rate=0.05,
            verbose=0, random_seed=42
        )
        cb.fit(X_train, y_train)

    print('Training Random Forest...')
    rf = RandomForestClassifier(
        n_estimators=300, max_depth=10, min_samples_split=10,
        min_samples_leaf=5, max_features='sqrt',
        class_weight='balanced', random_state=42, n_jobs=-1
    )
    rf.fit(X_train, y_train)

    print('Building Ensemble (Voting Classifier)...')
    if cb is not None:
        estimators = [('xgb', xgb), ('lgbm', lgbm), ('cb', cb), ('rf', rf)]
        weights = [0.30, 0.25, 0.25, 0.20]
    else:
        estimators = [('xgb', xgb), ('lgbm', lgbm), ('rf', rf)]
        weights = [0.40, 0.35, 0.25]

    ensemble = VotingClassifier(
        estimators=estimators,
        voting='soft',
        weights=weights
    )
    ensemble.fit(X_train, y_train)

    return ensemble, xgb, lgbm, cb, rf


def evaluate_model(model, X_test, y_test, model_name='Ensemble'):
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]
    acc = accuracy_score(y_test, y_pred)
    print(f'\n{model_name} Test Accuracy: {acc:.4f} ({acc*100:.2f}%)')
    print(classification_report(y_test, y_pred, target_names=['SELL', 'BUY']))
    return acc


def main():
    default_data = os.path.join(os.path.dirname(__file__), '../../data/rolling_30d_learning_memory.csv')
    if not os.path.exists(default_data):
        default_data = 'data/EURUSD_1m_yfinance.csv'

    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default=default_data)
    args = parser.parse_args()

    if not os.path.exists(args.data):
        print(f'Data file not found: {args.data}')
        print('Run: python scripts/data/download_data.py first')
        sys.exit(1)

    X, y, features = load_and_process_data(args.data)

    # Time-series split (no shuffle!)
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    print(f'Train: {len(X_train)}, Test: {len(X_test)}')

    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train
    ensemble, xgb, lgbm, cb, rf = train_models(X_train_scaled, y_train)

    # Evaluate each model
    eval_list = [('XGBoost', xgb), ('LightGBM', lgbm)]
    if cb is not None:
        eval_list.append(('CatBoost', cb))
    eval_list.extend([('Random Forest', rf), ('Ensemble', ensemble)])

    for name, m in eval_list:
        evaluate_model(m, X_test_scaled, y_test, name)

    # Save models
    ensemble_path = os.path.join(MODELS_DIR, 'ensemble_model.pkl')
    scaler_path = os.path.join(MODELS_DIR, 'scaler.pkl')
    xgb_path = os.path.join(MODELS_DIR, 'xgb_model.pkl')
    lgbm_path = os.path.join(MODELS_DIR, 'lgbm_model.pkl')
    rf_path = os.path.join(MODELS_DIR, 'rf_model.pkl')

    joblib.dump(ensemble, ensemble_path)
    joblib.dump(scaler, scaler_path)
    joblib.dump(xgb, xgb_path)
    joblib.dump(lgbm, lgbm_path)
    joblib.dump(rf, rf_path)

    if cb is not None:
        cb_path = os.path.join(MODELS_DIR, 'cb_model.pkl')
        joblib.dump(cb, cb_path)
        print(f'CatBoost model: {cb_path}')

    # Save metadata
    meta = {
        'version': '1.0.0',
        'trained_at': datetime.utcnow().isoformat(),
        'features': features,
        'n_samples': len(X),
        'train_size': len(X_train),
        'test_size': len(X_test),
        'accuracy': float(accuracy_score(y_test, ensemble.predict(X_test_scaled)))
    }
    with open(os.path.join(MODELS_DIR, 'model_meta.json'), 'w') as f:
        json.dump(meta, f, indent=2)

    print(f'\nModels saved to {MODELS_DIR}/')
    print('Ensemble model: ensemble_model.pkl')
    print('Scaler: scaler.pkl')
    print('Metadata: model_meta.json')


if __name__ == '__main__':
    main()
