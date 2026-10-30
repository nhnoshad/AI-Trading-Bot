# 🤖 AI Trading Signal Bot

> ML-powered Chrome Extension + Python Backend + React Dashboard for Quotex binary options trading

---

## 🏗️ System Architecture

```
Chrome Extension (Quotex Overlay)
        │  HTTP POST (candle data)
        ▼
FastAPI ML Backend (Python)
 ├── Technical Indicator Calculator (28 features)
 ├── XGBoost + LightGBM + Random Forest Ensemble
 └── PostgreSQL + Redis
        │
        ▼
React Web Dashboard (monitoring + settings)
```

---

## 📁 Project Structure

```
AI-Trading-Bot/
├── chrome-extension/          # Chrome Extension (Manifest V3)
│   ├── manifest.json
│   └── src/
│       ├── popup/             # popup.html + popup.css + popup.js
│       ├── overlay/           # overlay.css (injected into Quotex)
│       └── scripts/           # background.js + content.js
│
├── ml-backend/                # Python FastAPI ML Server
│   ├── app/
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── core/              # config.py + database.py
│   │   ├── api/               # routes.py (all endpoints)
│   │   └── services/          # indicators.py + predictor.py
│   ├── scripts/
│   │   ├── data/              # download_data.py
│   │   └── training/          # train_model.py
│   ├── models/                # Saved .pkl model files
│   ├── data/                  # Training CSV data
│   ├── requirements.txt
│   └── .env.example
│
├── web-dashboard/             # React + Tailwind Dashboard
│   ├── src/
│   │   ├── pages/             # Dashboard, TradeHistory, Settings, Backtesting, ModelPerformance
│   │   ├── components/        # Layout
│   │   ├── services/          # api.js
│   │   └── store/             # useStore.js (Zustand)
│   ├── package.json
│   └── vite.config.js
│
└── docker/                    # Docker + Nginx config
    ├── docker-compose.yml
    ├── Dockerfile.backend
    ├── Dockerfile.dashboard
    └── nginx.conf
```

---

## 🚀 Quick Start

### Step 1: ML Backend Setup

```bash
cd ml-backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate    # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Copy env file
copy .env.example .env

# Download training data
python scripts/data/download_data.py --pair EURUSD --interval 1m --source yfinance --days 60

# Train the ML models
python scripts/training/train_model.py --data data/EURUSD_1m_yfinance.csv

# Start the server
python run.py
# Server runs at http://localhost:8000
# API Docs at  http://localhost:8000/docs
```

### Step 2: Chrome Extension Setup

1. Open Chrome → `chrome://extensions/`
2. Enable **Developer Mode** (top right toggle)
3. Click **Load unpacked**
4. Select the `AI-Trading-Bot/chrome-extension/` folder
5. Extension icon appears in toolbar

### Step 3: Use on Quotex

1. Go to `https://qxbroker.com` or `https://quotex.com`
2. Click the 🤖 **AI Trading Bot** extension icon
3. Set Server URL: `http://localhost:8000`
4. Click **Test** to verify connection
5. Click **▶ START BOT**
6. The signal overlay appears on the Quotex page

### Step 4: Web Dashboard Setup

```bash
cd web-dashboard

# Install dependencies
npm install

# Start dev server
npm run dev
# Dashboard at http://localhost:3000
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Server health + model status |
| `POST` | `/api/predict` | Send candles → get BUY/SELL/WAIT signal |
| `POST` | `/api/log-trade` | Log a trade result |
| `GET` | `/api/stats` | Overall trading statistics |
| `GET` | `/api/indicators` | List of all indicator names |
| `POST` | `/api/retrain` | Trigger model retraining |
| `POST` | `/api/backtest` | Run backtesting simulation |

**Full interactive docs:** http://localhost:8000/docs

---

## 🧠 ML Models Used

| Model | Weight | Expected Accuracy |
|-------|--------|-------------------|
| XGBoost | 40% | 55-62% |
| LightGBM | 35% | 54-61% |
| Random Forest | 25% | 53-58% |
| **Ensemble** | - | **56-63%** |

---

## 📊 Technical Indicators (28 Features)

**Momentum:** RSI-14, RSI-7, Stochastic %K/%D, Williams %R, CCI  
**Trend:** EMA-9, EMA-21, SMA-50, MACD Line/Signal/Histogram, EMA Cross, ADX  
**Volatility:** Bollinger Band Width/Position, ATR-14  
**Price Action:** Price Change 1/3/5 candles, Candle Body Ratio  
**Candle Patterns:** Body Size, Upper/Lower Wick, Doji, Hammer, Engulfing, Consecutive Direction

---

## 🛡️ Safety Controls

| Control | Default | Description |
|---------|---------|-------------|
| Max Trades/Hour | 10 | Prevents overtrading |
| Max Consecutive Losses | 3 | Stops after 3 losses in a row |
| Daily Loss Limit | $50 | Auto-stops at daily loss cap |
| Daily Profit Target | $100 | Auto-stops when target reached |
| Min Confidence | 65% | Only trades high-confidence signals |
| Cooldown | 30s | Minimum gap between trades |

---

## 🐳 Docker Deployment

```bash
cd docker
docker-compose up -d
```

Services started:
- Backend API: http://localhost:8000
- Dashboard: http://localhost:3000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

---

## 📈 Data Sources

| Source | Quality | Best For |
|--------|---------|----------|
| Dukascopy | ⭐⭐⭐⭐⭐ | Primary training (2+ years) |
| Yahoo Finance | ⭐⭐⭐⭐ | Daily automated updates |
| Binance API | ⭐⭐⭐⭐⭐ | Crypto pairs (free unlimited) |
| Alpha Vantage | ⭐⭐⭐⭐ | Forex intraday (25 req/day free) |

---

## ⚠️ Important Disclaimers

> **Binary options trading carries significant financial risk. Past performance does not guarantee future results. This bot is a decision-support tool — always apply your own judgment. Never trade with money you cannot afford to lose.**

---

## 📋 Development Phases

- [x] **Phase 1** - ML Backend + API Server
- [x] **Phase 2** - Chrome Extension (overlay + auto-trade)
- [x] **Phase 3** - Web Dashboard
- [ ] **Phase 4** - Testing, optimization, LSTM model
