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
import concurrent.futures
from datetime import datetime, timedelta
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.linear_model import LogisticRegression
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
    # Use the AVAILABLE features (the new 5 may not be in older CSV data)
    old_28_features = [
        'rsi_14', 'rsi_7', 'stoch_k', 'stoch_d', 'williams_r', 'cci',
        'ema_9', 'ema_21', 'sma_50', 'macd_line', 'macd_signal', 'macd_hist',
        'ema_cross', 'adx', 'bb_width', 'bb_position', 'atr_14',
        'price_change_1', 'price_change_3', 'price_change_5', 'candle_body_ratio',
        'body_size', 'upper_wick', 'lower_wick', 'is_doji', 'is_hammer',
        'is_engulfing', 'consecutive_same_direction'
    ]
    has_base_features = all(f in df.columns for f in old_28_features)
    if has_base_features:
        print('Using pre-calculated technical indicator features from dataset...')
        df_features = df.copy()
        # For any new features not yet in older CSV, fill with 0 as neutral placeholder
        # This includes v2 (5 features) and v3 elite (5 features) additions
        for nf in FEATURE_COLUMNS:
            if nf not in df_features.columns:
                df_features[nf] = 0.0
                print(f'  [info] New feature "{nf}" not in CSV — filled with 0. Re-collect live data to include it.')
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

    # Features and target — only use columns that exist
    available_features = [f for f in FEATURE_COLUMNS if f in df_features.columns]
    X = np.nan_to_num(df_features[available_features].values, nan=0.0, posinf=0.0, neginf=0.0)
    y = df_features['label'].values.astype(int)

    # Sample weights calculation using Marcos López de Prado financial weighting
    sample_weights = compute_financial_sample_weights(df_features)

    print(f'Features: {len(available_features)}, Samples: {len(X)}')
    print(f'Label distribution: BUY={int(y.sum())}, SELL={int((1-y).sum())}')
    return X, y, available_features, sample_weights


def compute_financial_sample_weights(
    df: pd.DataFrame,
    retention_days: int = 35,
    half_life_days: float = 10.0,
    live_trade_boost: float = 3.0,
    error_penalty_boost: float = 4.0,
    high_conf_threshold: float = 0.70
) -> np.ndarray:
    """
    Computes Marcos López de Prado quantitative sample weights combining:
    1. Exponential Time Decay: w_t = exp(-lambda * delta_t) with half-life of 10 days.
    2. Real Live Trade Boost: live trades get 3.0x weight over historical synthetic bars.
    3. High-Confidence Error Penalty: samples where AI predicted with high confidence (>=70%)
       yet got the outcome wrong receive a 4.0x penalty weight to forcefully adapt decision boundaries.
    """
    n = len(df)
    weights = np.ones(n, dtype=np.float64)

    # 1. Exponential Time Decay
    if 'timestamp' in df.columns:
        now = datetime.utcnow()
        ts_series = pd.to_datetime(df['timestamp'], errors='coerce')
        default_ts = now - timedelta(days=retention_days / 2.0)
        ts_series = ts_series.fillna(default_ts)
        try:
            days_ago = np.array([
                max(0.0, (now - t.to_pydatetime().replace(tzinfo=None)).total_seconds() / 86400.0)
                for t in ts_series
            ])
            decay_lambda = np.log(2.0) / max(1.0, half_life_days)
            time_weights = np.exp(-decay_lambda * days_ago)
            time_weights = time_weights / (np.mean(time_weights) + 1e-6)
            weights *= time_weights
        except Exception:
            pass

    # 2. Live Trade Boost
    if 'source' in df.columns:
        is_live = (df['source'] == 'live_trade') | (df['source'] == 'quotex_interception')
        weights = np.where(is_live, weights * live_trade_boost, weights)

    # 3. High-Confidence Error Penalty
    if 'was_correct' in df.columns:
        was_correct = df['was_correct'].astype(int)
        conf = df.get('confidence', 0.65)
        if isinstance(conf, (pd.Series, np.ndarray)):
            conf_norm = np.where(conf > 1.0, conf / 100.0, conf)
        else:
            conf_norm = 0.65
        is_high_conf_error = (was_correct == 0) & (conf_norm >= high_conf_threshold)
        weights = np.where(is_high_conf_error, weights * error_penalty_boost, weights)

    weights = np.clip(weights, 0.1, 20.0)
    weights = weights / (np.mean(weights) + 1e-6)
    return weights


