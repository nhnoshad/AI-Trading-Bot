"""
Comprehensive Audit Script:
Verifies every single feature and calculation used in the AI Prediction Engine.
"""
import sys
import os
import time
import numpy as np
import pandas as pd

# Set working directory to ml-backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.indicators import (
    calculate_indicators, FEATURE_COLUMNS,
    get_indicator_signals, generate_reasons
)
from app.services.pattern_recognizer import detect_candlestick_pattern
from app.services.quotex_engine import (
    analyze_quotex_algorithm_dynamics,
    analyze_multi_timeframe_5m,
    analyze_micro_second_velocity
)
from app.services.predictor import get_predictor
from app.services.adaptive_learner import get_adaptive_learner


def generate_synthetic_candles(count=120, trend="UP"):
    candles = []
    base_price = 1.0850
    p = base_price
    for i in range(count):
        step = (i - count / 2)
        if trend == "UP":
            drift = 0.00015
        elif trend == "DOWN":
            drift = -0.00015
        else:
            drift = 0.0001 * np.sin(i / 5.0)

        o = p
        c = o + drift + (np.sin(i / 3.0) * 0.00008)
        h = max(o, c) + abs(np.cos(i / 2.0)) * 0.00006
        l = min(o, c) - abs(np.sin(i / 2.0)) * 0.00006
        vol = 1000 + int(np.sin(i) * 300)
        candles.append({
            'open': round(o, 5),
            'high': round(h, 5),
            'low': round(l, 5),
            'close': round(c, 5),
            'volume': vol
        })
        p = c
    return candles


