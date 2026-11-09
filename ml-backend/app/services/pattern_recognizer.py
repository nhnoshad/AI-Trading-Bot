"""
Quotex & Financial Markets Candlestick Pattern Recognizer Engine
Identifies the world's most famous, high-win-rate Japanese Candlestick & Price Action patterns:
- Morning Star & Evening Star (3-candle High-Probability Reversals)
- Three White Soldiers & Three Black Crows (3-candle Momentum/Continuations)
- Bullish & Bearish Engulfing (2-candle High-Probability Reversals)
- Piercing Line & Dark Cloud Cover (2-candle Reversals)
- Tweezer Bottom & Tweezer Top (2-candle Support/Resistance Reversals)
- Bullish & Bearish Harami / Inside Bar (2-candle Trend Pauses)
- Hammer, Inverted Hammer, Shooting Star, Hanging Man (1-candle Pin Bars)
- Bullish & Bearish Marubozu (1-candle Full-Momentum Expansions)
- Dragonfly & Gravestone Doji (Extreme Shadow Reversals)
- Spinning Top & Classic Doji (Market Indecision / Consolidation)
"""

from typing import List, Dict, Any, Optional
import numpy as np


def detect_candlestick_pattern(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyzes the latest candles and returns the most prominent detected candlestick pattern.
    Candles are expected in chronological order (latest candle is candles[-1]).
    """
    default_res = {
        'pattern_name': 'Normal Price Action',
        'direction': 'NEUTRAL',
        'signal': 'WAIT',
        'reliability': 'LOW',
        'score': 50,
        'type': 'NONE',
        'candles_involved': 1,
        'description': 'Standard market oscillation without extreme candlestick pattern.',
        'action_advice': 'Rely on technical indicators and ML ensemble consensus.'
    }

    if not candles or len(candles) < 3:
        return default_res

    # Extract last 5 candles if available
    recent = candles[-5:] if len(candles) >= 5 else candles
    n = len(recent)

    c0 = recent[-1]  # Most recent candle (current / just closed)
    c1 = recent[-2]  # 1 candle ago
    c2 = recent[-3]  # 2 candles ago
    c3 = recent[-4] if n >= 4 else None
    c4 = recent[-5] if n >= 5 else None

    # Helper function to extract OHLC and candle metrics
    def get_metrics(c):
        o = float(c.get('open', 0))
        h = float(c.get('high', 0))
        l = float(c.get('low', 0))
        cl = float(c.get('close', 0))
        rng = max(h - l, 1e-9)
        body = abs(cl - o)
        upper = h - max(o, cl)
        lower = min(o, cl) - l
        is_bull = cl > o
        is_bear = cl < o
        body_pct = body / rng
        return {
            'open': o, 'high': h, 'low': l, 'close': cl,
            'range': rng, 'body': body, 'upper': upper, 'lower': lower,
            'is_bull': is_bull, 'is_bear': is_bear, 'body_pct': body_pct
        }

    m0 = get_metrics(c0)
    m1 = get_metrics(c1)
    m2 = get_metrics(c2)

    # 10-bar average range for volatility comparison
    avg_range = np.mean([abs(float(c.get('high', 0)) - float(c.get('low', 0))) for c in candles[-10:]])
    if avg_range <= 0:
        avg_range = m0['range']

    # Trend context: compare c2/c1 to earlier candles
    prior_trend = 'FLAT'
    if c4 and c3:
        p_close = float(c4.get('close', 0))
        mid_close = float(c2.get('close', 0))
        if mid_close > p_close * 1.0005:
            prior_trend = 'UP'
        elif mid_close < p_close * 0.9995:
            prior_trend = 'DOWN'

    # ── 0. INSTITUTIONAL LIQUIDITY SWEEP & STOP-HUNT (Smart Money Concepts) ──
    if len(candles) >= 15:
        prev_lows = [float(c.get('low', 0)) for c in candles[-21:-1] if float(c.get('low', 0)) > 0]
        prev_highs = [float(c.get('high', 0)) for c in candles[-21:-1] if float(c.get('high', 0)) > 0]
        if prev_lows and prev_highs:
            lowest_prev = min(prev_lows)
            highest_prev = max(prev_highs)

            # Bullish Liquidity Sweep: Price pierced below lowest support, but rejected with massive lower wick
            if m0['low'] < lowest_prev and m0['close'] >= lowest_prev and (m0['lower'] / m0['range']) >= 0.50:
                return {
                    'pattern_name': 'Bullish Liquidity Sweep (Stop Hunt)',
                    'direction': 'BULLISH',
                    'signal': 'BUY',
                    'reliability': 'VERY HIGH',
                    'score': 96,
                    'type': 'LIQUIDITY_REVERSAL',
                    'candles_involved': 1,
                    'description': 'Institutional Stop Hunt: Market swept retail stop-losses below local support and rejected violently with a massive lower shadow.',
                    'action_advice': 'Ultra-High-Probability CALL (UP) reversal on smart money accumulation.'
                }

            # Bearish Liquidity Sweep: Price pierced above highest resistance, but rejected with massive upper wick
            if m0['high'] > highest_prev and m0['close'] <= highest_prev and (m0['upper'] / m0['range']) >= 0.50:
                return {
                    'pattern_name': 'Bearish Liquidity Sweep (Stop Hunt)',
                    'direction': 'BEARISH',
                    'signal': 'SELL',
                    'reliability': 'VERY HIGH',
                    'score': 96,
                    'type': 'LIQUIDITY_REVERSAL',
                    'candles_involved': 1,
                    'description': 'Institutional Stop Hunt: Market swept breakout buyers above local resistance and rejected violently with a massive upper shadow.',
                    'action_advice': 'Ultra-High-Probability PUT (DOWN) reversal on smart money distribution.'
                }

    # ── 1. THREE-CANDLE PATTERNS (Highest Probability) ──────────────────────

    # A) MORNING STAR (Bullish Reversal)
    # Candle 2: Strong Bearish
    # Candle 1: Small body (Star/Doji) at bottom
    # Candle 0: Strong Bullish closing > 50% into Candle 2's body
    if (m2['is_bear'] and m2['body_pct'] > 0.40 and
        m1['body_pct'] < 0.35 and m1['low'] <= m2['low'] * 1.0005 and
        m0['is_bull'] and m0['close'] >= (m2['close'] + 0.50 * m2['body'])):
        return {
            'pattern_name': 'Morning Star',
            'direction': 'BULLISH',
            'signal': 'BUY',
            'reliability': 'HIGH',
            'score': 94,
            'type': 'REVERSAL',
            'candles_involved': 3,
            'description': 'Famous 3-candle bullish reversal: strong drop halted by indecision star, followed by aggressive buyer surge.',
            'action_advice': 'High-probability CALL (UP) signal on next candle.'
        }

    # B) EVENING STAR (Bearish Reversal)
    # Candle 2: Strong Bullish
    # Candle 1: Small body (Star/Doji) at top
    # Candle 0: Strong Bearish closing < 50% into Candle 2's body
    if (m2['is_bull'] and m2['body_pct'] > 0.40 and
        m1['body_pct'] < 0.35 and m1['high'] >= m2['high'] * 0.9995 and
        m0['is_bear'] and m0['close'] <= (m2['close'] - 0.50 * m2['body'])):
        return {
            'pattern_name': 'Evening Star',
            'direction': 'BEARISH',
            'signal': 'SELL',
            'reliability': 'HIGH',
            'score': 94,
            'type': 'REVERSAL',
            'candles_involved': 3,
            'description': 'Famous 3-candle bearish reversal: strong rally halted by top star, followed by heavy seller rejection.',
            'action_advice': 'High-probability PUT (DOWN) signal on next candle.'
        }

    # C) THREE WHITE SOLDIERS (Bullish Continuation / Reversal)
    # 3 consecutive bullish candles with higher closes, opening within previous body
    if (m2['is_bull'] and m1['is_bull'] and m0['is_bull'] and
        m0['close'] > m1['close'] > m2['close'] and
        m0['open'] >= m1['open'] and m1['open'] >= m2['open'] and
        m0['body_pct'] > 0.45 and m1['body_pct'] > 0.45):
        return {
            'pattern_name': 'Three White Soldiers',
            'direction': 'BULLISH',
            'signal': 'BUY',
            'reliability': 'HIGH',
            'score': 92,
            'type': 'MOMENTUM',
            'candles_involved': 3,
            'description': '3 consecutive strong green candles with higher highs & closes, demonstrating relentless buying pressure.',
            'action_advice': 'Strong CALL (UP) trend continuation.'
        }

    # D) THREE BLACK CROWS (Bearish Continuation / Reversal)
    # 3 consecutive bearish candles with lower closes, opening within previous body
    if (m2['is_bear'] and m1['is_bear'] and m0['is_bear'] and
        m0['close'] < m1['close'] < m2['close'] and
        m0['open'] <= m1['open'] and m1['open'] <= m2['open'] and
        m0['body_pct'] > 0.45 and m1['body_pct'] > 0.45):
        return {
            'pattern_name': 'Three Black Crows',
            'direction': 'BEARISH',
            'signal': 'SELL',
            'reliability': 'HIGH',
            'score': 92,
            'type': 'MOMENTUM',
            'candles_involved': 3,
            'description': '3 consecutive strong red candles with lower lows & closes, confirming overwhelming seller domination.',
            'action_advice': 'Strong PUT (DOWN) trend continuation.'
        }

    # ── 2. TWO-CANDLE PATTERNS ──────────────────────────────────────────────

    # A) BULLISH ENGULFING
    # Current green candle body engulfs previous red candle body
    if (m1['is_bear'] and m0['is_bull'] and
        m0['close'] >= m1['open'] and m0['open'] <= m1['close'] and
        m0['body'] > m1['body'] * 1.05 and m0['body_pct'] > 0.50):
        return {
            'pattern_name': 'Bullish Engulfing',
            'direction': 'BULLISH',
            'signal': 'BUY',
            'reliability': 'HIGH',
            'score': 88,
            'type': 'REVERSAL',
            'candles_involved': 2,
            'description': 'Bullish Engulfing: buyers completely swallowed the previous drop, signalling aggressive trend reversal.',
            'action_advice': 'High-confidence CALL (UP) reversal trade.'
        }

    # B) BEARISH ENGULFING
    # Current red candle body engulfs previous green candle body
    if (m1['is_bull'] and m0['is_bear'] and
        m0['close'] <= m1['open'] and m0['open'] >= m1['close'] and
        m0['body'] > m1['body'] * 1.05 and m0['body_pct'] > 0.50):
        return {
            'pattern_name': 'Bearish Engulfing',
            'direction': 'BEARISH',
            'signal': 'SELL',
            'reliability': 'HIGH',
            'score': 88,
            'type': 'REVERSAL',
            'candles_involved': 2,
            'description': 'Bearish Engulfing: sellers completely swallowed the previous rally, signalling aggressive trend reversal.',
            'action_advice': 'High-confidence PUT (DOWN) reversal trade.'
        }

    # C) PIERCING LINE (Bullish Reversal)
    # Candle 1 bearish, Candle 0 opens low and closes > 50% into Candle 1 body
    if (m1['is_bear'] and m0['is_bull'] and
        m0['open'] <= m1['close'] and
        m0['close'] > (m1['close'] + 0.50 * m1['body']) and
        m0['close'] < m1['open']):
        return {
            'pattern_name': 'Piercing Line',
            'direction': 'BULLISH',
            'signal': 'BUY',
            'reliability': 'MEDIUM_HIGH',
            'score': 82,
            'type': 'REVERSAL',
            'candles_involved': 2,
            'description': 'Piercing Line: buyers drove price more than halfway back up into the previous bearish candle.',
            'action_advice': 'Reliable CALL (UP) entry on support confirmation.'
        }

    # D) DARK CLOUD COVER (Bearish Reversal)
    # Candle 1 bullish, Candle 0 opens high and closes < 50% into Candle 1 body
    if (m1['is_bull'] and m0['is_bear'] and
        m0['open'] >= m1['close'] and
        m0['close'] < (m1['close'] - 0.50 * m1['body']) and
        m0['close'] > m1['open']):
        return {
            'pattern_name': 'Dark Cloud Cover',
            'direction': 'BEARISH',
            'signal': 'SELL',
            'reliability': 'MEDIUM_HIGH',
            'score': 82,
            'type': 'REVERSAL',
            'candles_involved': 2,
            'description': 'Dark Cloud Cover: sellers penetrated deep into previous bull candle from the peak.',
            'action_advice': 'Reliable PUT (DOWN) entry on resistance confirmation.'
        }

    # E) TWEEZER BOTTOM (Matching Support Lows)
    # Lows match within 0.05%
    if (abs(m0['low'] - m1['low']) <= (m0['close'] * 0.0005) and
        (m1['is_bear'] or m1['lower'] > m1['body']) and
        (m0['is_bull'] or m0['lower'] > m0['body'])):
        return {
            'pattern_name': 'Tweezer Bottom',
            'direction': 'BULLISH',
            'signal': 'BUY',
            'reliability': 'MEDIUM_HIGH',
            'score': 80,
            'type': 'REVERSAL',
            'candles_involved': 2,
            'description': 'Tweezer Bottom: two consecutive candles tested identical price lows, forming a rock-solid support floor.',
            'action_advice': 'High-probability CALL (UP) bounce off support.'
        }

    # F) TWEEZER TOP (Matching Resistance Highs)
    # Highs match within 0.05%
    if (abs(m0['high'] - m1['high']) <= (m0['close'] * 0.0005) and
        (m1['is_bull'] or m1['upper'] > m1['body']) and
        (m0['is_bear'] or m0['upper'] > m0['body'])):
        return {
            'pattern_name': 'Tweezer Top',
            'direction': 'BEARISH',
            'signal': 'SELL',
            'reliability': 'MEDIUM_HIGH',
            'score': 80,
            'type': 'REVERSAL',
            'candles_involved': 2,
            'description': 'Tweezer Top: two consecutive candles rejected identical price highs, forming a heavy resistance ceiling.',
            'action_advice': 'High-probability PUT (DOWN) rejection off ceiling.'
        }

    # G) BULLISH HARAMI / INSIDE BAR
    if (m1['is_bear'] and m0['is_bull'] and
        m0['open'] >= m1['close'] and m0['close'] <= m1['open'] and
        m0['body'] < m1['body'] * 0.70):
        return {
            'pattern_name': 'Bullish Harami (Inside Bar)',
            'direction': 'BULLISH',
            'signal': 'BUY',
            'reliability': 'MEDIUM',
            'score': 74,
            'type': 'REVERSAL',
            'candles_involved': 2,
            'description': 'Bullish Harami: selling pressure abruptly stalled; inside bar signals impending bullish breakout.',
            'action_advice': 'Prepare CALL (UP) trade as buyers break above inside high.'
        }

    # H) BEARISH HARAMI / INSIDE BAR
    if (m1['is_bull'] and m0['is_bear'] and
        m0['open'] <= m1['close'] and m0['close'] >= m1['open'] and
        m0['body'] < m1['body'] * 0.70):
        return {
            'pattern_name': 'Bearish Harami (Inside Bar)',
            'direction': 'BEARISH',
            'signal': 'SELL',
            'reliability': 'MEDIUM',
            'score': 74,
            'type': 'REVERSAL',
            'candles_involved': 2,
            'description': 'Bearish Harami: buying pressure abruptly halted; inside bar signals impending bearish breakdown.',
            'action_advice': 'Prepare PUT (DOWN) trade as sellers break below inside low.'
        }

    # ── 3. SINGLE-CANDLE PIN BARS & MOMENTUM EXPANSIONS ─────────────────────

    # A) HAMMER (Bullish Reversal / Pin Bar)
    # Long lower shadow (>= 2x body), small upper shadow (<= 0.35x body)
    if (m0['lower'] >= 2.0 * m0['body'] and
        m0['upper'] <= 0.35 * m0['body'] and
        m0['body'] > 0 and
        m0['body_pct'] <= 0.35):
        return {
            'pattern_name': 'Hammer (Bullish Pin Bar)',
            'direction': 'BULLISH',
            'signal': 'BUY',
            'reliability': 'MEDIUM_HIGH',
            'score': 82,
            'type': 'REVERSAL',
            'candles_involved': 1,
            'description': 'Hammer / Bullish Pin Bar: sellers plunged price downward but buyers violently rejected lows to close near highs.',
            'action_advice': 'CALL (UP) trade on price rejection of key support.'
        }

    # B) SHOOTING STAR (Bearish Reversal / Pin Bar)
    # Long upper shadow (>= 2x body), small lower shadow (<= 0.35x body)
    if (m0['upper'] >= 2.0 * m0['body'] and
        m0['lower'] <= 0.35 * m0['body'] and
        m0['body'] > 0 and
        m0['body_pct'] <= 0.35):
        return {
            'pattern_name': 'Shooting Star (Bearish Pin Bar)',
            'direction': 'BEARISH',
            'signal': 'SELL',
            'reliability': 'MEDIUM_HIGH',
            'score': 82,
            'type': 'REVERSAL',
            'candles_involved': 1,
            'description': 'Shooting Star / Bearish Pin Bar: buyers rallied price upward but sellers slammed it back down to close near lows.',
            'action_advice': 'PUT (DOWN) trade on price rejection of resistance.'
        }

    # C) INVERTED HAMMER (Bullish Reversal Attempt)
    if (m0['upper'] >= 2.0 * m0['body'] and
        m0['lower'] <= 0.20 * m0['range'] and
        m1['is_bear']):
        return {
            'pattern_name': 'Inverted Hammer',
            'direction': 'BULLISH',
            'signal': 'BUY',
            'reliability': 'MEDIUM',
            'score': 75,
            'type': 'REVERSAL',
            'candles_involved': 1,
            'description': 'Inverted Hammer: buyers tested higher prices following a decline; seller exhaustion imminent.',
            'action_advice': 'Monitor CALL (UP) continuation if next tick holds above open.'
        }

    # D) HANGING MAN (Bearish Reversal Warning at Highs)
    if (m0['lower'] >= 2.0 * m0['body'] and
        m0['upper'] <= 0.20 * m0['range'] and
        m1['is_bull']):
        return {
            'pattern_name': 'Hanging Man',
            'direction': 'BEARISH',
            'signal': 'SELL',
            'reliability': 'MEDIUM',
            'score': 75,
            'type': 'REVERSAL',
            'candles_involved': 1,
            'description': 'Hanging Man: sudden intraday selloff at recent highs warning that buyer support is deteriorating.',
            'action_advice': 'Caution on long positions; potential PUT (DOWN) reversal.'
        }

    # E) BULLISH MARUBOZU (Full Momentum Expansion)
    # Strong green body > 85% of candle range and above-average range
    if (m0['is_bull'] and m0['body_pct'] >= 0.85 and m0['range'] >= avg_range * 0.90):
        return {
            'pattern_name': 'Bullish Marubozu',
            'direction': 'BULLISH',
            'signal': 'BUY',
            'reliability': 'HIGH',
            'score': 86,
            'type': 'MOMENTUM',
            'candles_involved': 1,
            'description': 'Bullish Marubozu: pure buyer domination with no wicks from open to close; powerful upward momentum.',
            'action_advice': 'Strong CALL (UP) trend ride.'
        }

    # F) BEARISH MARUBOZU (Full Momentum Expansion)
    # Strong red body > 85% of candle range and above-average range
    if (m0['is_bear'] and m0['body_pct'] >= 0.85 and m0['range'] >= avg_range * 0.90):
        return {
            'pattern_name': 'Bearish Marubozu',
            'direction': 'BEARISH',
            'signal': 'SELL',
            'reliability': 'HIGH',
            'score': 86,
            'type': 'MOMENTUM',
            'candles_involved': 1,
            'description': 'Bearish Marubozu: pure seller domination with no wicks from open to close; powerful downward momentum.',
            'action_advice': 'Strong PUT (DOWN) trend ride.'
        }

    # G) DRAGONFLY DOJI (Bullish Reversal)
    if (m0['body_pct'] <= 0.08 and m0['lower'] >= 0.70 * m0['range'] and m0['upper'] <= 0.10 * m0['range']):
        return {
            'pattern_name': 'Dragonfly Doji',
            'direction': 'BULLISH',
            'signal': 'BUY',
            'reliability': 'MEDIUM_HIGH',
            'score': 80,
            'type': 'REVERSAL',
            'candles_involved': 1,
            'description': 'Dragonfly Doji: extreme seller rejection at the lows; buyers pulled price all the way back to open.',
            'action_advice': 'Bullish CALL (UP) bounce setup.'
        }

    # H) GRAVESTONE DOJI (Bearish Reversal)
    if (m0['body_pct'] <= 0.08 and m0['upper'] >= 0.70 * m0['range'] and m0['lower'] <= 0.10 * m0['range']):
        return {
            'pattern_name': 'Gravestone Doji',
            'direction': 'BEARISH',
            'signal': 'SELL',
            'reliability': 'MEDIUM_HIGH',
            'score': 80,
            'type': 'REVERSAL',
            'candles_involved': 1,
            'description': 'Gravestone Doji: extreme buyer rejection at the highs; sellers crushed price back down to open.',
            'action_advice': 'Bearish PUT (DOWN) tumble setup.'
        }

    # I) SPINNING TOP / CLASSIC DOJI (Indecision)
    if (m0['body_pct'] <= 0.15 and m0['upper'] >= 0.25 * m0['range'] and m0['lower'] >= 0.25 * m0['range']):
        return {
            'pattern_name': 'Spinning Top / Doji',
            'direction': 'NEUTRAL',
            'signal': 'WAIT',
            'reliability': 'MEDIUM',
            'score': 65,
            'type': 'INDECISION',
            'candles_involved': 1,
            'description': 'Spinning Top: complete tug-of-war balance between buyers and sellers with no directional winner.',
            'action_advice': 'Wait for clear breakout candle before entering trade.'
        }

    return default_res
