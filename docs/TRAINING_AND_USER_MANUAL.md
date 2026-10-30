# 📚 Complete Training Manual, Architecture, Deployment & User Guide
**Project:** AI Trading Signal Bot (Quotex Chrome Extension + ML Backend + Web Dashboard)

---

## 🧠 How the 4-Stage Adaptive AI Lifecycle Works

Per your specification, the AI is engineered around a continuous 4-stage loop:

1. **Stage 1 — Fast Analyze (`<10ms`)**:
   - The Chrome Extension intercepts Quotex live WebSocket frames (`ws_hook.js`) or scrapes DOM/Canvas candles and posts the last 100+ OHLCV candles to `POST /api/predict`.
   - `indicators.py` computes all **28 Technical Indicators** (Momentum, Trend, Volatility, Price Action, and Candle Patterns) using vectorized NumPy/Pandas operations in under 10 milliseconds.
   - `predictor.py` evaluates **XGBoost**, **LightGBM**, and **Random Forest** simultaneously and blends their probabilities using live dynamic weights (`dynamic_weights.json`).

2. **Stage 2 — Performance Measure (`AdaptiveLearner.measure_performance`)**:
   - Every signal's 28-feature vector and sub-model probability votes are saved in the `signals` database table.
   - When a trade finishes (`POST /api/log-trade`) or when the next candle closes (`auto_verify`), the system compares the predicted direction against the actual outcome (`WIN` or `LOSS`).
   - Rolling 24-hour, 7-day, and 30-day accuracy, precision, recall, F1 score, and confusion matrices are updated in real time.

3. **Stage 3 — Save >= 1 Month (35 Days) Learning Memory**:
   - Every verified feature vector + actual market outcome is stored in `ml-backend/data/rolling_30d_learning_memory.csv` and the SQLite/PostgreSQL `learning_samples` table.
   - The rolling buffer automatically retains **35 days (> 1 full month)** of historical and live trade data so the AI never forgets recent market regimes.

4. **Stage 4 — Learn & Update from Results (`record_outcome_and_learn` & `retrain_from_rolling_memory`)**:
   - **Immediate Online Learning**: After every single trade result, exponential moving accuracy (`EMA`) is updated for XGBoost, LightGBM, and Random Forest, and ensemble weights automatically shift toward the highest-performing model.
   - **Periodic / Triggered Full Retraining**: Every 25 verified trade outcomes (or weekly via `scheduler.py` / manually via the Dashboard **"Retrain on 1-Month Memory"** button), all three models retrain on the 35-day rolling dataset with **3x sample weighting on real live trade outcomes**.

---

## 🎓 6-Session Training Curriculum (13 Hours Total)

### Session 1: System Overview & Architecture (2 Hours)
- **Architecture Walkthrough**:
  - `chrome-extension/` (Manifest V3 Content Script + Page-Context WebSocket Hook + Popup Control Panel)
  - `ml-backend/` (FastAPI + SQLAlchemy + 28 Indicators + Adaptive Ensemble Engine)
  - `web-dashboard/` (React 18 + Vite + Tailwind CSS + Recharts + Zustand)
- **Starting & Stopping Services**:
  - Backend: `cd ml-backend && python run.py` (Port `8000`)
  - Dashboard: `cd web-dashboard && npm run dev` (Port `3000`)
  - Docker Full Stack: `cd docker && docker-compose up -d`
- **Health Monitoring**: Check `http://localhost:8000/api/health` and `http://localhost:8000/docs`.

### Session 2: ML Model Management & 30-Day Continuous Learning (3 Hours)
- **The 28 Technical Indicators**:
  - *Momentum (6)*: `rsi_14`, `rsi_7`, `stoch_k`, `stoch_d`, `williams_r`, `cci`
  - *Trend (8)*: `ema_9`, `ema_21`, `sma_50`, `macd_line`, `macd_signal`, `macd_hist`, `ema_cross`, `adx`
  - *Volatility (3)*: `bb_width`, `bb_position`, `atr_14`
  - *Price Action (4)*: `price_change_1`, `price_change_3`, `price_change_5`, `candle_body_ratio`
  - *Candle Patterns (7)*: `body_size`, `upper_wick`, `lower_wick`, `is_doji`, `is_hammer`, `is_engulfing`, `consecutive_same_direction`
- **Commands for Data & Training**:
  - Bootstrap 35-day memory & train models: `python scripts/training/bootstrap_initial_models.py`
  - Download fresh Yahoo Finance / Binance data: `python scripts/data/download_data.py --pair EURUSD --interval 1m --days 60`
  - Run continuous learning manually: `python scripts/training/continuous_learning.py`
  - Run backtesting: `python scripts/training/backtest.py --confidence 65`

### Session 3: Chrome Extension Management (2 Hours)
- **Installation**:
  1. Open `chrome://extensions/`
  2. Enable **Developer mode**
  3. Click **Load unpacked** and select `AI-Trading-Bot/chrome-extension`
- **Updating DOM Selectors if Quotex Changes UI**:
  - Open `chrome-extension/src/scripts/content.js`
  - Edit `priceSelectors`, `pairSelectors`, `buySelectors`, and `sellSelectors` arrays if Quotex renames CSS classes.
- **Debugging**: Right-click the Quotex page → **Inspect** → **Console** to view `[AI Bot]` logs, or inspect the Popup directly.

### Session 4: Web Dashboard & Database Management (2 Hours)
- **Pages Included**:
  - `/login` — Email/Password + 6-digit OTP verification + Password Reset
  - `/dashboard` — Live Signal, Equity Curve, Win Rate, P&L, Best Pair
  - `/history` — Filterable Trade History + 1-Click CSV Export
  - `/backtest` — Interactive Backtesting Simulator
  - `/model` — 35-Day Rolling Memory Status, Dynamic Ensemble Weights, Confusion Matrix, Feature Importance, and 1-Click Model Retrain
  - `/settings` — Risk & Safety Controls
- **Database Backup**:
  - SQLite: Copy `ml-backend/trading_bot.db` and `ml-backend/data/rolling_30d_learning_memory.csv`.
  - PostgreSQL: `pg_dump -U trader trading_bot > backup.sql`

### Session 5: Server & Deployment Management (2 Hours)
- **Docker Production Deployment**:
  - Configure `.env` from `.env.example`
  - Run `docker-compose -f docker/docker-compose.yml up -d --build`
  - View logs: `docker-compose logs -f backend`

### Session 6: Trading Strategy, Risk & Safety Controls (2 Hours)
- **Built-In Safety Controls**:
  - **Max Trades/Hour** (Default: `10`)
  - **Max Consecutive Losses** (Default: `3` → auto-stops bot)
  - **Daily Loss Limit** (Default: `\$50` → auto-stops bot)
  - **Daily Profit Target** (Default: `\$100` → locks in profits)
  - **Minimum Confidence Threshold** (Default: `65%` → filters out noisy setups)
  - **Cooldown Period** (Default: `30s` between trades)
  - **Emergency STOP ALL Button** directly on the Quotex overlay.

---

## ❓ Troubleshooting & FAQ

- **Q: Extension says "Offline" in Popup?**
  - Ensure the Python ML server is running on `http://localhost:8000` (`python run.py` inside `ml-backend/`).
- **Q: How do I export signals or trades to CSV?**
  - Click **📥 CSV** in the Chrome Extension popup for the last 50 signals, or click **Export CSV** on the Web Dashboard Trade History page.
- **Q: How do I force the AI to retrain on my latest trades immediately?**
  - Open the Web Dashboard → **AI Model** page → click **Retrain on 1-Month Memory**, or send `POST http://localhost:8000/api/retrain`.
