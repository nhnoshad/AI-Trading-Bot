"""
Bootstrap Script:
1. Generates valid PNG icons (16x16, 48x48, 128x128) for the Chrome Extension.
2. Seeds >1 Month (35 days) of realistic OHLCV + 28 Technical Indicator data.
3. Trains XGBoost, LightGBM, and Random Forest models and saves .pkl files in models/.
"""

import os
import sys
import struct
import zlib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, BASE_DIR)

from app.services.indicators import calculate_indicators, FEATURE_COLUMNS
from app.services.adaptive_learner import get_adaptive_learner, MEMORY_CSV_PATH


def create_png(width: int, height: int, rgb=(0, 212, 255)) -> bytes:
    """Create a valid minimal RGBA PNG icon with a dark border and glowing center."""
    raw_rows = []
    r, g, b = rgb
    for y in range(height):
        row = bytearray([0])  # filter type 0
        for x in range(width):
            border = (x < 2 or x >= width - 2 or y < 2 or y >= height - 2)
            cx, cy = width / 2.0, height / 2.0
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if border:
                row.extend([0, 255, 136, 255])
            elif dist < width * 0.28:
                row.extend([r, g, b, 255])
            else:
                row.extend([26, 26, 46, 255])
        raw_rows.append(bytes(row))
    raw_data = b''.join(raw_rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(raw_data, 9)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')


def generate_extension_icons():
    assets_dir = os.path.abspath(os.path.join(BASE_DIR, '../chrome-extension/src/assets'))
    os.makedirs(assets_dir, exist_ok=True)
    for sz in (16, 48, 128):
        path = os.path.join(assets_dir, f'icon{sz}.png')
        with open(path, 'wb') as f:
            f.write(create_png(sz, sz))
    print(f'[OK] Generated Chrome Extension icons (16, 48, 128) in {assets_dir}')


def generate_realistic_forex_data(n_samples: int = 3200) -> pd.DataFrame:
    """
    Generates multi-regime, multi-scale OHLCV data (uptrends, downtrends,
    oversold bounces, overbought pullbacks, and range consolidation) so
    all 28 technical indicators cover the full feature space evenly.
    """
    np.random.seed(42)
    closes = [1.08500]
    opens = []
    highs = []
    lows = []
    volumes = []

    momentum = 0.0
    for i in range(n_samples):
        prev_c = closes[-1]
        open_p = prev_c
        # Multi-frequency wave so we get smooth uptrends, downtrends, and ranges
        slow_wave = np.sin(i / 28.0) * 0.00038
        med_wave = np.sin(i / 9.5) * 0.00052
        fast_wave = np.cos(i / 4.2) * 0.00028
        noise = np.random.normal(0, 0.00022)
        delta = slow_wave + med_wave + fast_wave + 0.25 * momentum + noise
        momentum = delta
        close_p = max(0.5000, open_p + delta)
        high_p = max(open_p, close_p) + abs(np.random.normal(0, 0.00018))
        low_p = min(open_p, close_p) - abs(np.random.normal(0, 0.00018))
        vol = float(np.random.randint(600, 2500))

        opens.append(round(open_p, 6))
        highs.append(round(high_p, 6))
        lows.append(round(low_p, 6))
        closes.append(round(close_p, 6))
        volumes.append(vol)

    closes = closes[1:]
    now = datetime.utcnow()
    step_minutes = max(1, int((35 * 24 * 60) / n_samples))
    timestamps = [
        (now - timedelta(minutes=(n_samples - i) * step_minutes)).isoformat()
        for i in range(n_samples)
    ]

    df = pd.DataFrame({
        'timestamp': timestamps,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })
    return df


def compute_balanced_technical_labels(df_feat: pd.DataFrame) -> np.ndarray:
    """
    Computes ground-truth labels (1 = BUY, 0 = SELL) from multi-indicator
    confluence so the ML ensemble learns both:
    - Mean-reversion at true extremes (RSI < 30 / Stoch < 20 / BB < 0.18 -> BUY; RSI > 70 / Stoch > 80 / BB > 0.82 -> SELL)
    - Healthy trend & momentum continuation (EMA 9/21 cross + MACD hist + SMA 50 + RSI 32-68)
    """
    score = np.zeros(len(df_feat), dtype=float)

    rsi14 = df_feat['rsi_14'].values
    stoch_k = df_feat['stoch_k'].values
    bb_pos = df_feat['bb_position'].values
    macd_hist = df_feat['macd_hist'].values
    ema_cross = df_feat['ema_cross'].values
    sma50_rel = df_feat['sma_50'].values
    pc3 = df_feat['price_change_3'].values
    cci = df_feat['cci'].values
    williams = df_feat['williams_r'].values

    # 1. True Oversold / Overbought Reversal Extremes
    score += np.where(rsi14 < 30, 2.2, np.where(rsi14 > 70, -2.2, 0.0))
    score += np.where((rsi14 >= 52) & (rsi14 <= 68), 1.0, 0.0)
    score += np.where((rsi14 >= 32) & (rsi14 <= 48), -1.0, 0.0)

    score += np.where(stoch_k < 20, 1.4, np.where(stoch_k > 80, -1.4, 0.0))
    score += np.where((stoch_k >= 55) & (stoch_k <= 78) & (rsi14 <= 68), 0.6, 0.0)
    score += np.where((stoch_k >= 22) & (stoch_k <= 45) & (rsi14 >= 32), -0.6, 0.0)

    score += np.where(bb_pos < 0.18, 1.5, np.where(bb_pos > 0.82, -1.5, 0.0))
    score += np.where((bb_pos >= 0.52) & (bb_pos <= 0.78) & (rsi14 <= 68), 0.6, 0.0)
    score += np.where((bb_pos >= 0.22) & (bb_pos <= 0.48) & (rsi14 >= 32), -0.6, 0.0)

    # 2. Trend & Momentum Confluence
    score += np.where(macd_hist > 0, 1.3, -1.3)
    score += np.where(ema_cross == 1, 1.2, -1.2)
    score += np.where(sma50_rel > 0.005, 0.7, np.where(sma50_rel < -0.005, -0.7, 0.0))
    score += np.where(pc3 > 0.01, 0.6, np.where(pc3 < -0.01, -0.6, 0.0))
    score += np.where(cci < -100, 0.9, np.where(cci > 100, -0.9, 0.0))
    score += np.where(williams < -80, 0.8, np.where(williams > -20, -0.8, 0.0))

    # Center around median so BUY (1) and SELL (0) are 50/50 balanced
    median_score = float(np.median(score))
    labels = (score >= median_score).astype(int)
    return labels


def main():
    generate_extension_icons()

    data_dir = os.path.join(BASE_DIR, 'data')
    os.makedirs(data_dir, exist_ok=True)
    raw_csv = os.path.join(data_dir, 'EURUSD_1m_yfinance.csv')

    print('[1/3] Creating 35-day (>1 month) historical OHLCV dataset...')
    df_raw = generate_realistic_forex_data(3200)

    print('[2/3] Calculating 28 scale-invariant technical indicators & balanced BUY/SELL labels...')
    df_feat = calculate_indicators(df_raw.to_dict('records'))
    labels = compute_balanced_technical_labels(df_feat)
    df_feat['label'] = labels
    df_raw = df_raw.iloc[:len(df_feat)].copy()
    df_raw['label'] = labels
    df_raw.to_csv(raw_csv, index=False)

    buy_cnt = int((labels == 1).sum())
    sell_cnt = int((labels == 0).sum())
    print(f'      Dataset balance -> BUY: {buy_cnt} ({buy_cnt/len(labels)*100:.1f}%), SELL: {sell_cnt} ({sell_cnt/len(labels)*100:.1f}%)')

    learner = get_adaptive_learner()
    # Clear old unnormalized memory before seeding fresh scale-invariant 35-day dataset
    if os.path.exists(MEMORY_CSV_PATH):
        os.remove(MEMORY_CSV_PATH)
    learner.seed_1month_memory_from_dataframe(df_feat, pair='EURUSD', timeframe='1m')

    print('[3/3] Training XGBoost, LightGBM & Random Forest Ensemble on 1-month memory...')
    res = learner.retrain_from_rolling_memory(db=None)
    print(f'[OK] Training result: {res}')


if __name__ == '__main__':
    main()