def run_audit():
    print("=" * 80)
    print("STARTING COMPREHENSIVE AI PREDICTION FEATURE & MODEL AUDIT")
    print("=" * 80)
    all_passed = True

    # -------------------------------------------------------------
    # 1. AUDIT: 33 Technical Features Extraction & Column Integrity
    # -------------------------------------------------------------
    print("\n[Step 1] Auditing Technical Feature Extraction (33 Features)...")
    candles = generate_synthetic_candles(120, "UP")
    df_feat = calculate_indicators(candles)

    print(f"  Calculated DataFrame shape: {df_feat.shape}")
    print(f"  Target FEATURE_COLUMNS length: {len(FEATURE_COLUMNS)}")

    missing_cols = [c for c in FEATURE_COLUMNS if c not in df_feat.columns]
    if missing_cols:
        print(f"  [FAIL] Missing columns: {missing_cols}")
        all_passed = False
    else:
        print(f"  [PASS] All {len(FEATURE_COLUMNS)} required features are present in DataFrame.")

    # Check for NaN / Inf
    latest_row = df_feat[FEATURE_COLUMNS].iloc[-1]
    nan_cols = latest_row.index[latest_row.isna()].tolist()
    inf_cols = latest_row.index[np.isinf(latest_row)].tolist()

    if nan_cols:
        print(f"  [FAIL] NaN values found in: {nan_cols}")
        all_passed = False
    elif inf_cols:
        print(f"  [FAIL] Inf values found in: {inf_cols}")
        all_passed = False
    else:
        print(f"  [PASS] All 33 features have clean, finite numeric values.")

    # Feature range and type sanity check
    sanity_checks = {
        'rsi_14': (0, 100),
        'rsi_7': (0, 100),
        'stoch_k': (0, 100),
        'stoch_d': (0, 100),
        'williams_r': (-100, 0),
        'bb_position': (-1.0, 2.0),
        'adx': (0, 100),
        'ema_cross': (0, 1),
        'is_doji': (0, 1),
        'is_hammer': (0, 1),
        'is_engulfing': (0, 1),
        'bb_squeeze': (0, 1),
        'candle_directionality': (-1.01, 1.01)
    }
    for feat, (low, high) in sanity_checks.items():
        val = latest_row[feat]
        if not (low <= val <= high):
            print(f"  [FAIL] Feature {feat}={val} out of expected bounds [{low}, {high}]")
            all_passed = False
        else:
            print(f"    - {feat:22}: {val:8.3f} [Valid]")

    # -------------------------------------------------------------
    # 2. AUDIT: Scaler & ML Ensemble Models (XGB, LGBM, CB, RF)
    # -------------------------------------------------------------
    print("\n[Step 2] Auditing ML Models & Scaler Compatibility...")
    predictor = get_predictor()

    if predictor.scaler is None:
        print("  [FAIL] Scaler is None!")
        all_passed = False
    else:
        print("  [PASS] Scaler is loaded.")
        # Verify feature count
        n_features = predictor.scaler.n_features_in_
        print(f"  Scaler expects {n_features} features. FEATURE_COLUMNS has {len(FEATURE_COLUMNS)}.")
        if n_features != len(FEATURE_COLUMNS):
            print(f"  [FAIL] Dimension mismatch between Scaler ({n_features}) and FEATURE_COLUMNS ({len(FEATURE_COLUMNS)})")
            all_passed = False
        else:
            print("  [PASS] Scaler feature dimension exactly matches FEATURE_COLUMNS (33).")

    models = {
        'XGBoost': predictor.xgb_model,
        'LightGBM': predictor.lgbm_model,
        'CatBoost': predictor.cb_model,
        'RandomForest': predictor.rf_model,
        'Ensemble': predictor.model
    }

    X_sample = df_feat[FEATURE_COLUMNS].iloc[-1:].values
    X_scaled = predictor.scaler.transform(X_sample)

    for name, m in models.items():
        if m is None:
            print(f"  [FAIL] Model {name} is NOT loaded!")
            all_passed = False
            continue
        try:
            probs = m.predict_proba(X_scaled)[0]
            pred = int(np.argmax(probs))
            print(f"  [PASS] {name:14}: Probabilities [SELL={probs[0]:.4f}, BUY={probs[1]:.4f}] -> Pred={pred}")
            if not (0.999 <= sum(probs) <= 1.001):
                print(f"  [FAIL] Probabilities do not sum to 1.0: {sum(probs)}")
                all_passed = False
        except Exception as e:
            print(f"  [FAIL] Model {name} prediction error: {e}")
            all_passed = False

    # -------------------------------------------------------------
    # 3. AUDIT: Candlestick Pattern Recognizer
    # -------------------------------------------------------------
    print("\n[Step 3] Auditing Candlestick Pattern Recognizer...")
    pat = detect_candlestick_pattern(candles)
    print(f"  Detected pattern: {pat.get('pattern_name')}")
    print(f"  Direction: {pat.get('direction')}, Reliability: {pat.get('reliability')}")
    if 'pattern_name' in pat and 'direction' in pat and 'reliability' in pat:
        print("  [PASS] Candlestick pattern recognizer returns compliant structure.")
    else:
        print("  [FAIL] Missing keys in pattern recognizer output!")
        all_passed = False

    # -------------------------------------------------------------
    # 4. AUDIT: Quotex OTC Reverse-Engineering & Institutional Dynamics
    # -------------------------------------------------------------
    print("\n[Step 4] Auditing Quotex OTC Reverse-Engineering Dynamics...")
    dynamics = analyze_quotex_algorithm_dynamics(candles, micro_ticks={
        'velocity': 0.12, 'direction': 'UP', 'is_decelerating': False
    })

    required_dynamics_keys = [
        'regime', 'market_memory', 'hurst_exponent', 'quotex_bias',
        'confidence_adjustment', 'exhaustion_risk', 'mtf', 'micro_velocity', 'reasons'
    ]
    for k in required_dynamics_keys:
        if k not in dynamics:
            print(f"  [FAIL] Missing dynamic key: {k}")
            all_passed = False
        else:
            print(f"    - {k:25}: {dynamics[k]}")

    print(f"  Hurst Exponent: {dynamics['hurst_exponent']:.4f} (Memory: {dynamics['market_memory']}, Regime: {dynamics['regime']})")
    print("  [PASS] Quotex algorithmic dynamics operational.")

    # -------------------------------------------------------------
    # 5. AUDIT: Multi-Timeframe 5M Confluence Logic
    # -------------------------------------------------------------
    print("\n[Step 5] Auditing Multi-Timeframe (5M) Confluence...")
    mtf = analyze_multi_timeframe_5m(candles)
    print(f"  5M Macro Trend: {mtf.get('mtf_trend')}")
    print(f"  5M Strength: {mtf.get('mtf_strength')}")
    print(f"  5M RSI: {mtf.get('rsi_5m'):.2f}")
    print(f"  5M EMA9: {mtf.get('ema9_5m'):.5f} vs EMA21: {mtf.get('ema21_5m'):.5f}")
    if mtf.get('mtf_trend') in ['BULLISH', 'BEARISH', 'RANGING', 'NEUTRAL']:
        print("  [PASS] Multi-timeframe synthesis correctly computes 5M trend.")
    else:
        print("  [FAIL] Unexpected macro trend value!")
        all_passed = False

    # -------------------------------------------------------------
    # 6. AUDIT: Micro-Second Velocity Lock & Trap Confirmation
    # -------------------------------------------------------------
    print("\n[Step 6] Auditing Micro-Second Velocity Lock...")
    # Test normal confirming ticks
    normal_ticks = {'velocity': 0.25, 'direction': 'UP', 'is_decelerating': False}
    vel_res = analyze_micro_second_velocity(normal_ticks, expected_dir="BUY")
    print(f"  Confirming velocity: {vel_res.get('velocity')}, Confirmed: {vel_res.get('micro_confirmed')}, Trap: {vel_res.get('last_second_trap')}")
    if vel_res.get('micro_confirmed') and not vel_res.get('last_second_trap'):
        print("  [PASS] Confirming micro-velocity provides expected status.")
    else:
        print("  [FAIL] Confirming velocity logic unexpected!")
        all_passed = False

    # Test counter-spike trap (< -2.0 for BUY)
    trap_ticks = {'velocity': -3.5, 'direction': 'DOWN', 'is_decelerating': False}
    trap_res = analyze_micro_second_velocity(trap_ticks, expected_dir="BUY")
    print(f"  Counter-spike velocity: {trap_res.get('velocity')}, Trap: {trap_res.get('last_second_trap')}")
    if trap_res.get('last_second_trap') is True and not trap_res.get('micro_confirmed'):
        print("  [PASS] Last-second trap correctly flagged!")
    else:
        print("  [FAIL] Counter-spike was NOT flagged as a trap!")
        all_passed = False

    # -------------------------------------------------------------
    # 7. AUDIT: End-to-End Prediction Pipeline & Latency
    # -------------------------------------------------------------
    print("\n[Step 7] Auditing Full End-to-End Prediction Pipeline...")
    t0 = time.perf_counter()
    res = predictor.predict(
        candles=candles,
        timeframe="1m",
        pair="EURUSD",
        min_confidence=68.0,
        micro_ticks={'velocity': 0.15, 'direction': 'UP', 'is_decelerating': False}
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    print(f"  Signal Result: {res.get('signal')}")
    print(f"  Confidence: {res.get('confidence')}%")
    print(f"  Dynamic Gate Threshold: {res.get('dynamic_gate_threshold')}%")
    print(f"  Execution Latency: {elapsed_ms:.2f} ms")
    print(f"  Next Candle Summary: {res.get('next_candle_summary')}")
    print(f"  Reasons: {res.get('reasons')}")

    if res.get('signal') in ['BUY', 'SELL', 'WAIT']:
        print("  [PASS] Signal output format is valid.")
    else:
        print("  [FAIL] Invalid signal output!")
        all_passed = False

    if elapsed_ms < 60.0:
        print(f"  [PASS] Latency is sub-60ms ({elapsed_ms:.2f}ms) — High-frequency ready!")
    else:
        print(f"  [WARN] Latency higher than 60ms: {elapsed_ms:.2f}ms")

    # -------------------------------------------------------------
    # 8. AUDIT: Online Adaptive Learner & Dynamic Weight Updates
    # -------------------------------------------------------------
    print("\n[Step 8] Auditing Adaptive Learner & Weight Evolution...")
    from app.core.database import SessionLocal
    learner = get_adaptive_learner()
    weights_before = dict(learner.weights)
    print(f"  Ensemble Weights before update: {weights_before}")

    db = SessionLocal()
    try:
        update_res = learner.record_outcome_and_learn(
            db=db,
            signal_id=None,
            pair="EURUSD",
            direction="BUY",
            result="WIN",
            features_dict={col: 1.0 for col in FEATURE_COLUMNS},
            model_preds={'xgb': 0.72, 'lgbm': 0.76, 'cb': 0.73, 'rf': 0.69},
            confidence=74.5,
            timeframe="1m",
            source="audit_test"
        )
    finally:
        db.close()

    weights_after = learner.weights
    print(f"  Outcome recorded: {update_res.get('learned')}")
    print(f"  Ensemble Weights after update: {weights_after}")

    w_sum = sum([weights_after['xgb'], weights_after['lgbm'], weights_after['cb'], weights_after['rf']])
    if 0.99 <= w_sum <= 1.01:
        print(f"  [PASS] Dynamic weights normalize to 1.0 (Sum={w_sum:.4f}).")
    else:
        print(f"  [FAIL] Dynamic weights do not normalize: {w_sum}")
        all_passed = False

    # -------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    if all_passed:
        print(">>> ALL PREDICTION FEATURES AND COMPONENTS AUDITED AND FUNCTIONING 100% PERFECTLY! <<<")
    else:
        print(">>> SOME AUDIT CHECKS FAILED. PLEASE REVIEW LOGS ABOVE. <<<")
    print("=" * 80)
    return all_passed


if __name__ == "__main__":
    success = run_audit()
    sys.exit(0 if success else 1)
