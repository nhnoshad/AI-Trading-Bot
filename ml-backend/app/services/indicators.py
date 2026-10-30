import pandas as pd
import numpy as np
from typing import List, Dict, Any

try:
    import ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False


def calculate_indicators(candles: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Calculate all 28 technical indicators from OHLCV candle data.
    Returns a DataFrame with all features.
    """
    if len(candles) < 50:
        raise ValueError(f'Need at least 50 candles, got {len(candles)}')

    df = pd.DataFrame(candles)
    # Normalise column names
    df.columns = [c.lower() for c in df.columns]
    required = ['open', 'high', 'low', 'close']
    for col in required:
        if col not in df.columns:
            raise ValueError(f'Missing required column: {col}')

    df['open'] = pd.to_numeric(df['open'], errors='coerce')
    df['high'] = pd.to_numeric(df['high'], errors='coerce')
    df['low'] = pd.to_numeric(df['low'], errors='coerce')
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    if 'volume' not in df.columns:
        df['volume'] = 1000.0
    else:
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(1000.0)
    df.dropna(subset=['open', 'high', 'low', 'close'], inplace=True)

    # ── MOMENTUM ────────────────────────────────────────────────────────────
    delta = df['close'].diff()
    gain14 = delta.clip(lower=0).rolling(14).mean()
    loss14 = (-delta.clip(upper=0)).rolling(14).mean()
    rs14 = gain14 / (loss14 + 1e-9)
    df['rsi_14'] = 100 - 100 / (1 + rs14)

    gain7 = delta.clip(lower=0).rolling(7).mean()
    loss7 = (-delta.clip(upper=0)).rolling(7).mean()
    rs7 = gain7 / (loss7 + 1e-9)
    df['rsi_7'] = 100 - 100 / (1 + rs7)

    low14 = df['low'].rolling(14).min()
    high14 = df['high'].rolling(14).max()
    df['stoch_k'] = 100 * (df['close'] - low14) / (high14 - low14 + 1e-9)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()

    df['williams_r'] = -100 * (high14 - df['close']) / (high14 - low14 + 1e-9)

    tp = (df['high'] + df['low'] + df['close']) / 3
    tp_sma = tp.rolling(20).mean()
    tp_std = tp.rolling(20).std()
    df['cci'] = (tp - tp_sma) / (0.015 * tp_std + 1e-9)

    # ── TREND (Scale-invariant % relative to close price) ────────────────────
    close_safe = df['close'].abs().clip(lower=1e-6)
    ema9_raw = df['close'].ewm(span=9, adjust=False).mean()
    ema21_raw = df['close'].ewm(span=21, adjust=False).mean()
    sma50_raw = df['close'].rolling(50).mean()

    df['ema_9'] = (df['close'] - ema9_raw) / close_safe * 100.0
    df['ema_21'] = (df['close'] - ema21_raw) / close_safe * 100.0
    df['sma_50'] = (df['close'] - sma50_raw) / close_safe * 100.0

    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd_line'] = (ema12 - ema26) / close_safe * 100.0
    df['macd_signal'] = df['macd_line'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd_line'] - df['macd_signal']

    df['ema_cross'] = (ema9_raw > ema21_raw).astype(int)

    # ADX
    high_diff = df['high'].diff()
    low_diff = -df['low'].diff()
    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs()
    ], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    plus_di = 100 * plus_dm.rolling(14).mean() / (atr14 + 1e-9)
    minus_di = 100 * minus_dm.rolling(14).mean() / (atr14 + 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    df['adx'] = dx.rolling(14).mean()

    # ── VOLATILITY ───────────────────────────────────────────────────────────
    sma20 = df['close'].rolling(20).mean()
    std20 = df['close'].rolling(20).std()
    upper_bb = sma20 + 2 * std20
    lower_bb = sma20 - 2 * std20
    df['bb_width'] = (upper_bb - lower_bb) / (sma20 + 1e-9)
    df['bb_position'] = (df['close'] - lower_bb) / (upper_bb - lower_bb + 1e-9)
    df['atr_14'] = atr14 / close_safe * 100.0

    # ── PRICE ACTION ─────────────────────────────────────────────────────────
    df['price_change_1'] = df['close'].pct_change(1) * 100
    df['price_change_3'] = df['close'].pct_change(3) * 100
    df['price_change_5'] = df['close'].pct_change(5) * 100
    candle_range = df['high'] - df['low']
    df['candle_body_ratio'] = (df['close'] - df['open']).abs() / (candle_range + 1e-9)

    # ── CANDLE PATTERN ───────────────────────────────────────────────────────
    body = (df['close'] - df['open']).abs()
    upper_wick_raw = df['high'] - df[['open', 'close']].max(axis=1)
    lower_wick_raw = df[['open', 'close']].min(axis=1) - df['low']
    df['body_size'] = body / close_safe * 100.0
    df['upper_wick'] = upper_wick_raw / close_safe * 100.0
    df['lower_wick'] = lower_wick_raw / close_safe * 100.0
    df['is_doji'] = (body < 0.1 * candle_range).astype(int)
    df['is_hammer'] = (
        (lower_wick_raw > 2 * body) &
        (upper_wick_raw < body) &
        (body > 0)
    ).astype(int)

    # Engulfing: current candle body engulfs previous candle body
    prev_body_start = df['open'].shift(1)
    prev_body_end = df['close'].shift(1)
    curr_bullish = df['close'] > df['open']
    curr_bearish = df['close'] < df['open']
    prev_bearish = prev_body_start > prev_body_end  # prev close < prev open
    prev_bullish = prev_body_end > prev_body_start
    bull_engulf = curr_bullish & prev_bearish & (df['open'] < df['close'].shift(1)) & (df['close'] > df['open'].shift(1))
    bear_engulf = curr_bearish & prev_bullish & (df['open'] > df['close'].shift(1)) & (df['close'] < df['open'].shift(1))
    df['is_engulfing'] = (bull_engulf | bear_engulf).astype(int)

    direction = (df['close'] > df['open']).astype(int)
    consec = []
    count = 0
    prev_dir = None
    for d in direction:
        if d == prev_dir:
            count += 1
        else:
            count = 1
            prev_dir = d
        consec.append(count)
    df['consecutive_same_direction'] = consec

    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.fillna(0, inplace=True)
    return df


FEATURE_COLUMNS = [
    'rsi_14', 'rsi_7', 'stoch_k', 'stoch_d', 'williams_r', 'cci',
    'ema_9', 'ema_21', 'sma_50', 'macd_line', 'macd_signal', 'macd_hist',
    'ema_cross', 'adx', 'bb_width', 'bb_position', 'atr_14',
    'price_change_1', 'price_change_3', 'price_change_5', 'candle_body_ratio',
    'body_size', 'upper_wick', 'lower_wick', 'is_doji', 'is_hammer',
    'is_engulfing', 'consecutive_same_direction'
]


def get_indicator_signals(row: pd.Series) -> Dict[str, Dict]:
    """Return a human-readable interpretation of each indicator for the latest row."""
    signals = {}

    rsi = row.get('rsi_14', 50)
    if rsi < 30:
        rsi_sig = 'OVERSOLD_BUY'
    elif rsi > 70:
        rsi_sig = 'OVERBOUGHT_SELL'
    elif rsi >= 52:
        rsi_sig = 'BULLISH_BUY'
    elif rsi <= 48:
        rsi_sig = 'BEARISH_SELL'
    else:
        rsi_sig = 'NEUTRAL'
    signals['rsi_14'] = {'value': round(float(rsi), 2), 'signal': rsi_sig}

    rsi7 = row.get('rsi_7', 50)
    if rsi7 < 25:
        r7s = 'OVERSOLD_BUY'
    elif rsi7 > 75:
        r7s = 'OVERBOUGHT_SELL'
    else:
        r7s = 'NEUTRAL'
    signals['rsi_7'] = {'value': round(float(rsi7), 2), 'signal': r7s}

    macd_hist = row.get('macd_hist', 0)
    signals['macd'] = {
        'value': 'bullish_cross' if macd_hist > 0 else 'bearish_cross',
        'signal': 'BUY' if macd_hist > 0 else 'SELL'
    }

    bb_pos = row.get('bb_position', 0.5)
    if bb_pos < 0.2:
        bb_sig = 'BUY'
    elif bb_pos > 0.8:
        bb_sig = 'SELL'
    else:
        bb_sig = 'NEUTRAL'
    signals['bb'] = {'value': round(float(bb_pos), 3), 'signal': bb_sig}

    ema_cross = row.get('ema_cross', 0)
    signals['ema_cross'] = {
        'value': 'bullish' if ema_cross == 1 else 'bearish',
        'signal': 'BUY' if ema_cross == 1 else 'SELL'
    }

    stoch = row.get('stoch_k', 50)
    if stoch < 20:
        st_sig = 'OVERSOLD_BUY'
    elif stoch > 80:
        st_sig = 'OVERBOUGHT_SELL'
    elif stoch >= 55 and rsi <= 68:
        st_sig = 'BULLISH_BUY'
    elif stoch <= 45 and rsi >= 32:
        st_sig = 'BEARISH_SELL'
    else:
        st_sig = 'NEUTRAL'
    signals['stochastic'] = {'value': round(float(stoch), 2), 'signal': st_sig}

    adx = row.get('adx', 0)
    signals['adx'] = {'value': round(float(adx), 2), 'signal': 'STRONG_TREND' if adx > 25 else 'WEAK_TREND'}

    return signals


def generate_reasons(indicator_signals: Dict, prediction: int, confidence: float) -> List[str]:
    """Generate human-readable reasons for the signal."""
    reasons = []
    direction = 'BUY' if prediction == 1 else 'SELL'

    rsi_info = indicator_signals.get('rsi_14', {})
    rsi_sig = rsi_info.get('signal', '')
    if rsi_sig == 'OVERSOLD_BUY' and direction == 'BUY':
        reasons.append(f"RSI oversold bounce at {rsi_info['value']} (below 30)")
    elif rsi_sig == 'OVERBOUGHT_SELL' and direction == 'SELL':
        reasons.append(f"RSI overbought pullback at {rsi_info['value']} (above 70)")
    elif rsi_sig == 'BULLISH_BUY' and direction == 'BUY':
        reasons.append(f"RSI bullish momentum at {rsi_info['value']}")
    elif rsi_sig == 'BEARISH_SELL' and direction == 'SELL':
        reasons.append(f"RSI bearish momentum at {rsi_info['value']}")

    macd_info = indicator_signals.get('macd', {})
    if macd_info.get('signal') == direction:
        reasons.append(f"MACD {macd_info['value']} detected")

    ema_info = indicator_signals.get('ema_cross', {})
    if ema_info.get('signal') == direction:
        reasons.append(f"EMA 9 {'above' if direction == 'BUY' else 'below'} EMA 21 ({ema_info['value']} trend)")

    bb_info = indicator_signals.get('bb', {})
    if bb_info.get('signal') == direction:
        pos = bb_info['value']
        reasons.append(f"Price {'near lower' if pos < 0.2 else 'near upper'} Bollinger Band")

    stoch_info = indicator_signals.get('stochastic', {})
    st_sig = stoch_info.get('signal', '')
    if st_sig == 'OVERSOLD_BUY' and direction == 'BUY':
        reasons.append(f"Stochastic oversold reversal at {stoch_info['value']}")
    elif st_sig == 'OVERBOUGHT_SELL' and direction == 'SELL':
        reasons.append(f"Stochastic overbought reversal at {stoch_info['value']}")
    elif st_sig == 'BULLISH_BUY' and direction == 'BUY':
        reasons.append(f"Stochastic upward momentum at {stoch_info['value']}")
    elif st_sig == 'BEARISH_SELL' and direction == 'SELL':
        reasons.append(f"Stochastic downward momentum at {stoch_info['value']}")

    if not reasons:
        reasons.append(f"ML ensemble model confidence: {confidence:.1f}%")

    return reasons
