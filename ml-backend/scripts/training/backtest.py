"""
Backtesting Engine
==================
Simulates trading signals on historical data to evaluate strategy performance.

Usage:
    python scripts/training/backtest.py --data data/EURUSD_1m_yfinance.csv --confidence 65

Outputs:
    - Win rate, total trades, max drawdown, Sharpe ratio, profit factor
    - Equity curve CSV
    - Confusion matrix
"""

import os
import sys
import argparse
import json
import joblib
import numpy as np
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from app.services.indicators import calculate_indicators, FEATURE_COLUMNS

MODELS_DIR = os.path.join(os.path.dirname(__file__), '../../models')
DATA_DIR = os.path.join(os.path.dirname(__file__), '../../data')


def run_backtest(df: pd.DataFrame, model, scaler, confidence_threshold: float = 0.65,
                 trade_amount: float = 10.0, payout: float = 0.85) -> dict:
    """
    Simulate trades on historical data using the trained model.
    Only takes trades when model confidence >= threshold.
    Returns comprehensive performance metrics.
    """
    # Feature engineering
    df_feat = calculate_indicators(df.to_dict('records'))
    available = [f for f in FEATURE_COLUMNS if f in df_feat.columns]
    X = df_feat[available].values
    X_scaled = scaler.transform(X)

    proba = model.predict_proba(X_scaled)
    predictions = model.predict(X_scaled)
    confidence = np.max(proba, axis=1)

    # Simulate trades
    equity = [0.0]
    trades = []
    win_count = 0
    loss_count = 0

    for i in range(len(df_feat) - 1):
        conf = confidence[i]
        if conf < confidence_threshold:
            equity.append(equity[-1])
            continue

        pred = predictions[i]
        # Actual next candle direction (ground truth)
        actual = 1 if df_feat['close'].iloc[i + 1] > df_feat['close'].iloc[i] else 0

        is_win = (pred == actual)
        pnl = trade_amount * payout if is_win else -trade_amount
        equity.append(equity[-1] + pnl)

        if is_win:
            win_count += 1
        else:
            loss_count += 1

        trades.append({
            'index': i,
            'prediction': 'BUY' if pred == 1 else 'SELL',
            'confidence': round(conf * 100, 2),
            'result': 'WIN' if is_win else 'LOSS',
            'pnl': round(pnl, 2),
            'equity': round(equity[-1], 2)
        })

    total_trades = win_count + loss_count
    win_rate = win_count / total_trades * 100 if total_trades > 0 else 0
    total_pnl = equity[-1]

    # Max drawdown
    peak = 0
    max_dd = 0
    for e in equity:
        if e > peak:
            peak = e
        dd = peak - e
        if dd > max_dd:
            max_dd = dd

    # Sharpe ratio (simplified)
    trade_returns = [t['pnl'] for t in trades]
    if len(trade_returns) > 1:
        mean_r = np.mean(trade_returns)
        std_r = np.std(trade_returns)
        sharpe = (mean_r / std_r * np.sqrt(252)) if std_r > 0 else 0
    else:
        sharpe = 0

    # Profit factor
    gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    return {
        'total_trades': total_trades,
        'wins': win_count,
        'losses': loss_count,
        'win_rate': round(win_rate, 2),
        'total_pnl': round(total_pnl, 2),
        'max_drawdown': round(max_dd, 2),
        'sharpe_ratio': round(sharpe, 3),
        'profit_factor': round(profit_factor, 3),
        'trades_filtered': len(df_feat) - total_trades,
        'confidence_threshold': confidence_threshold,
        'equity_curve': equity[::max(1, len(equity) // 200)]  # sample for chart
    }


def main():
    parser = argparse.ArgumentParser(description='Backtest the trading model')
    parser.add_argument('--data', default='data/EURUSD_1m_yfinance.csv')
    parser.add_argument('--confidence', type=float, default=65.0, help='Min confidence 0-100')
    parser.add_argument('--amount', type=float, default=10.0, help='Trade amount ($)')
    parser.add_argument('--payout', type=float, default=0.85, help='Payout ratio (e.g. 0.85 = 85%%)')
    args = parser.parse_args()

    # Load data
    if not os.path.exists(args.data):
        print(f'Data file not found: {args.data}')
        print('Run: python scripts/data/download_data.py first')
        sys.exit(1)

    df = pd.read_csv(args.data)
    print(f'Loaded {len(df)} candles from {args.data}')

    # Load model
    model_path = os.path.join(MODELS_DIR, 'ensemble_model.pkl')
    scaler_path = os.path.join(MODELS_DIR, 'scaler.pkl')
    if not (os.path.exists(model_path) and os.path.exists(scaler_path)):
        print('Models not found. Run train_model.py first.')
        sys.exit(1)

    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)
    print('Models loaded.')

    # Run backtest
    print(f'\nRunning backtest (confidence >= {args.confidence}%, amount=${args.amount})...')
    results = run_backtest(df, model, scaler,
                           confidence_threshold=args.confidence / 100,
                           trade_amount=args.amount,
                           payout=args.payout)

    # Display results
    print('\n' + '=' * 50)
    print('BACKTEST RESULTS')
    print('=' * 50)
    print(f'Total Trades:      {results["total_trades"]}')
    print(f'Wins:              {results["wins"]}')
    print(f'Losses:            {results["losses"]}')
    print(f'Win Rate:          {results["win_rate"]}%')
    print(f'Total P&L:         ${results["total_pnl"]:.2f}')
    print(f'Max Drawdown:      ${results["max_drawdown"]:.2f}')
    print(f'Sharpe Ratio:      {results["sharpe_ratio"]}')
    print(f'Profit Factor:     {results["profit_factor"]}')
    print(f'Skipped (low conf): {results["trades_filtered"]}')
    print('=' * 50)

    # Save equity curve
    equity_path = os.path.join(DATA_DIR, f'equity_curve_{int(args.confidence)}.csv')
    pd.DataFrame({'equity': results['equity_curve']}).to_csv(equity_path, index=False)
    print(f'Equity curve saved to {equity_path}')

    # Save full results
    out = {k: v for k, v in results.items() if k != 'equity_curve'}
    print(f'\nJSON results:\n{json.dumps(out, indent=2)}')


if __name__ == '__main__':
    main()
