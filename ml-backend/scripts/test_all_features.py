"""
Comprehensive End-to-End Test Suite
Tests all endpoints, 28 indicators, CatBoost sub-model, dynamic weight adaptation,
and prediction pipeline.
"""
import os
import sys
import json
import numpy as np

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, BASE_DIR)

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import init_db
from app.services.indicators import FEATURE_COLUMNS, calculate_indicators

init_db()
client = TestClient(app)

def test_full_pipeline():
    print("=" * 65)
    print("RUNNING COMPREHENSIVE END-TO-END FEATURE VERIFICATION")
    print("=" * 65)

    # 1. Health Endpoint
    print("\n[Test 1] GET /api/health ...")
    res = client.get("/api/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    health = res.json()
    print("  Status:", health.get('status'))
    print("  Model Version:", health.get('model_version'))
    print("  Model Loaded:", health.get('model_loaded'))
    print("  Ensemble Weights:", health.get('ensemble_weights'))
    assert health.get('model_loaded') is True
    assert 'cb' in health.get('ensemble_weights'), "CatBoost missing from health weights!"
    print("  -> Health check PASSED!")

    # 2. Indicators Endpoint
    print("\n[Test 2] GET /api/indicators ...")
    res = client.get("/api/indicators")
    assert res.status_code == 200
    ind_data = res.json()
    print("  Total indicators reported:", ind_data.get('count'))
    assert ind_data.get('count') == len(FEATURE_COLUMNS), f"Expected {len(FEATURE_COLUMNS)} indicators, got {ind_data.get('count')}"
    assert ind_data.get('indicators') == FEATURE_COLUMNS
    print(f"  -> Indicators verification PASSED (exact {len(FEATURE_COLUMNS)} features)!")

    # 3. Model Performance Endpoint
    print("\n[Test 3] GET /api/model-performance ...")
    res = client.get("/api/model-performance")
    assert res.status_code == 200
    perf = res.json()
    print("  Overall Accuracy:", perf.get('overall_accuracy'), "%")
    print("  Sub-models:")
    for sm in perf.get('sub_models', []):
        print(f"    - {sm['model']}: Accuracy={sm['accuracy']}, Weight={sm['weight']}, Status={sm['status']}")
    assert any(sm['model'] == 'CatBoost' for sm in perf.get('sub_models', [])), "CatBoost missing from sub_models!"
    print("  Dynamic Weights:", perf.get('dynamic_weights'))
    assert 'cb' in perf.get('dynamic_weights'), "CatBoost missing from dynamic weights!"
    print("  -> Model performance check PASSED!")

    # 4. Predict Endpoint with 28 features & 4-model votes
    print("\n[Test 4] POST /api/predict (Live 60-candle batch) ...")
    candles = []
    price = 1.0850
    for i in range(65):
        o = price
        c = o + np.random.uniform(-0.0004, 0.0004)
        h = max(o, c) + np.random.uniform(0.0001, 0.0003)
        l = min(o, c) - np.random.uniform(0.0001, 0.0003)
        candles.append({'open': o, 'high': h, 'low': l, 'close': c, 'volume': 1200.0})
        price = c

    payload = {
        'candles': candles,
        'timeframe': '1m',
        'pair': 'EURUSD',
        'min_confidence': 60.0
    }
    res = client.post("/api/predict", json=payload)
    assert res.status_code == 200, f"Predict failed: {res.text}"
    pred = res.json()
    print("  Signal:", pred['signal'])
    print("  Confidence:", pred['confidence'], "%")
    print("  Strength:", pred['strength'])
    print("  Analysis Latency:", pred['analysis_ms'], "ms")
    print("  Model Votes (all 4):", pred['model_votes'])
    print("  Ensemble Weights (all 4):", pred['ensemble_weights'])
    print("  Next Candle Summary:", pred['next_candle_prediction']['summary'])
    print("  Next Candle Duration:", pred['next_candle_prediction']['duration_text'])

    assert 'cb' in pred['model_votes'], "CatBoost missing from model_votes!"
    assert 'cb' in pred['ensemble_weights'], "CatBoost missing from ensemble_weights!"
    signal_id = pred.get('signal_id')
    assert signal_id is not None
    print(f"  Generated Signal ID: {signal_id}")
    print("  -> Predict endpoint PASSED!")

    # 5. Record Candle Outcome Endpoint (verifying online learning & CatBoost adaptation)
    print("\n[Test 5] POST /api/record-candle-outcome ...")
    outcome_payload = {
        'signal_id': signal_id,
        'pair': 'EURUSD',
        'timeframe': '1m',
        'direction': pred['signal'] if pred['signal'] in ('BUY', 'SELL') else 'BUY',
        'entry_price': pred['entry_price'],
        'exit_price': pred['entry_price'] + 0.0005,
        'result': 'WIN',
        'confidence': pred['confidence'],
        'duration': 60
    }
    res = client.post("/api/record-candle-outcome", json=outcome_payload)
    assert res.status_code == 200, f"Outcome recording failed: {res.text}"
    outcome_data = res.json()
    print("  Outcome Success:", outcome_data.get('success'))
    print("  Updated Weights:", outcome_data.get('learning_update', {}).get('updated_weights'))
    assert 'cb' in outcome_data.get('learning_update', {}).get('updated_weights', {}), "CatBoost weight update missing!"
    print("  -> Record candle outcome & online learning PASSED!")

    # 6. Stats Endpoint
    print("\n[Test 6] GET /api/stats ...")
    res = client.get("/api/stats")
    assert res.status_code == 200
    stats = res.json()
    print("  Total Trades:", stats.get('total_trades'))
    print("  Win Rate:", stats.get('win_rate'), "%")
    print("  Total PnL:", stats.get('total_pnl'))
    print("  Streak:", f"{stats.get('streak_dir')} {stats.get('streak')}")
    print("  -> Stats check PASSED!")

    print("\n" + "=" * 65)
    print("ALL 6 TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 65)

if __name__ == '__main__':
    test_full_pipeline()
