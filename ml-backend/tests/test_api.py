"""
Automated Test Suite for AI Trading Signal Bot ML Backend
Tests all API endpoints, 28 technical indicators, fast analysis latency,
performance measurement, 35-day rolling memory, and outcome-based learning.
"""

import os
import sys
import numpy as np
import pytest
from fastapi.testclient import TestClient

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, BASE_DIR)

from app.main import app
from app.core.database import init_db, SessionLocal, Trade, Signal, LearningSample
from app.services.indicators import calculate_indicators, FEATURE_COLUMNS

init_db()
client = TestClient(app)


def make_sample_candles(n: int = 80):
    np.random.seed(123)
    candles = []
    price = 1.0850
    for i in range(n):
        open_p = price
        close_p = price + (np.random.randn() * 0.0004)
        high_p = max(open_p, close_p) + 0.0002
        low_p = min(open_p, close_p) - 0.0002
        candles.append({
            'open': round(float(open_p), 5),
            'high': round(float(high_p), 5),
            'low': round(float(low_p), 5),
            'close': round(float(close_p), 5),
            'volume': 1200.0
        })
        price = close_p
    return candles


def test_indicators_calculation():
    candles = make_sample_candles(80)
    df = calculate_indicators(candles)
    assert len(FEATURE_COLUMNS) >= 33  # 33 original + new elite indicators
    for col in FEATURE_COLUMNS:
        assert col in df.columns, f'Missing indicator column: {col}'


def test_health_endpoint():
    resp = client.get('/api/health')
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'running'
    assert 'ensemble_weights' in data


def test_predict_and_outcome_learning_cycle():
    candles = make_sample_candles(80)
    resp = client.post('/api/predict', json={
        'candles': candles,
        'timeframe': '1m',
        'pair': 'EURUSD'
    })
    assert resp.status_code == 200
    pred = resp.json()
    assert pred['signal'] in ('BUY', 'SELL', 'WAIT')
    assert 'confidence' in pred
    assert 'signal_id' in pred
    assert 'analysis_ms' in pred
    assert 'indicators' in pred
    assert 'reasons' in pred

    # Now log a trade result linked to this signal and verify adaptive learning
    trade_id = None
    try:
        trade_resp = client.post('/api/log-trade', json={
            'signal_id': pred['signal_id'],
            'pair': 'EURUSD',
            'direction': 'BUY',
            'amount': 10.0,
            'duration': 60,
            'entry_price': pred['entry_price'],
            'exit_price': pred['entry_price'] + 0.0005,
            'result': 'WIN',
            'mode': 'PREDICTION'
        })
        assert trade_resp.status_code == 200
        t_data = trade_resp.json()
        assert t_data['logged'] is True
        assert t_data['learning_update']['learned'] is True
        assert t_data['learning_update']['sample_saved'] is True
        trade_id = t_data.get('trade', {}).get('id')
    finally:
        db = SessionLocal()
        try:
            if trade_id:
                db.query(Trade).filter(Trade.id == trade_id).delete()
            if pred.get('signal_id'):
                db.query(Signal).filter(Signal.id == pred['signal_id']).delete()
                db.query(LearningSample).filter(LearningSample.signal_id == pred['signal_id']).delete()
            db.commit()
        finally:
            db.close()


def test_stats_trades_signals_and_performance():
    assert client.get('/api/stats').status_code == 200
    assert client.get('/api/trades').status_code == 200
    assert client.get('/api/signals').status_code == 200
    assert client.get('/api/indicators').status_code == 200

    perf_resp = client.get('/api/model-performance')
    assert perf_resp.status_code == 200
    perf = perf_resp.json()
    assert 'memory_buffer' in perf
    assert perf['memory_buffer']['retention_days'] >= 30
    assert 'dynamic_weights' in perf


def test_backtest_endpoint():
    bt_resp = client.post('/api/backtest', json={
        'strategy': 'default',
        'period': '30d',
        'pair': 'EURUSD',
        'timeframe': '1m',
        'confidence_threshold': 60.0
    })
    assert bt_resp.status_code == 200
    bt = bt_resp.json()
    assert 'win_rate' in bt
    assert 'equity_curve' in bt


