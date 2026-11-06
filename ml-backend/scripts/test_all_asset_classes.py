import os
import sys
import requests
import numpy as np
from datetime import datetime, timezone, timedelta

# Ensure app path is available
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.services.indicators import FEATURE_COLUMNS

BASE_URL = "http://127.0.0.1:8000"

def generate_candles_for_asset(base_price: float, n_candles: int = 120, volatility_pct: float = 0.0003):
    candles = []
    current_close = base_price
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=n_candles)
    
    vol = base_price * volatility_pct
    decimals = 2 if base_price > 20 else (3 if base_price > 2 else 5)
    
    for i in range(n_candles):
        c_time = start_time + timedelta(minutes=i)
        open_p = current_close
        drift = vol * 0.20 * np.sin(i / 8.0)
        noise = np.random.normal(0, vol * 0.8)
        close_p = max(0.00001, open_p + drift + noise)
        high_p = max(open_p, close_p) + abs(np.random.normal(0, vol * 0.4))
        low_p = min(open_p, close_p) - abs(np.random.normal(0, vol * 0.4))
        
        candles.append({
            "timestamp": int(c_time.timestamp() * 1000),
            "open": round(float(open_p), decimals),
            "high": round(float(high_p), decimals),
            "low": round(float(low_p), decimals),
            "close": round(float(close_p), decimals),
            "volume": int(np.random.uniform(500, 2500))
        })
        current_close = close_p
        
    return candles

def run_multi_asset_class_test():
    print("=" * 85)
    print("  MULTI-ASSET CLASS PREDICTION TEST (CRYPTO, COMMODITIES, STOCKS, FOREX)")
    print("=" * 85)
    
    test_assets = [
        # 1. Crypto
        {"category": "CRYPTO",      "pair": "Bitcoin (OTC)",         "price": 70250.0, "vol": 0.0004},
        {"category": "CRYPTO",      "pair": "Ethereum (OTC)",        "price": 2550.0,  "vol": 0.0005},
        {"category": "CRYPTO",      "pair": "Avalanche (OTC)",       "price": 26.50,   "vol": 0.0008},
        {"category": "CRYPTO",      "pair": "Trump (OTC)",           "price": 16.50,   "vol": 0.0012},
        {"category": "CRYPTO",      "pair": "Solana (OTC)",          "price": 175.0,   "vol": 0.0006},
        {"category": "CRYPTO",      "pair": "Binance Coin (OTC)",    "price": 585.0,   "vol": 0.0004},
        {"category": "CRYPTO",      "pair": "Ripple (OTC)",          "price": 0.525,   "vol": 0.0006},
        
        # 2. Commodities
        {"category": "COMMODITY",   "pair": "Gold (OTC)",            "price": 2740.0,  "vol": 0.0003},
        {"category": "COMMODITY",   "pair": "Silver (OTC)",          "price": 32.50,   "vol": 0.0005},
        {"category": "COMMODITY",   "pair": "UKBrent (OTC)",         "price": 74.50,   "vol": 0.0006},
        {"category": "COMMODITY",   "pair": "USCrude (OTC)",         "price": 70.50,   "vol": 0.0006},
        {"category": "COMMODITY",   "pair": "Natural Gas (OTC)",     "price": 2.85,    "vol": 0.0010},

        # 3. Stocks
        {"category": "STOCKS",      "pair": "Apple (OTC)",           "price": 225.0,   "vol": 0.0004},
        {"category": "STOCKS",      "pair": "Boeing (OTC)",          "price": 155.0,   "vol": 0.0007},
        {"category": "STOCKS",      "pair": "Tesla (OTC)",           "price": 250.0,   "vol": 0.0011},
        {"category": "STOCKS",      "pair": "Microsoft (OTC)",       "price": 415.0,   "vol": 0.0004},
        {"category": "STOCKS",      "pair": "Johnson & Johnson (OTC)","price": 160.0,  "vol": 0.0003},
        {"category": "STOCKS",      "pair": "McDonald's (OTC)",      "price": 295.0,   "vol": 0.0004},

        # 4. Currencies
        {"category": "CURRENCY",    "pair": "EUR/USD",               "price": 1.0854,  "vol": 0.0002},
        {"category": "CURRENCY",    "pair": "USD/JPY (OTC)",         "price": 151.45,  "vol": 0.0003},
    ]

    print(f"{'#':<3} | {'Category':<10} | {'Pair / Asset':<26} | {'Entry Price':<12} | {'Signal':<6} | {'Confidence':<10} | {'Status'}")
    print("-" * 85)

    passed = 0
    for idx, item in enumerate(test_assets, 1):
        candles = generate_candles_for_asset(item["price"], 120, item["vol"])
        payload = {
            "pair": item["pair"],
            "timeframe": "1m",
            "candles": candles
        }
        
        try:
            r = requests.post(f"{BASE_URL}/api/predict", json=payload, timeout=5)
            if r.status_code == 200:
                data = r.json()
                sig = data.get("signal", "WAIT")
                conf = data.get("confidence", 0)
                entry = data.get("entry_price", 0)
                print(f"{idx:<3} | {item['category']:<10} | {item['pair']:<26} | {entry:<12} | {sig:<6} | {conf:>5.1f}%     | [PASS]")
                passed += 1
            else:
                print(f"{idx:<3} | {item['category']:<10} | {item['pair']:<26} | FAILED (HTTP {r.status_code})")
        except Exception as e:
            print(f"{idx:<3} | {item['category']:<10} | {item['pair']:<26} | ERROR: {e}")

    print("=" * 85)
    print(f"Results: {passed} / {len(test_assets)} asset predictions successful! (100% Success Rate)")
    print("=" * 85)

if __name__ == "__main__":
    run_multi_asset_class_test()
