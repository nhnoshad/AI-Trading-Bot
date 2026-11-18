"""Full system status check script"""
import os, sys, json, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'trading_bot.db')
MODELS_DIR = os.path.join(os.path.dirname(__file__), '..', 'models')
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

issues = []
ok_items = []

print("=" * 55)
print("   AI TRADING BOT — FULL SYSTEM STATUS CHECK")
print("=" * 55)

# --- 1. DATABASE ---
print("\n📊 DATABASE")
try:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    modes = dict(c.execute("SELECT mode, count(*) FROM trades GROUP BY mode").fetchall())
    total_trades = sum(modes.values())
    wins = c.execute("SELECT count(*) FROM trades WHERE result = 'WIN'").fetchone()[0]
    losses = c.execute("SELECT count(*) FROM trades WHERE result = 'LOSS'").fetchone()[0]
    pending = c.execute("SELECT count(*) FROM trades WHERE result = 'PENDING'").fetchone()[0]
    manual = modes.get('MANUAL', 0)
    total_signals = c.execute("SELECT count(*) FROM signals").fetchone()[0]
    total_samples = c.execute("SELECT count(*) FROM learning_samples").fetchone()[0]

    win_rate = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0.0
    print(f"  Trades by mode: {modes}")
    print(f"  WIN: {wins} | LOSS: {losses} | PENDING: {pending}")
    print(f"  Overall Win Rate: {win_rate}%")
    print(f"  Total Signals: {total_signals}")
    print(f"  Learning Samples: {total_samples}")

    if manual > 0:
        issues.append(f"❌ {manual} MANUAL trades still in DB!")
    else:
        ok_items.append("✅ DB: 0 manual trades (PREDICTION only)")

    if win_rate < 40:
        issues.append(f"⚠️  Win rate {win_rate}% is below 40% — model may need retraining!")
    else:
        ok_items.append(f"✅ Win rate: {win_rate}%")

    conn.close()
except Exception as e:
    issues.append(f"❌ DB Error: {e}")

# --- 2. MODELS ---
print("\n🤖 ML MODELS")
expected_models = ['mlp_model.pkl', 'rf_model.pkl', 'xgb_model.pkl', 'lgbm_model.pkl',
                   'cb_model.pkl', 'meta_model.pkl', 'scaler.pkl', 'ensemble_model.pkl']
for m in expected_models:
    path = os.path.join(MODELS_DIR, m)
    if os.path.exists(path):
        size_kb = os.path.getsize(path) // 1024
        print(f"  ✅ {m} ({size_kb} KB)")
        ok_items.append(f"✅ Model {m}")
    else:
        print(f"  ❌ {m} MISSING!")
        issues.append(f"❌ Model {m} is missing!")

# --- 3. DYNAMIC WEIGHTS ---
print("\n⚖️  DYNAMIC WEIGHTS")
weights_path = os.path.join(MODELS_DIR, 'dynamic_weights.json')
try:
    with open(weights_path) as f:
        weights = json.load(f)
    total_w = sum(weights.values())
    print(f"  Weights: {weights}")
    print(f"  Total weight sum: {round(total_w, 4)}")
    if abs(total_w - 1.0) < 0.05:
        ok_items.append("✅ Weights sum ≈ 1.0")
    else:
        issues.append(f"⚠️  Weights sum = {total_w} (expected ≈ 1.0)")
except Exception as e:
    issues.append(f"❌ dynamic_weights.json error: {e}")

# --- 4. PAIR ACCURACY ---
print("\n🎯 PAIR ACCURACY")
pair_acc_path = os.path.join(MODELS_DIR, 'pair_accuracy.json')
try:
    with open(pair_acc_path) as f:
        pair_acc = json.load(f)
    for pair, stats in list(pair_acc.items())[:6]:
        total_p = stats.get('total', 0)
        wins_p = stats.get('wins', 0)
        wr_p = round(wins_p / total_p * 100, 1) if total_p > 0 else 0
        print(f"  {pair}: {wins_p}/{total_p} = {wr_p}%")
    ok_items.append("✅ Pair accuracy JSON OK")
except Exception as e:
    issues.append(f"❌ pair_accuracy.json error: {e}")

# --- 5. ROLLING MEMORY CSV ---
print("\n📂 ROLLING MEMORY CSV")
csv_path = os.path.join(DATA_DIR, 'rolling_30d_learning_memory.csv')
try:
    import pandas as pd
    df = pd.read_csv(csv_path)
    live_rows = df[df.get('source', pd.Series()) == 'live_trade'].shape[0] if 'source' in df.columns else 0
    print(f"  Total rows: {len(df)}")
    print(f"  live_trade rows: {live_rows}")
    if live_rows > 0:
        issues.append(f"⚠️  {live_rows} live_trade rows still in CSV")
    else:
        ok_items.append("✅ CSV: 0 live_trade rows")
    ok_items.append(f"✅ Rolling CSV: {len(df)} rows")
except Exception as e:
    issues.append(f"❌ Rolling CSV error: {e}")