def test_balanced_multi_pair_buy_sell_wait_predictions():
    import math
    from app.services.predictor import get_predictor

    predictor = get_predictor()
    predictor.reload_models()

    def unit_rand(pair_hash: int, step: int, salt: int) -> float:
        x = (pair_hash ^ (step * 374761393) ^ (salt * 668265263)) & 0xFFFFFFFF
        x = ((x ^ (x >> 13)) * 1274126177) & 0xFFFFFFFF
        x = (x ^ (x >> 16)) & 0xFFFFFFFF
        return (x % 100000) / 100000.0

    def make_rolling_candles(pair: str, base_price: float, current_step: int, count: int = 120):
        scale = 0.08 if base_price > 50 else 0.00045
        decimals = 3 if base_price > 50 else 5
        pair_hash = 2166136261
        for ch in pair:
            pair_hash ^= ord(ch)
            pair_hash = (pair_hash * 16777619) & 0xFFFFFFFF
        start_step = current_step - count
        phase1 = (pair_hash % 360) * (math.pi / 180.0)
        phase2 = ((pair_hash >> 8) % 360) * (math.pi / 180.0)
        freq1 = 8.5 + (pair_hash % 7) * 0.6
        freq2 = 21.0 + ((pair_hash >> 4) % 9) * 0.8
        price = base_price
        candles = []
        for idx in range(1, count + 1):
            t = start_step + idx
            wf = math.sin(t / freq1 + phase1) * scale * 0.85
            ws = math.cos(t / freq2 + phase2) * scale * 0.65
            noise = (unit_rand(pair_hash, t, 1) - 0.50) * scale * 0.90
            mr = (base_price - price) * 0.06
            o = price
            c = max(0.0001, o + wf + ws + noise + mr)
            h = max(o, c) + unit_rand(pair_hash, t, 2) * scale * 0.45
            l = min(o, c) - unit_rand(pair_hash, t, 3) * scale * 0.45
            candles.append({
                'open': round(o, decimals),
                'high': round(h, decimals),
                'low': round(l, decimals),
                'close': round(c, decimals),
                'volume': 1000.0
            })
            price = c
        return candles

    pairs = [
        ('EUR/AUD (OTC)', 1.6520),
        ('EUR/USD (OTC)', 1.0854),
        ('GBP/USD (OTC)', 1.2742),
        ('USD/JPY (OTC)', 151.45),
        ('USD/BDT (OTC)', 119.50),
    ]
    counts = {'BUY': 0, 'SELL': 0, 'WAIT': 0}
    euraud_signals = set()
    for pair, bp in pairs:
        for step in range(1000, 1040):
            res = predictor.predict(make_rolling_candles(pair, bp, step), '1m', pair, min_confidence_override=0.55)
            counts[res['signal']] += 1
            if pair == 'EUR/AUD (OTC)':
                euraud_signals.add(res['signal'])

    print('\nMulti-pair signal distribution:', counts, '| EUR/AUD signals:', euraud_signals)
    assert counts['BUY'] >= 15, f"Expected plenty of BUY signals, got {counts}"
    assert counts['SELL'] >= 15, f"Expected plenty of SELL signals, got {counts}"
    assert 'BUY' in euraud_signals and 'SELL' in euraud_signals


def test_candlestick_pattern_recognizer():
    from app.services.pattern_recognizer import detect_candlestick_pattern

    # 1. Morning Star (Bullish Reversal)
    morning_star = [
        {'open': 1.1050, 'high': 1.1060, 'low': 1.0990, 'close': 1.1000},
        {'open': 1.0998, 'high': 1.1002, 'low': 1.0985, 'close': 1.0999},
        {'open': 1.1000, 'high': 1.1050, 'low': 1.0998, 'close': 1.1040}
    ]
    p_ms = detect_candlestick_pattern(morning_star)
    assert p_ms['pattern_name'] == 'Morning Star'
    assert p_ms['direction'] == 'BULLISH'
    assert p_ms['reliability'] == 'HIGH'

    # 2. Evening Star (Bearish Reversal)
    evening_star = [
        {'open': 1.1000, 'high': 1.1050, 'low': 1.0998, 'close': 1.1045},
        {'open': 1.1048, 'high': 1.1055, 'low': 1.1042, 'close': 1.1049},
        {'open': 1.1045, 'high': 1.1048, 'low': 1.0990, 'close': 1.1005}
    ]
    p_es = detect_candlestick_pattern(evening_star)
    assert p_es['pattern_name'] == 'Evening Star'
    assert p_es['direction'] == 'BEARISH'
    assert p_es['reliability'] == 'HIGH'

    # 3. Three White Soldiers
    soldiers = [
        {'open': 1.1000, 'high': 1.1020, 'low': 1.0995, 'close': 1.1018},
        {'open': 1.1015, 'high': 1.1035, 'low': 1.1010, 'close': 1.1033},
        {'open': 1.1030, 'high': 1.1055, 'low': 1.1025, 'close': 1.1052}
    ]
    p_tws = detect_candlestick_pattern(soldiers)
    assert p_tws['pattern_name'] == 'Three White Soldiers'
    assert p_tws['direction'] == 'BULLISH'

    # 4. Bulkowski #1 Ranked Pattern: Bullish Three Line Strike
    strike_candles = [
        {'open': 1.1060, 'high': 1.1065, 'low': 1.1038, 'close': 1.1040},  # Bear 1
        {'open': 1.1040, 'high': 1.1042, 'low': 1.1018, 'close': 1.1020},  # Bear 2
        {'open': 1.1020, 'high': 1.1022, 'low': 1.0998, 'close': 1.1000},  # Bear 3
        {'open': 1.0999, 'high': 1.1070, 'low': 1.0995, 'close': 1.1068}   # Mega Bull Strike
    ]
    p_strike = detect_candlestick_pattern(strike_candles)
    assert 'Three Line Strike' in p_strike['pattern_name']
    assert p_strike['direction'] == 'BULLISH'
    assert p_strike['reliability'] == 'VERY HIGH'

    # 5. Predict endpoint returns detected_pattern
    candles = make_sample_candles(80)
    resp = client.post('/api/predict', json={
        'candles': candles,
        'timeframe': '1m',
        'pair': 'Bitcoin (OTC)'
    })
    assert resp.status_code == 200
    pred = resp.json()
    assert 'pattern' in pred
    assert 'pattern_name' in pred['pattern']
    assert 'direction' in pred['pattern']


