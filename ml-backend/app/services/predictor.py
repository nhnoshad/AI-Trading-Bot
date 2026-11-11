import os
import time
import json
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.services.indicators import (
    calculate_indicators, FEATURE_COLUMNS,
    get_indicator_signals, generate_reasons
)
from app.services.pattern_recognizer import detect_candlestick_pattern
from app.services.quotex_engine import analyze_quotex_algorithm_dynamics
from app.services.adaptive_learner import get_adaptive_learner
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
MODELS_DIR = os.path.join(BASE_DIR, 'models')
PAIR_DATA_DIR = os.path.join(BASE_DIR, 'data', 'pair_datasets')
os.makedirs(PAIR_DATA_DIR, exist_ok=True)


class TradingPredictor:
    """
    Core ML prediction engine for trading signals:
    - Uses trained XGBoost + LightGBM + Random Forest ensemble + 28 technical indicators
    - Supports pair-specific historical datasets (EUR/USD, GBP/USD, USD/JPY, OTC pairs, etc.)
    - Outputs decisive BUY, SELL, or WAIT signals based on model confidence & indicator agreement
    """

    def __init__(self):
        self.model = None
        self.xgb_model = None
        self.lgbm_model = None
        self.cb_model = None
        self.rf_model = None
        self.mlp_model = None
        self.scaler = None
        self.model_version = settings.MODEL_VERSION
        self.confidence_threshold = 0.68   # Raised to 0.68 (68%) for Elite Quotex Sniping Filter
        self.last_prediction_time: Optional[str] = None
        self.start_time = time.time()
        self._load_models()

    def _load_models(self):
        """Load pre-trained models and metadata from disk."""
        try:
            ens_path = os.path.join(MODELS_DIR, 'ensemble_model.pkl')
            xgb_path = os.path.join(MODELS_DIR, 'xgb_model.pkl')
            lgbm_path = os.path.join(MODELS_DIR, 'lgbm_model.pkl')
            cb_path = os.path.join(MODELS_DIR, 'cb_model.pkl')
            rf_path = os.path.join(MODELS_DIR, 'rf_model.pkl')
            mlp_path = os.path.join(MODELS_DIR, 'mlp_model.pkl')
            scaler_path = os.path.join(MODELS_DIR, 'scaler.pkl')
            meta_path = os.path.join(MODELS_DIR, 'model_meta.json')

            if os.path.exists(ens_path):
                self.model = joblib.load(ens_path)
                logger.info(f'Loaded ensemble model from {ens_path}')
            if os.path.exists(xgb_path):
                self.xgb_model = joblib.load(xgb_path)
            if os.path.exists(lgbm_path):
                self.lgbm_model = joblib.load(lgbm_path)
            if os.path.exists(cb_path):
                self.cb_model = joblib.load(cb_path)
                logger.info(f'Loaded CatBoost model from {cb_path}')
            if os.path.exists(rf_path):
                self.rf_model = joblib.load(rf_path)
            if os.path.exists(mlp_path):
                self.mlp_model = joblib.load(mlp_path)
                logger.info(f'Loaded Deep MLP model from {mlp_path}')
            if os.path.exists(scaler_path):
                self.scaler = joblib.load(scaler_path)
                logger.info(f'Loaded scaler from {scaler_path}')
            if os.path.exists(meta_path):
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
                    self.model_version = meta.get('version', self.model_version)
        except Exception as e:
            logger.error(f'Error loading models: {e}')

    def _rule_based_score(self, row: pd.Series) -> tuple:
        """
        Calculates technical indicator consensus score from the 28 indicators.
        Handles both:
        1. Mean-reversion at true extremes (RSI < 30 / > 70, Stoch < 20 / > 80, BB < 0.18 / > 0.82)
        2. Trend & momentum continuation in normal ranges (EMA 9/21 cross, MACD hist, SMA 50, RSI 32-68)
        Returns (direction: 1=BUY / 0=SELL / -1=WAIT, agreement_ratio: 0.0 to 1.0)
        """
        buy_pts = 0.0
        sell_pts = 0.0

        rsi14 = float(row.get('rsi_14', 50))
        rsi7 = float(row.get('rsi_7', 50))
        stoch_k = float(row.get('stoch_k', 50))
        bb_pos = float(row.get('bb_position', 0.5))
        macd_hist = float(row.get('macd_hist', 0))
        ema_cross = int(row.get('ema_cross', 0))
        sma50_rel = float(row.get('sma_50', 0))
        cci = float(row.get('cci', 0))
        williams = float(row.get('williams_r', -50))
        pc3 = float(row.get('price_change_3', 0))
        is_hammer = int(row.get('is_hammer', 0))
        is_engulfing = int(row.get('is_engulfing', 0))

        adx = float(row.get('adx', 20))
        is_trending = adx >= 25
        is_ranging = adx < 20

        # 1. Overbought / Oversold Signals (ADX Regime Aware)
        # In a strong trend (ADX >= 25), Stoch > 75 is Bullish Trend Momentum, NOT a sell signal!
        if is_trending:
            if stoch_k > 70 and rsi14 >= 50:
                buy_pts += 1.4   # Strong Bullish Trend Momentum
            elif stoch_k < 30 and rsi14 <= 50:
                sell_pts += 1.4  # Strong Bearish Trend Momentum
        elif is_ranging:
            if stoch_k < 20:
                buy_pts += 1.5   # Mean reversion bounce off floor
            elif stoch_k > 80:
                sell_pts += 1.5  # Mean reversion rejection off ceiling
        else:
            if 55 <= stoch_k <= 78 and rsi14 <= 68:
                buy_pts += 0.6
            elif 22 <= stoch_k <= 45 and rsi14 >= 32:
                sell_pts += 0.6

        if rsi14 < 30:
            buy_pts += 2.0
        elif rsi14 > 70:
            sell_pts += 2.0
        elif 52 <= rsi14 <= 68:
            buy_pts += 0.9
        elif 32 <= rsi14 <= 48:
            sell_pts += 0.9

        # Bollinger Band Position
        if is_ranging:
            if bb_pos < 0.18:
                buy_pts += 1.5
            elif bb_pos > 0.82:
                sell_pts += 1.5
        else:
            if bb_pos > 0.60 and rsi14 >= 52:
                buy_pts += 1.0  # Riding upper band in trend
            elif bb_pos < 0.40 and rsi14 <= 48:
                sell_pts += 1.0  # Riding lower band in trend

        # 2. Trend & MACD Momentum Signals (Require meaningful magnitude, not micro-noise)
        ema9_rel = float(row.get('ema_9', 0))
        if ema_cross == 1 and ema9_rel > 0.02:
            buy_pts += 1.1
        elif ema_cross == 0 and ema9_rel < -0.02:
            sell_pts += 1.1

        if abs(macd_hist) > 0.005:
            if macd_hist > 0:
                buy_pts += 1.1
            else:
                sell_pts += 1.1

        # SMA 50 relative deviation
        if sma50_rel > 0.05:
            buy_pts += 0.7
        elif sma50_rel < -0.05:
            sell_pts += 0.7

        if pc3 > 0.10:
            buy_pts += 0.6
        elif pc3 < -0.10:
            sell_pts += 0.6

        if cci < -100:
            buy_pts += 0.9
        elif cci > 100:
            sell_pts += 0.9

        if williams < -80:
            buy_pts += 0.8
        elif williams > -20:
            sell_pts += 0.8

        if rsi7 < 30 and rsi14 < 45:
            buy_pts += 0.7
        elif rsi7 > 70 and rsi14 > 55:
            sell_pts += 0.7

        if is_hammer == 1:
            buy_pts += 0.8
        if is_engulfing == 1:
            if ema_cross == 1:
                buy_pts += 0.7
            else:
                sell_pts += 0.7

        # ── World-Famous Indicators Integration ──────────────────────────────
        st_val = float(row.get('supertrend', 0))
        if st_val > 0.5:
            buy_pts += 1.0
        elif st_val < -0.5:
            sell_pts += 1.0

        cmo_val = float(row.get('cmo_14', 0))
        if cmo_val < -45:
            buy_pts += 1.0
        elif cmo_val > 45:
            sell_pts += 1.0

        mfi_val = float(row.get('mfi_14', 50))
        if mfi_val < 22:
            buy_pts += 1.2
        elif mfi_val > 78:
            sell_pts += 1.2

        hma_val = float(row.get('hma_16_slope', 0))
        if hma_val > 0.04:
            buy_pts += 0.8
        elif hma_val < -0.04:
            sell_pts += 0.8

        total = buy_pts + sell_pts + 1e-9
        diff = abs(buy_pts - sell_pts)
        if diff < 1.0:
            # Market is flat/indecisive -> WAIT
            return -1, 0.52

        direction = 1 if buy_pts > sell_pts else 0
        ratio = max(buy_pts, sell_pts) / total
        return direction, min(0.95, max(0.55, ratio))

    def predict(
        self,
        candles: List[Dict],
        timeframe: str = '1m',
        pair: str = 'EUR/USD',
        min_confidence_override: Optional[float] = None,
        micro_ticks: Optional[Dict[str, Any]] = None,
        min_confidence: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Analyzes the selected pair's candle data using all 33 technical indicators
        and the trained ML ensemble, returning BUY, SELL, or WAIT.
        """
        if min_confidence_override is None and min_confidence is not None:
            min_confidence_override = min_confidence / 100.0 if min_confidence > 1 else min_confidence
        t0 = time.perf_counter()
        df = calculate_indicators(candles)
        latest_row = df.iloc[-1]
        entry_price = float(latest_row['close'])

        features_dict = {col: round(float(latest_row.get(col, 0.0)), 6) for col in FEATURE_COLUMNS}
        learner = get_adaptive_learner()
        weights = learner.weights

        rule_dir, rule_conf = self._rule_based_score(latest_row)
        model_preds = {}

        if self.scaler is not None and (self.model is not None or self.xgb_model is not None):
            features = np.nan_to_num(df[FEATURE_COLUMNS].iloc[-1:].values, nan=0.0)
            features_scaled = np.nan_to_num(self.scaler.transform(features), nan=0.0)

            if self.xgb_model is not None and self.lgbm_model is not None and self.rf_model is not None:
                p_xgb = self.xgb_model.predict_proba(features_scaled)[0]
                p_lgbm = self.lgbm_model.predict_proba(features_scaled)[0]
                p_rf = self.rf_model.predict_proba(features_scaled)[0]

                model_preds = {
                    'xgb': round(float(p_xgb[1]), 4),
                    'lgbm': round(float(p_lgbm[1]), 4),
                    'rf': round(float(p_rf[1]), 4)
                }

                w_xgb = weights.get('xgb', 0.24)
                w_lgbm = weights.get('lgbm', 0.20)
                w_cb = weights.get('cb', 0.22)
                w_rf = weights.get('rf', 0.16)
                w_mlp = weights.get('mlp', 0.18)

                components = [(w_xgb, p_xgb), (w_lgbm, p_lgbm), (w_rf, p_rf)]

                if self.cb_model is not None:
                    p_cb = self.cb_model.predict_proba(features_scaled)[0]
                    model_preds['cb'] = round(float(p_cb[1]), 4)
                    components.append((w_cb, p_cb))

                if self.mlp_model is not None:
                    p_mlp = self.mlp_model.predict_proba(features_scaled)[0]
                    model_preds['mlp'] = round(float(p_mlp[1]), 4)
                    components.append((w_mlp, p_mlp))

                tot_w = sum(w for w, _ in components)
                ml_proba = sum(w * p for w, p in components) / tot_w
            else:
                ml_proba = self.model.predict_proba(features_scaled)[0]

            ml_dir = int(np.argmax(ml_proba))
            ml_conf = float(ml_proba[ml_dir])

            # ── Epistemic Uncertainty & Model Disagreement Variance Gate ────────────
            # Computes variance and standard deviation across all 5 sub-models:
            # Low variance (std <= 0.045) = Strong unanimous consensus across all model architectures.
            # High variance (std > 0.085) or deadlock = Epistemic ambiguity (dangerous coin-flip noise).
            ensemble_std = 0.0
            if model_preds:
                prob_vals = list(model_preds.values())
                ensemble_std = float(np.std(prob_vals))
                votes_buy = sum(1 for v in model_preds.values() if v > 0.50)
                votes_sell = sum(1 for v in model_preds.values() if v <= 0.50)
                n_models = len(model_preds)

                is_deadlock = (n_models % 2 == 0 and votes_buy == votes_sell)
                majority_thresh = (n_models // 2) + 1
                majority_agrees = (ml_dir == 1 and votes_buy >= majority_thresh) or \
                                  (ml_dir == 0 and votes_sell >= majority_thresh)
                is_unanimous = (ml_dir == 1 and votes_buy == n_models) or \
                               (ml_dir == 0 and votes_sell == n_models)

                if is_deadlock or ensemble_std > 0.085:
                    # Model disagreement: push toward WAIT to avoid coin flips
                    ml_conf = min(ml_conf, 0.58)
                elif not majority_agrees:
                    ml_conf = min(ml_conf, 0.61)
                elif is_unanimous or ensemble_std <= 0.040:
                    # Unanimous / strong consensus bonus across all 5 architectures
                    ml_conf = min(0.97, ml_conf + 0.04)

            # ── ADX-aware trend gate ──────────────────────────────────────────────────
            adx_val = float(latest_row.get('adx', 0))
            # Choppy/no-trend market: suppress signals unless ML is very strong
            adx_choppy = adx_val < 18
            # Strong trend: allow threshold to relax slightly
            adx_trending = adx_val > 28

            # ── Combine ML + indicator rule with ADX-adaptive blend ───────────────────
            if rule_dir == -1:
                # Indicators show sideways/chop: only trade if ML confidence is very strong (>78%)
                if ml_conf >= 0.78 and not adx_choppy:
                    prediction = ml_dir
                    confidence_raw = ml_conf * 0.85
                else:
                    prediction = -1
                    confidence_raw = 0.54
            elif rule_dir == ml_dir:
                # Both trained ML model and technical indicators agree → High confidence
                prediction = ml_dir
                # ADX trending: trust ML more (65% weight); ranging: trust indicators more (45%)
                ml_weight = 0.65 if adx_trending else 0.60
                rule_weight = 1.0 - ml_weight
                confidence_raw = min(0.95, ml_conf * ml_weight + rule_conf * rule_weight + 0.02)
                # Extra suppression in choppy markets even when both agree
                if adx_choppy and confidence_raw < 0.72:
                    prediction = -1
                    confidence_raw = 0.54
            else:
                # ML model and short-term indicators disagree on direction
                # In binary trading, trading into direct indicator/ML conflict is low win-rate
                # Strict Sniper: Only trade if at least 3 ML models agree AND ml_conf >= 0.74 AND not choppy
                votes_for_ml = votes_buy if ml_dir == 1 else votes_sell
                if votes_for_ml >= 3 and ml_conf >= 0.74 and not adx_choppy:
                    prediction = ml_dir
                    confidence_raw = ml_conf * 0.90
                else:
                    prediction = -1
                    confidence_raw = 0.54
                if adx_choppy:
                    prediction = -1
                    confidence_raw = 0.52
        else:
            prediction, confidence_raw = rule_dir, rule_conf
            p_up = confidence_raw if prediction == 1 else (1.0 - confidence_raw)
            model_preds = {'xgb': round(p_up, 4), 'lgbm': round(p_up, 4), 'rf': round(p_up, 4), 'mlp': round(p_up, 4)}

        # ── World-Famous Candlestick Pattern Detection ───────────────────────────
        detected_pattern = detect_candlestick_pattern(candles)
        pattern_dir = detected_pattern.get('direction', 'NEUTRAL')
        pattern_rel = detected_pattern.get('reliability', 'LOW')

        # Pattern Synergy with ML / Technical Consensus
        if pattern_dir == 'BULLISH':
            if prediction == 1:
                boost = 0.035 if pattern_rel == 'HIGH' else 0.02
                confidence_raw = min(0.96, confidence_raw + boost)
            elif prediction == 0:
                penalty = 0.05 if pattern_rel == 'HIGH' else 0.03
                confidence_raw = max(0.50, confidence_raw - penalty)
        elif pattern_dir == 'BEARISH':
            if prediction == 0:
                boost = 0.035 if pattern_rel == 'HIGH' else 0.02
                confidence_raw = min(0.96, confidence_raw + boost)
            elif prediction == 1:
                penalty = 0.05 if pattern_rel == 'HIGH' else 0.03
                confidence_raw = max(0.50, confidence_raw - penalty)
        elif pattern_dir == 'NEUTRAL' and detected_pattern.get('type') == 'INDECISION':
            confidence_raw = min(confidence_raw, 0.62)

        # ── Quotex Algorithmic Dynamics Integration ──────────────────────────────
        quotex_dyn = analyze_quotex_algorithm_dynamics(candles, micro_ticks=micro_ticks)
        q_bias = quotex_dyn.get('quotex_bias', 'WAIT')
        q_regime = quotex_dyn.get('regime', 'RANGING')
        q_memory = quotex_dyn.get('market_memory', 'RANDOM_WALK_NOISE')
        q_exhaustion = quotex_dyn.get('exhaustion_risk', False)
        q_adj = quotex_dyn.get('confidence_adjustment', 0.0)
        vsa_info = quotex_dyn.get('vsa', {})
        vsa_bias = vsa_info.get('bias', 'NEUTRAL')
        mtf_info = quotex_dyn.get('mtf', {})
        mtf_trend = mtf_info.get('mtf_trend', 'NEUTRAL')
        micro_vel = quotex_dyn.get('micro_velocity', {})

        # 1. Anti-Exhaustion Guard (Prevent buying tops / selling bottoms on Quotex 3-to-5 bar traps)
        if q_exhaustion:
            if prediction == 1 and q_bias == 'SELL':
                # Block buying at the top of exhausted green candle run!
                prediction = -1
                confidence_raw = 0.52
            elif prediction == 0 and q_bias == 'BUY':
                # Block selling at the bottom of exhausted red candle run!
                prediction = -1
                confidence_raw = 0.52
            elif pattern_dir == q_bias and pattern_rel == 'HIGH':
                # Reversal pattern confirms mean-reversion counter-trade!
                prediction = 1 if q_bias == 'BUY' else 0
                confidence_raw = min(0.94, confidence_raw + 0.05)

        # 2. Multi-Timeframe Confluence (5M Macro Trend vs 1M Trigger)
        if not q_exhaustion:
            if prediction == 1:
                if mtf_trend == 'BULLISH':
                    confidence_raw = min(0.98, confidence_raw + 0.04)
                elif mtf_trend == 'BEARISH':
                    # 1m BUY directly into 5m Bearish macro trend -> High loss probability
                    confidence_raw = max(0.50, confidence_raw - 0.10)
                    prediction = -1
            elif prediction == 0:
                if mtf_trend == 'BEARISH':
                    confidence_raw = min(0.98, confidence_raw + 0.04)
                elif mtf_trend == 'BULLISH':
                    # 1m SELL directly into 5m Bullish macro trend -> High loss probability
                    confidence_raw = max(0.50, confidence_raw - 0.10)
                    prediction = -1

        # 3. Quotex Algorithmic Trend, VSA & Fractal Hurst Synergy
        if not q_exhaustion and prediction != -1:
            if (prediction == 1 and q_bias == 'BUY') or (prediction == 0 and q_bias == 'SELL'):
                confidence_raw = min(0.96, confidence_raw + q_adj)
                # Extra boost if VSA confirms smart money absorption or effort expansion
                if vsa_bias == q_bias:
                    confidence_raw = min(0.98, confidence_raw + 0.03)
            elif (prediction == 1 and q_bias == 'SELL') or (prediction == 0 and q_bias == 'BUY'):
                confidence_raw = max(0.48, confidence_raw - 0.08)
            elif q_regime == 'CHOPPY_SIDEWAYS' or (q_memory == 'RANDOM_WALK_NOISE' and confidence_raw < 0.74):
                # Filter out pure noise trades on Quotex
                confidence_raw = min(confidence_raw, 0.58)
                prediction = -1

        # 4. Micro-Second Velocity Lock (:57-second confirmation)
        if micro_vel.get('last_second_trap', False):
            prediction = -1
            confidence_raw = 0.50

        # 5. Dynamic Volatility-Adaptive Confidence Gate
        base_threshold = min_confidence_override if min_confidence_override is not None else self.confidence_threshold
        if q_regime == 'CHOPPY_SIDEWAYS' or q_memory == 'RANDOM_WALK_NOISE':
            # In choppy noise, demand at least 78% certainty
            adaptive_threshold = max(0.78, base_threshold + 0.08)
        elif (prediction == 1 and mtf_trend == 'BULLISH') or (prediction == 0 and mtf_trend == 'BEARISH'):
            # In confirmed multi-timeframe trend, allow 68%+
            adaptive_threshold = max(0.68, base_threshold - 0.02)
        elif q_exhaustion:
            adaptive_threshold = max(0.72, base_threshold)
        else:
            adaptive_threshold = base_threshold

        confidence_pct = round(confidence_raw * 100, 2)
        threshold = adaptive_threshold

        if prediction == -1 or confidence_raw < threshold:
            signal = 'WAIT'
            strength = 'WEAK'
        elif confidence_raw >= 0.78:
            signal = 'BUY' if prediction == 1 else 'SELL'
            strength = 'STRONG'
        elif confidence_raw >= 0.68:
            signal = 'BUY' if prediction == 1 else 'SELL'
            strength = 'MEDIUM'
        else:
            signal = 'BUY' if prediction == 1 else 'SELL'
            strength = 'WEAK'

        indicator_signals = get_indicator_signals(latest_row)
        if signal == 'WAIT':
            reasons = [
                f"Market consolidating on {pair} (Confidence {confidence_pct}% below sniper threshold {int(threshold*100)}%)",
                f"Quotex Regime: {q_regime} — sniper filter waiting for high-probability A+ setup"
            ]
        else:
            reasons = generate_reasons(indicator_signals, 1 if signal == 'BUY' else 0, confidence_pct)

        if detected_pattern.get('pattern_name') != 'Normal Price Action':
            pat_text = f"Pattern: {detected_pattern['pattern_name']} ({detected_pattern['direction']} {detected_pattern['type']}) — {detected_pattern['action_advice']}"
            reasons.insert(0, pat_text)

        if quotex_dyn.get('reasons'):
            for qr in quotex_dyn['reasons']:
                reasons.insert(0, f"Quotex Engine: {qr}")

        duration_map = {'30s': 30, '1m': 60, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600}
        recommended_duration = duration_map.get(timeframe, 60)

        # Current candle achieved position analysis
        candle_open = float(latest_row.get('open', entry_price))
        candle_high = float(latest_row.get('high', max(candle_open, entry_price)))
        candle_low = float(latest_row.get('low', min(candle_open, entry_price)))
        candle_delta = entry_price - candle_open
        candle_pct = round((candle_delta / (candle_open + 1e-9)) * 100, 3)

        if candle_delta > 0:
            c_direction = "BULLISH"
            c_achieved = f"Current candle achieved Bullish advance (+{candle_pct:.2f}%) from {candle_open:.5f} to {entry_price:.5f}"
        elif candle_delta < 0:
            c_direction = "BEARISH"
            c_achieved = f"Current candle achieved Bearish drop ({candle_pct:.2f}%) from {candle_open:.5f} to {entry_price:.5f}"
        else:
            c_direction = "DOJI"
            c_achieved = f"Current candle indecisive (Doji/Flat) at {entry_price:.5f}"

        # Next candle prediction details
        scale = 0.0001 if entry_price < 5 else (0.1 if entry_price > 1000 else 0.01)
        if signal == 'BUY':
            next_action = "BUY (CALL UP)"
            next_summary = f"Next {timeframe} candle predicted to go UP for {recommended_duration}s"
            ideal_entry = round(entry_price - 0.6 * scale, 5 if entry_price < 5 else 2)
            sniper_entry_advice = f"Sniper CALL: Target micro-pullback to ~{ideal_entry} in :02s-:10s for peak win-margin"
        elif signal == 'SELL':
            next_action = "SELL (PUT DOWN)"
            next_summary = f"Next {timeframe} candle predicted to go DOWN for {recommended_duration}s"
            ideal_entry = round(entry_price + 0.6 * scale, 5 if entry_price < 5 else 2)
            sniper_entry_advice = f"Sniper PUT: Target micro-bounce to ~{ideal_entry} in :02s-:10s for peak win-margin"
        else:
            next_action = "WAIT (CHOP)"
            next_summary = f"Next {timeframe} candle direction uncertain — wait for breakout"
            sniper_entry_advice = "Market in consolidation — Await confirmed breakout before entering"

        duration_text = f"{recommended_duration // 60} min ({recommended_duration}s)" if recommended_duration >= 60 else f"{recommended_duration}s"

        analysis_ms = round((time.perf_counter() - t0) * 1000, 2)
        now_iso = datetime.utcnow().isoformat() + 'Z'
        self.last_prediction_time = now_iso

        uncertainty_level = 'LOW' if ensemble_std <= 0.05 else ('MEDIUM' if ensemble_std <= 0.08 else 'HIGH')

        return {
            'signal': signal,
            'confidence': confidence_pct,
            'strength': strength,
            'entry_price': entry_price,
            'pair': pair,
            'timeframe': timeframe,
            'dynamic_gate_threshold': round(adaptive_threshold * 100, 1),
            'next_candle_summary': next_summary,
            'sniper_entry_advice': sniper_entry_advice,
            'epistemic_uncertainty': {
                'ensemble_std': round(float(ensemble_std), 4),
                'uncertainty_level': uncertainty_level,
                'unanimous_consensus': bool(ensemble_std <= 0.05)
            },
            'pattern': detected_pattern,
            'detected_pattern': detected_pattern,
            'quotex_dynamics': quotex_dyn,
            'candles_analyzed': len(candles),
            'history_hours': round((len(candles) * (300 if timeframe == '5m' else 60)) / 3600.0, 1),
            'analysis_ms': analysis_ms,
            'indicators': indicator_signals,
            'features': features_dict,
            'model_votes': model_preds,
            'ensemble_weights': {
                'xgb': weights.get('xgb', 0.30),
                'lgbm': weights.get('lgbm', 0.25),
                'cb': weights.get('cb', 0.25),
                'rf': weights.get('rf', 0.20)
            },
            'reasons': reasons,
            'recommended_duration': recommended_duration,
            'current_candle': {
                'open': candle_open,
                'high': candle_high,
                'low': candle_low,
                'close': entry_price,
                'direction': c_direction,
                'change_pct': candle_pct,
                'achieved_position': c_achieved
            },
            'next_candle_prediction': {
                'action': next_action,
                'direction': 'UP' if signal == 'BUY' else ('DOWN' if signal == 'SELL' else 'WAIT'),
                'duration_seconds': recommended_duration,
                'duration_text': duration_text,
                'summary': next_summary
            },
            'timestamp': now_iso,
            'model_version': self.model_version
        }

    def get_uptime_str(self) -> str:
        elapsed = int(time.time() - self.start_time)
        hrs, rem = divmod(elapsed, 3600)
        mins, secs = divmod(rem, 60)
        return f'{hrs}h {mins}m {secs}s'

    def reload_models(self):
        """Reload models from disk (called after retraining)."""
        self._load_models()


_predictor: Optional[TradingPredictor] = None


def get_predictor() -> TradingPredictor:
    global _predictor
    if _predictor is None:
        _predictor = TradingPredictor()
    return _predictor
