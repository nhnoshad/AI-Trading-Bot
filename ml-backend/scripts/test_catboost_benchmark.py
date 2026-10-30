"""
CatBoost Integration & Accuracy Verification Benchmark
Compares 3-model ensemble vs 4-model ensemble (with CatBoost) on real learning memory data.
Verifies all 28 indicator features and model inference pipeline.
"""
import os
import sys
import json
import time
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier

# Path setup
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, BASE_DIR)

from app.services.indicators import calculate_indicators, FEATURE_COLUMNS
from app.services.adaptive_learner import get_adaptive_learner
from app.services.predictor import get_predictor

DATA_PATH = os.path.join(BASE_DIR, 'data', 'rolling_30d_learning_memory.csv')

def run_benchmark():
    print("=" * 70)
    print("CATBOOST INTEGRATION BENCHMARK & ACCURACY VERIFICATION")
    print("=" * 70)
    
    # 1. Feature verification
    print(f"\n[1] Verifying 28 Features in indicators.py...")
    print(f"Total defined FEATURE_COLUMNS: {len(FEATURE_COLUMNS)}")
    assert len(FEATURE_COLUMNS) == 28, f"Expected 28 features, got {len(FEATURE_COLUMNS)}"
    for idx, f in enumerate(FEATURE_COLUMNS, 1):
        print(f"  {idx:2d}. {f}")
    
    # 2. Load dataset
    print(f"\n[2] Loading dataset from: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH)
    print(f"Total rows loaded: {len(df)}")
    
    # Verify features are in dataset
    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing:
        print(f"Missing columns: {missing}")
        sys.exit(1)
    print("All 28 features verified in dataset!")

    X = df[FEATURE_COLUMNS].fillna(0.0).values
    y = df['label'].astype(int).values
    sample_weights = np.where(df.get('source', 'historical') == 'live_trade', 3.0, 1.0)
    
    # Time-series 80/20 train/test split
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    w_train = sample_weights[:split]
    
    print(f"Train samples: {len(X_train)}, Test samples: {len(X_test)}")
    print(f"Label balance - Test set BUY: {int(y_test.sum())}, SELL: {int((1-y_test).sum())}")
    
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    
    # 3. Train individual models
    print("\n[3] Training individual models...")
    
    # XGBoost
    t0 = time.time()
    xgb = XGBClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
        gamma=0.1, reg_alpha=0.1, reg_lambda=1.0,
        random_state=42, eval_metric='logloss', verbosity=0
    )
    xgb.fit(X_train_s, y_train, sample_weight=w_train)
    t_xgb = time.time() - t0
    
    # LightGBM
    t0 = time.time()
    lgbm = LGBMClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.05,
        num_leaves=31, subsample=0.8, colsample_bytree=0.8,
        min_child_samples=20, reg_alpha=0.1, reg_lambda=0.1,
        random_state=42, verbosity=-1
    )
    lgbm.fit(X_train_s, y_train, sample_weight=w_train)
    t_lgbm = time.time() - t0
    
    # Random Forest
    t0 = time.time()
    rf = RandomForestClassifier(
        n_estimators=200, max_depth=10, min_samples_split=10,
        min_samples_leaf=5, max_features='sqrt',
        class_weight='balanced', random_state=42, n_jobs=-1
    )
    rf.fit(X_train_s, y_train, sample_weight=w_train)
    t_rf = time.time() - t0
    
    # CatBoost
    t0 = time.time()
    cb = CatBoostClassifier(
        iterations=250, depth=6, learning_rate=0.05,
        verbose=0, random_seed=42
    )
    cb.fit(X_train_s, y_train, sample_weight=w_train)
    t_cb = time.time() - t0
    
    # Evaluate individual models
    models_dict = {
        'XGBoost': (xgb, t_xgb),
        'LightGBM': (lgbm, t_lgbm),
        'Random Forest': (rf, t_rf),
        'CatBoost': (cb, t_cb)
    }
    
    print("\n--- Individual Model Accuracies on Test Set ---")
    ind_scores = {}
    for name, (m, elapsed) in models_dict.items():
        pred = m.predict(X_test_s)
        acc = accuracy_score(y_test, pred) * 100
        prec = precision_score(y_test, pred, zero_division=0) * 100
        rec = recall_score(y_test, pred, zero_division=0) * 100
        f1 = f1_score(y_test, pred, zero_division=0) * 100
        ind_scores[name] = acc
        print(f"  {name:15s}: Acc = {acc:.2f}% | Prec = {prec:.2f}% | Rec = {rec:.2f}% | F1 = {f1:.2f}% | Time = {elapsed:.2f}s")
    
    # 4. Compare Ensembles: 3-Model vs 4-Model
    print("\n[4] Evaluating Ensemble Architectures...")
    
    # 3-Model Ensemble (XGB + LGBM + RF)
    ens_3 = VotingClassifier(
        estimators=[('xgb', xgb), ('lgbm', lgbm), ('rf', rf)],
        voting='soft',
        weights=[0.40, 0.35, 0.25]
    )
    ens_3.fit(X_train_s, y_train)
    pred_3 = ens_3.predict(X_test_s)
    acc_3 = accuracy_score(y_test, pred_3) * 100
    prec_3 = precision_score(y_test, pred_3, zero_division=0) * 100
    f1_3 = f1_score(y_test, pred_3, zero_division=0) * 100
    
    # 4-Model Ensemble (XGB + LGBM + CatBoost + RF)
    ens_4 = VotingClassifier(
        estimators=[('xgb', xgb), ('lgbm', lgbm), ('cb', cb), ('rf', rf)],
        voting='soft',
        weights=[0.30, 0.25, 0.25, 0.20]
    )
    ens_4.fit(X_train_s, y_train)
    pred_4 = ens_4.predict(X_test_s)
    acc_4 = accuracy_score(y_test, pred_4) * 100
    prec_4 = precision_score(y_test, pred_4, zero_division=0) * 100
    f1_4 = f1_score(y_test, pred_4, zero_division=0) * 100
    
    print("\n" + "=" * 55)
    print("ACCURACY COMPARISON RESULTS:")
    print(f"  3-Model Ensemble (XGB + LGBM + RF)    : {acc_3:.2f}% (F1: {f1_3:.2f}%)")
    print(f"  4-Model Ensemble (+ CATBOOST)         : {acc_4:.2f}% (F1: {f1_4:.2f}%)")
    delta_acc = acc_4 - acc_3
    print(f"  Net Accuracy Improvement from CatBoost: {'+' if delta_acc >= 0 else ''}{delta_acc:.2f}%")
    print("=" * 55)
    
    # 5. Run full retraining through AdaptiveLearner to verify deployment & disk persistence
    print("\n[5] Running Full Retraining through AdaptiveLearner...")
    learner = get_adaptive_learner()
    retrain_res = learner.retrain_from_rolling_memory()
    print(f"Retrain Result: {retrain_res}")
    
    # Verify cb_model.pkl exists
    cb_path = os.path.join(BASE_DIR, 'models', 'cb_model.pkl')
    print(f"CatBoost model file exists on disk: {os.path.exists(cb_path)} ({os.path.getsize(cb_path)} bytes)")
    
    # 6. Test Predictor with live candle batch & verify all 28 features in output
    print("\n[6] Testing Live Predictor Pipeline with 4 models & 28 features...")
    predictor = get_predictor()
    predictor.reload_models()
    
    print(f"Predictor models loaded:")
    print(f"  Ensemble model : {predictor.model is not None}")
    print(f"  XGBoost model  : {predictor.xgb_model is not None}")
    print(f"  LightGBM model : {predictor.lgbm_model is not None}")
    print(f"  CatBoost model : {predictor.cb_model is not None}")
    print(f"  RF model       : {predictor.rf_model is not None}")
    print(f"  Scaler         : {predictor.scaler is not None}")
    
    # Generate test candle batch from recent memory data
    test_candles = []
    base_price = 1.0850
    for i in range(60):
        c_open = base_price + np.random.normal(0, 0.0005)
        c_close = c_open + np.random.normal(0, 0.0004)
        c_high = max(c_open, c_close) + abs(np.random.normal(0, 0.0002))
        c_low = min(c_open, c_close) - abs(np.random.normal(0, 0.0002))
        test_candles.append({
            'open': c_open, 'high': c_high, 'low': c_low, 'close': c_close, 'volume': 1500.0
        })
        base_price = c_close
        
    pred_res = predictor.predict(test_candles, timeframe='1m', pair='EURUSD')
    print("\nPrediction Output Check:")
    print(f"  Signal              : {pred_res['signal']}")
    print(f"  Confidence          : {pred_res['confidence']}%")
    print(f"  Model Votes (4)     : {pred_res['model_votes']}")
    print(f"  Ensemble Weights (4): {pred_res['ensemble_weights']}")
    print(f"  Features count      : {len(pred_res['features'])}")
    print(f"  Analysis latency    : {pred_res['analysis_ms']} ms")
    
    assert 'cb' in pred_res['model_votes'], "CatBoost vote missing from prediction!"
    assert 'cb' in pred_res['ensemble_weights'], "CatBoost weight missing from prediction!"
    assert len(pred_res['features']) == 28, f"Expected 28 features in prediction, got {len(pred_res['features'])}"
    
    print("\n" + "*" * 60)
    print("ALL TESTS & BENCHMARKS PASSED SUCCESSFULLY!")
    print("*" * 60)

if __name__ == '__main__':
    run_benchmark()
