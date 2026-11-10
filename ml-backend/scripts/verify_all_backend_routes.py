import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

print("=" * 70)
print("VERIFYING ALL ML BACKEND ROUTES AND DATA STRUCTURES")
print("=" * 70)

# 1. Health
r = client.get('/api/health')
print(f"1. GET /api/health           -> Status {r.status_code} | Version: {r.json().get('model_version')}")
assert r.status_code == 200

# 2. Indicators
r = client.get('/api/indicators')
print(f"2. GET /api/indicators       -> Status {r.status_code} | Total Features: {r.json().get('count')}")
assert r.status_code == 200

# 3. Stats
r = client.get('/api/stats')
st = r.json()
print(f"3. GET /api/stats            -> Status {r.status_code} | Best Pair: {st.get('best_pair_display')} | Streak: {st.get('streak')}{st.get('streak_dir')} | Total: {st.get('total_trades')}")
assert r.status_code == 200

# 4. Trades
r = client.get('/api/trades?limit=1000')
td = r.json()
print(f"4. GET /api/trades           -> Status {r.status_code} | Returned {td.get('count')} trades | Total Unique Pairs: {len(td.get('all_pairs', []))}")
assert r.status_code == 200
print(f"   Available Pairs in DB: {td.get('all_pairs')[:6]} ... (+ {len(td.get('all_pairs')) - 6} more)")

# 5. Signals
r = client.get('/api/signals?limit=10')
print(f"5. GET /api/signals          -> Status {r.status_code} | Returned {len(r.json().get('signals', []))} signals")
assert r.status_code == 200

# 6. Model Performance
r = client.get('/api/model-performance')
mp = r.json()
print(f"6. GET /api/model-performance-> Status {r.status_code} | Accuracy: {mp.get('overall_accuracy')}%")
assert r.status_code == 200

# 7. Predict
candles = []
p = 1.0850
for i in range(120):
    o = p
    c = o + 0.0001
    h = c + 0.00005
    l = o - 0.00005
    candles.append({'open': o, 'high': h, 'low': l, 'close': c, 'volume': 1000})
    p = c
pred_payload = {'candles': candles, 'timeframe': '1m', 'pair': 'EUR/USD', 'min_confidence': 68}
r = client.post('/api/predict', json=pred_payload)
pr = r.json()
print(f"7. POST /api/predict         -> Status {r.status_code} | Signal: {pr.get('signal')} | Conf: {pr.get('confidence')}%")
assert r.status_code == 200

# 8. Log trade
r = client.post('/api/log-trade', json={'pair': 'EUR/USD', 'direction': 'BUY', 'amount': 10.0, 'duration': 60, 'entry_price': 1.0850, 'result': 'WIN', 'pnl': 8.5, 'mode': 'TEST'})
print(f"8. POST /api/log-trade       -> Status {r.status_code} | Recorded Trade ID: {r.json().get('trade', {}).get('id')}")
assert r.status_code == 200

# 9. Record candle outcome
r = client.post('/api/record-candle-outcome', json={
    'pair': 'EUR/USD',
    'timeframe': '1m',
    'direction': 'BUY',
    'entry_price': 1.0850,
    'exit_price': 1.0855,
    'result': 'WIN',
    'confidence': 72.0
})
print(f"9. POST /api/record-outcome  -> Status {r.status_code} | Online Learning: {r.json().get('success')}")
assert r.status_code == 200

# 10. Backtest
r = client.post('/api/backtest', json={'strategy': 'ml_ensemble', 'pair': 'EUR/USD', 'timeframe': '1m', 'period': '30d', 'confidence_threshold': 68.0, 'trade_amount': 10.0})
print(f"10. POST /api/backtest       -> Status {r.status_code} | Win Rate: {r.json().get('win_rate')}% | Trades: {r.json().get('total_trades')}")
assert r.status_code == 200

print("=" * 70)
print("ALL 10 ML BACKEND ENDPOINTS ARE FULLY OPERATIONAL AND RETURNING 200 OK!")
print("=" * 70)