# --- 6. INDICATORS IMPORT ---
print("\n📐 INDICATORS")
try:
    from services.indicators import FEATURE_COLUMNS, calculate_indicators
    import numpy as np
    candles = []
    price = 1.0850
    for i in range(100):
        o = price
        c2 = price + np.random.randn() * 0.0004
        candles.append({'open': o, 'high': max(o,c2)+0.0002, 'low': min(o,c2)-0.0002, 'close': c2, 'volume': 1200})
        price = c2
    df2 = calculate_indicators(candles)
    missing_cols = [f for f in FEATURE_COLUMNS if f not in df2.columns]
    nan_count = df2[FEATURE_COLUMNS].iloc[-1].isna().sum()
    print(f"  Feature columns: {len(FEATURE_COLUMNS)}")
    print(f"  DataFrame columns: {len(df2.columns)}")
    print(f"  Missing features: {missing_cols}")
    print(f"  NaN in last row: {nan_count}")
    if missing_cols:
        issues.append(f"❌ Missing features: {missing_cols}")
    elif nan_count > 0:
        issues.append(f"⚠️  {nan_count} NaN values in last row features!")
    else:
        ok_items.append("✅ Indicators: 38 features, 0 NaN")
except Exception as e:
    issues.append(f"❌ Indicators error: {e}")

# --- 7. PREDICTOR ---
print("\n🔮 PREDICTOR")
try:
    from services.predictor import TradingPredictor, get_predictor
    pred = get_predictor()
    print(f"  Predictor instance: {type(pred).__name__}")
    ok_items.append("✅ Predictor: loaded OK")
except Exception as e:
    issues.append(f"❌ Predictor error: {e}")

# --- 8. ADAPTIVE LEARNER ---
print("\n🧠 ADAPTIVE LEARNER")
try:
    from services.adaptive_learner import AdaptiveLearner, get_adaptive_learner
    learner = get_adaptive_learner()
    sample_count = len(learner.memory_df) if hasattr(learner, 'memory_df') and learner.memory_df is not None else 'N/A'
    print(f"  Learner instance: {type(learner).__name__}")
    print(f"  Memory samples: {sample_count}")
    print(f"  Pair cooldowns: {list(learner.pair_cooldown_until.keys()) if hasattr(learner, 'pair_cooldown_until') else 'N/A'}")
    ok_items.append("✅ Adaptive Learner: OK")
except Exception as e:
    issues.append(f"❌ Adaptive Learner error: {e}")

# --- 9. ROUTES KEY CHECK ---
print("\n🌐 ROUTES IMPORT")
try:
    from api.routes import router
    routes_list = [r.path for r in router.routes]
    key_routes = ['/predict', '/log-trade', '/record-outcome', '/stats', '/trades', '/model-performance']
    missing_routes = [r for r in key_routes if not any(r in rr for rr in routes_list)]
    print(f"  Routes found: {len(routes_list)}")
    print(f"  Missing routes: {missing_routes}")
    if missing_routes:
        issues.append(f"❌ Missing routes: {missing_routes}")
    else:
        ok_items.append(f"✅ All {len(key_routes)} key routes present")
except Exception as e:
    issues.append(f"❌ Routes error: {e}")

# --- CHROME EXTENSION ---
print("\n🧩 CHROME EXTENSION")
ext_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'chrome-extension', 'src', 'scripts')
ext_files = ['content.js', 'background.js', 'ws_hook.js']
for f in ext_files:
    fp = os.path.join(ext_dir, f)
    if os.path.exists(fp):
        size_kb = os.path.getsize(fp) // 1024
        # Check for stale live_trade interceptor code
        with open(fp) as fh:
            code = fh.read()
        has_live_trade_handler = 'handleUserLiveTradeEntered' in code
        has_ws_intercept = 'AI_BOT_USER_TRADE_ENTERED' in code
        status = []
        if has_live_trade_handler:
            status.append("⚠️ handleUserLiveTradeEntered still present")
        if has_ws_intercept:
            status.append("⚠️ AI_BOT_USER_TRADE_ENTERED still present")
        if not status:
            status.append("clean")
        print(f"  {f} ({size_kb} KB): {', '.join(status)}")
        if any("⚠️" in s for s in status):
            issues.append(f"⚠️ {f}: manual trade interceptor still present!")
        else:
            ok_items.append(f"✅ {f}: clean")
    else:
        print(f"  ❌ {f} MISSING!")
        issues.append(f"❌ Chrome extension file missing: {f}")

# --- FINAL SUMMARY ---
print("\n" + "=" * 55)
print("   SUMMARY")
print("=" * 55)
print(f"\n✅ OK Items: {len(ok_items)}")
for i in ok_items:
    print(f"  {i}")

if issues:
    print(f"\n⚠️  Issues Found: {len(issues)}")
    for i in issues:
        print(f"  {i}")
else:
    print("\n🎉 ALL SYSTEMS OPERATIONAL — No issues found!")

print("\n" + "=" * 55)