def train_models(X_train, y_train, sample_weight=None):
    """
    High-Performance Multi-Core Parallel Training of 5-Model Ensemble:
    - XGBoost: Histogram-based tree building (tree_method='hist') for 10x speedup
    - LightGBM: Gradient-based One-Side Sampling (GOSS) for 3x speedup
    - CatBoost: Minimal Variance Sampling (MVS) for 2.5x speedup
    - Random Forest: Multi-threaded parallel fitting (n_jobs=-1)
    - Deep MLP: Adaptive Adam learning rate for neuro-embeddings
    - Stacking Meta-Learner: L2-regularized Logistic Regression stacking probability blender
    """
    print('\n[Parallel Execution] Fitting XGBoost, LightGBM, CatBoost, RF & MLP concurrently across CPU cores...')

    def fit_xgb():
        print(' -> Fitting XGBoost (hist accelerated)...')
        xgb = XGBClassifier(
            n_estimators=350, max_depth=5, learning_rate=0.04,
            subsample=0.8, colsample_bytree=0.8, min_child_weight=6,
            gamma=0.15, reg_alpha=0.2, reg_lambda=1.5,
            tree_method='hist',
            scale_pos_weight=1, random_state=42,
            eval_metric='logloss', verbosity=0
        )
        xgb.fit(X_train, y_train, sample_weight=sample_weight)
        return xgb

    def fit_lgbm():
        print(' -> Fitting LightGBM (GOSS accelerated)...')
        lgbm = LGBMClassifier(
            n_estimators=350, max_depth=5, learning_rate=0.04,
            boosting_type='goss', max_bin=127,
            num_leaves=24, subsample=1.0, colsample_bytree=0.8,
            min_child_samples=20, reg_alpha=0.2, reg_lambda=0.2,
            random_state=42, verbosity=-1
        )
        lgbm.fit(X_train, y_train, sample_weight=sample_weight)
        return lgbm

    def fit_cb():
        if not CATBOOST_AVAILABLE:
            return None
        print(' -> Fitting CatBoost (MVS accelerated)...')
        cb = CatBoostClassifier(
            iterations=350, depth=5, learning_rate=0.04,
            border_count=128, bootstrap_type='MVS',
            l2_leaf_reg=5.0, random_strength=1.5,
            thread_count=-1,
            verbose=0, random_seed=42
        )
        cb.fit(X_train, y_train, sample_weight=sample_weight)
        return cb

    def fit_rf():
        print(' -> Fitting Random Forest (n_jobs=-1 parallel)...')
        rf = RandomForestClassifier(
            n_estimators=300, max_depth=9, min_samples_split=12,
            min_samples_leaf=6, max_features='sqrt',
            class_weight='balanced', random_state=42, n_jobs=-1
        )
        rf.fit(X_train, y_train, sample_weight=sample_weight)
        return rf

    def fit_mlp():
        print(' -> Fitting Deep MLP Neural Network (Neuro-Embeddings)...')
        mlp = MLPClassifier(
            hidden_layer_sizes=(128, 64, 32),
            activation='relu',
            solver='adam',
            alpha=0.005,
            batch_size=64,
            learning_rate='adaptive',
            learning_rate_init=0.002,
            max_iter=300,
            warm_start=False,
            early_stopping=False,
            random_state=42
        )
        mlp.fit(X_train, y_train)
        return mlp

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        f_xgb = executor.submit(fit_xgb)
        f_lgbm = executor.submit(fit_lgbm)
        f_cb = executor.submit(fit_cb)
        f_rf = executor.submit(fit_rf)
        f_mlp = executor.submit(fit_mlp)

        xgb = f_xgb.result()
        lgbm = f_lgbm.result()
        cb = f_cb.result()
        rf = f_rf.result()
        mlp = f_mlp.result()

    print('[Parallel Execution] All 5 base models fitted successfully.')

    # Train Level-2 Stacking Meta-Learner (Logistic Regression on probability outputs)
    print('Training Level-2 Stacking Meta-Learner (L2 Regularized)...')
    p_xgb = xgb.predict_proba(X_train)[:, 1]
    p_lgbm = lgbm.predict_proba(X_train)[:, 1]
    p_rf = rf.predict_proba(X_train)[:, 1]
    p_mlp = mlp.predict_proba(X_train)[:, 1]

    if cb is not None:
        p_cb = cb.predict_proba(X_train)[:, 1]
        meta_X = np.column_stack([p_xgb, p_lgbm, p_cb, p_rf, p_mlp])
        estimators = [('xgb', xgb), ('lgbm', lgbm), ('cb', cb), ('rf', rf), ('mlp', mlp)]
        weights = [0.24, 0.20, 0.22, 0.16, 0.18]
    else:
        meta_X = np.column_stack([p_xgb, p_lgbm, p_rf, p_mlp])
        estimators = [('xgb', xgb), ('lgbm', lgbm), ('rf', rf), ('mlp', mlp)]
        weights = [0.30, 0.28, 0.20, 0.22]

    meta_model = LogisticRegression(C=1.5, penalty='l2', solver='lbfgs', max_iter=250, random_state=42)
    meta_model.fit(meta_X, y_train)

    ensemble = VotingClassifier(
        estimators=estimators,
        voting='soft',
        weights=weights
    )
    ensemble.fit(X_train, y_train)

    return ensemble, xgb, lgbm, cb, rf, mlp, meta_model


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

    X, y, features, sample_weights = load_and_process_data(args.data)

    # Time-series split (no shuffle!)
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    w_train = sample_weights[:split]
    print(f'Train: {len(X_train)}, Test: {len(X_test)}')

    # Scale features
    scaler = StandardScaler()
    X_train_scaled = np.nan_to_num(scaler.fit_transform(X_train), nan=0.0)
    X_test_scaled = np.nan_to_num(scaler.transform(X_test), nan=0.0)

    # Train (Fast Parallel Fitting + Stacking Meta-Learner)
    ensemble, xgb, lgbm, cb, rf, mlp, meta_model = train_models(X_train_scaled, y_train, sample_weight=w_train)

    # Evaluate each model
    eval_list = [('XGBoost', xgb), ('LightGBM', lgbm)]
    if cb is not None:
        eval_list.append(('CatBoost', cb))
    eval_list.extend([('Random Forest', rf), ('Deep MLP', mlp), ('5-Way Neuro-Ensemble', ensemble)])

    for name, m in eval_list:
        evaluate_model(m, X_test_scaled, y_test, name)

    # Save models
    ensemble_path = os.path.join(MODELS_DIR, 'ensemble_model.pkl')
    meta_model_path = os.path.join(MODELS_DIR, 'meta_model.pkl')
    scaler_path = os.path.join(MODELS_DIR, 'scaler.pkl')
    xgb_path = os.path.join(MODELS_DIR, 'xgb_model.pkl')
    lgbm_path = os.path.join(MODELS_DIR, 'lgbm_model.pkl')
    rf_path = os.path.join(MODELS_DIR, 'rf_model.pkl')
    mlp_path = os.path.join(MODELS_DIR, 'mlp_model.pkl')

    joblib.dump(ensemble, ensemble_path)
    joblib.dump(meta_model, meta_model_path)
    joblib.dump(scaler, scaler_path)
    joblib.dump(xgb, xgb_path)
    joblib.dump(lgbm, lgbm_path)
    joblib.dump(rf, rf_path)
    joblib.dump(mlp, mlp_path)

    if cb is not None:
        cb_path = os.path.join(MODELS_DIR, 'cb_model.pkl')
        joblib.dump(cb, cb_path)
        print(f'CatBoost model: {cb_path}')

    print(f'Stacking Meta-Model: {meta_model_path}')
    print(f'Deep MLP model: {mlp_path}')

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
