"""
Quotex Algorithmic Market Engine
Reverse-engineered market dynamics for Quotex binary options (1m & 5m charts):
1. Ornstein-Uhlenbeck (O-U) Mean-Reverting Equilibrium Model:
   - Quotex OTC prices revert to local equilibrium (EMA 20) when stretched beyond 2.0x ATR.
2. Market Regime Filter (Trend vs Range):
   - In Trend (ADX >= 25): Momentum continuation holds; Stochastic > 80 is NOT sell, but strong trend.
   - In Range (ADX < 20): Mean-reversion at Bollinger Bands & S/R levels.
3. Quotex 3-to-5 Bar Run Exhaustion:
   - Reversal probability spikes when consecutive candles >= 3 and rejection wick forms.
4. Psychological Round Number Rejection (.000, .500, .200, .800):
   - Quotex algorithmic pricing respects major round grid levels.
5. Wick Rejection & Absorption Ratio:
   - Upper shadow >= 40% range at resistance -> Institutional seller rejection (PUT).
   - Lower shadow >= 40% range at support -> Institutional buyer defense (CALL).
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np
import pandas as pd


def detect_psychological_levels(price: float, pair: str = 'EURUSD') -> Dict[str, Any]:
    """
    Identifies nearest Quotex round psychological grid numbers and evaluates proximity/rejection.
    """
    if price <= 0:
        return {'near_round_level': False, 'level': price, 'distance_pips': 999.0, 'bias': 'NEUTRAL'}

    # Determine grid spacing based on asset scale
    if price > 1000:       # Bitcoin, Gold, Ethereum
        grid = 50.0 if price > 10000 else 10.0
    elif price > 100:      # Stocks, BNB, Sol, JPY pairs
        grid = 1.0 if price > 200 else 0.50
    elif price > 5:        # Toncoin, Avalanche, Oil
        grid = 0.10
    else:                  # Currencies (1.08500, 1.28000, etc.)
        grid = 0.0050      # Every 50 pips (e.g. 1.0800, 1.0850, 1.0900)

    lower_level = np.floor(price / grid) * grid
    upper_level = lower_level + grid
    dist_lower = abs(price - lower_level)
    dist_upper = abs(price - upper_level)

    nearest = lower_level if dist_lower < dist_upper else upper_level
    dist = min(dist_lower, dist_upper)
    dist_pct = dist / price * 100.0

    # Near round number threshold: within 0.03% of price
    is_near = dist_pct <= 0.04

    bias = 'NEUTRAL'
    if is_near:
        if nearest >= price:
            bias = 'RESISTANCE'  # Price pushing up into round ceiling
        else:
            bias = 'SUPPORT'     # Price plunging down into round floor

    return {
        'near_round_level': bool(is_near),
        'nearest_level': round(float(nearest), 5),
        'distance_pct': round(float(dist_pct), 4),
        'bias': str(bias)
    }


def analyze_quotex_algorithm_dynamics(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyzes candle series for Quotex algorithmic market behavior:
    - Market Regime: TRENDING / RANGING / CHOPPY / EXHAUSTED
    - Ornstein-Uhlenbeck z-score (Mean-reversion tension)
    - Consecutive bar exhaustion (3-5 bar trap)
    - Wick rejection absorption
    - Psychological round level confluence
    """
    default_res = {
        'regime': 'RANGING',
        'quotex_bias': 'WAIT',
        'confidence_adjustment': 0.0,
        'exhaustion_risk': False,
        'wick_rejection': 'NONE',
        'ou_z_score': 0.0,
        'round_level_info': {'near_round_level': False, 'bias': 'NEUTRAL'},
        'sniper_verdict': 'WAIT',
        'reasons': []
    }

    if not candles or len(candles) < 20:
        return default_res

    df = pd.DataFrame(candles)
    for col in ('open', 'high', 'low', 'close'):
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.dropna(subset=['open', 'high', 'low', 'close'], inplace=True)
    if len(df) < 20:
        return default_res

    c_cur = df.iloc[-1]
    c_prev = df.iloc[-2]
    c_prev2 = df.iloc[-3] if len(df) >= 3 else c_prev

    close = float(c_cur['close'])
    open_p = float(c_cur['open'])
    high = float(c_cur['high'])
    low = float(c_cur['low'])
    rng = max(high - low, 1e-9)
    body = abs(close - open_p)
    upper_wick = high - max(open_p, close)
    lower_wick = min(open_p, close) - low

    # 1. 20-period EMA & ATR for Ornstein-Uhlenbeck Mean Reversion
    ema20 = float(df['close'].ewm(span=20, adjust=False).mean().iloc[-1])
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs()
    ], axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1])
    if atr14 <= 0:
        atr14 = rng

    # O-U tension z-score: how far is price from EMA20 in units of ATR?
    ou_z = (close - ema20) / (atr14 + 1e-9)

    # 2. ADX calculation for Market Regime
    high_diff = df['high'].diff()
    low_diff = -df['low'].diff()
    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)
    plus_di = 100 * plus_dm.rolling(14).mean() / (tr.rolling(14).mean() + 1e-9)
    minus_di = 100 * minus_dm.rolling(14).mean() / (tr.rolling(14).mean() + 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    adx_series = dx.rolling(14).mean()
    adx = float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else 20.0

    # 3. Consecutive candles in same direction (Quotex Micro-Trend)
    consec = 1
    direction = 1 if close > open_p else (-1 if close < open_p else 0)
    for i in range(len(df) - 2, max(-1, len(df) - 7), -1):
        prev_dir = 1 if df.iloc[i]['close'] > df.iloc[i]['open'] else (-1 if df.iloc[i]['close'] < df.iloc[i]['open'] else 0)
        if prev_dir == direction and direction != 0:
            consec += 1
        else:
            break

    # 4. Wick Rejection Analysis
    upper_wick_ratio = upper_wick / rng
    lower_wick_ratio = lower_wick / rng
    wick_rejection = 'NONE'
    if upper_wick_ratio >= 0.40 and body <= 0.40 * rng:
        wick_rejection = 'BEARISH_REJECTION'  # Buyers pushed high, Quotex slammed price down
    elif lower_wick_ratio >= 0.40 and body <= 0.40 * rng:
        wick_rejection = 'BULLISH_REJECTION'  # Sellers pushed low, Quotex bought price back

    # 5. Psychological Round Number S/R
    round_info = detect_psychological_levels(close)

    # 6. Regime Classification
    reasons = []
    confidence_adj = 0.0
    quotex_bias = 'WAIT'
    exhaustion_risk = False

    # A) EXHAUSTION TRAP (Quotex 3-to-5 Bar Run Reversal)
    if consec >= 3:
        if direction == 1:
            # 3+ green candles into high or upper wick -> Quotex exhaustion
            if upper_wick_ratio >= 0.35 or ou_z > 1.8 or round_info['bias'] == 'RESISTANCE':
                exhaustion_risk = True
                quotex_bias = 'SELL'
                confidence_adj += 0.04
                reasons.append(f"Quotex {consec}-bar Bullish run exhaustion + Upper wick rejection (Mean-Reversion PUT setup)")
        elif direction == -1:
            # 3+ red candles into low or lower wick -> Quotex exhaustion
            if lower_wick_ratio >= 0.35 or ou_z < -1.8 or round_info['bias'] == 'SUPPORT':
                exhaustion_risk = True
                quotex_bias = 'BUY'
                confidence_adj += 0.04
                reasons.append(f"Quotex {consec}-bar Bearish run exhaustion + Lower wick defense (Mean-Reversion CALL setup)")

    # B) STRONG TREND REGIME (ADX >= 25)
    if adx >= 25 and not exhaustion_risk:
        regime = 'TRENDING'
        # In a healthy trend (consec <= 2), follow the trend
        if direction == 1 and ou_z > 0.3 and lower_wick_ratio <= 0.30:
            quotex_bias = 'BUY'
            confidence_adj += 0.035
            reasons.append(f"Quotex Momentum Trend continuation (ADX {adx:.1f} >= 25)")
        elif direction == -1 and ou_z < -0.3 and upper_wick_ratio <= 0.30:
            quotex_bias = 'SELL'
            confidence_adj += 0.035
            reasons.append(f"Quotex Bearish Momentum Trend continuation (ADX {adx:.1f} >= 25)")
    elif exhaustion_risk:
        regime = 'EXHAUSTION_ZONE'
    elif adx < 18:
        regime = 'CHOPPY_SIDEWAYS'
        # In chop, penalize trade unless strong wick rejection off round level
        if round_info['near_round_level'] and wick_rejection != 'NONE':
            if wick_rejection == 'BULLISH_REJECTION':
                quotex_bias = 'BUY'
                confidence_adj += 0.03
                reasons.append(f"Quotex Support bounce at round level {round_info['nearest_level']}")
            elif wick_rejection == 'BEARISH_REJECTION':
                quotex_bias = 'SELL'
                confidence_adj += 0.03
                reasons.append(f"Quotex Resistance rejection at round level {round_info['nearest_level']}")
        else:
            quotex_bias = 'WAIT'
            confidence_adj -= 0.06
            reasons.append(f"Quotex Choppy Market (ADX {adx:.1f} < 18) — high random noise, avoiding trade")
    else:
        regime = 'RANGING'
        # O-U Extreme Reversion
        if ou_z > 2.0 and wick_rejection == 'BEARISH_REJECTION':
            quotex_bias = 'SELL'
            confidence_adj += 0.035
            reasons.append(f"Quotex O-U extreme stretch (z={ou_z:.2f}) + Bearish rejection")
        elif ou_z < -2.0 and wick_rejection == 'BULLISH_REJECTION':
            quotex_bias = 'BUY'
            confidence_adj += 0.035
            reasons.append(f"Quotex O-U extreme oversold (z={ou_z:.2f}) + Bullish defense")

    return {
        'regime': str(regime),
        'quotex_bias': str(quotex_bias),
        'confidence_adjustment': round(float(confidence_adj), 4),
        'exhaustion_risk': bool(exhaustion_risk),
        'consecutive_bars': int(consec),
        'wick_rejection': str(wick_rejection),
        'ou_z_score': round(float(ou_z), 2),
        'adx': round(float(adx), 1),
        'round_level_info': round_info,
        'reasons': reasons
    }
