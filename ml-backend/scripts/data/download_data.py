"""
Data Download Script
Downloads historical OHLCV data from multiple sources for model training.
Usage: python scripts/data/download_data.py --pair EURUSD --days 365
"""
import argparse
import os
import sys
import pandas as pd
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), '../../data')
os.makedirs(DATA_DIR, exist_ok=True)


def download_yfinance(pair: str, interval: str, period: str) -> pd.DataFrame:
    try:
        import yfinance as yf
        # Map pair to Yahoo symbol
        symbol_map = {
            'EURUSD': 'EURUSD=X', 'GBPUSD': 'GBPUSD=X', 'USDJPY': 'JPY=X',
            'AUDUSD': 'AUDUSD=X', 'EURGBP': 'EURGBP=X', 'GBPJPY': 'GBPJPY=X',
            'BTCUSDT': 'BTC-USD', 'ETHUSDT': 'ETH-USD'
        }
        symbol = symbol_map.get(pair.upper(), pair)
        logger.info(f'Downloading {symbol} ({interval}) from Yahoo Finance...')
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        df.reset_index(inplace=True)
        df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
        df = df[['datetime' if 'datetime' in df.columns else 'date', 'open', 'high', 'low', 'close', 'volume']]
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df.dropna(inplace=True)
        logger.info(f'Downloaded {len(df)} candles from Yahoo Finance')
        return df
    except Exception as e:
        logger.error(f'Yahoo Finance download failed: {e}')
        return pd.DataFrame()


def download_binance(pair: str, interval: str, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        from binance.client import Client
        client = Client()
        interval_map = {
            '1m': Client.KLINE_INTERVAL_1MINUTE,
            '5m': Client.KLINE_INTERVAL_5MINUTE,
            '15m': Client.KLINE_INTERVAL_15MINUTE,
            '1h': Client.KLINE_INTERVAL_1HOUR
        }
        bi = interval_map.get(interval, Client.KLINE_INTERVAL_1MINUTE)
        logger.info(f'Downloading {pair} ({interval}) from Binance...')
        klines = client.get_historical_klines(pair.upper(), bi, start_date, end_date)
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy', 'taker_quote', 'ignore'
        ])
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        logger.info(f'Downloaded {len(df)} candles from Binance')
        return df
    except Exception as e:
        logger.error(f'Binance download failed: {e}')
        return pd.DataFrame()


def create_labels(df: pd.DataFrame, lookahead: int = 1) -> pd.DataFrame:
    """Create binary labels: 1=BUY (price goes up), 0=SELL (price goes down)."""
    df = df.copy()
    df['future_close'] = df['close'].shift(-lookahead)
    df['label'] = (df['future_close'] > df['close']).astype(int)
    df.dropna(subset=['label'], inplace=True)
    return df


def main():
    parser = argparse.ArgumentParser(description='Download trading data')
    parser.add_argument('--pair', default='EURUSD', help='Trading pair (e.g. EURUSD, BTCUSDT)')
    parser.add_argument('--interval', default='1m', choices=['1m', '5m', '15m', '1h'])
    parser.add_argument('--source', default='yfinance', choices=['yfinance', 'binance'])
    parser.add_argument('--days', type=int, default=60, help='Days of history to download')
    args = parser.parse_args()

    end = datetime.now()
    start = end - timedelta(days=args.days)

    if args.source == 'yfinance':
        period_map = {7: '7d', 14: '14d', 30: '1mo', 60: '60d', 90: '3mo', 365: '1y', 730: '2y'}
        period = period_map.get(args.days, '60d')
        df = download_yfinance(args.pair, args.interval, period)
    elif args.source == 'binance':
        df = download_binance(args.pair, args.interval,
                              start.strftime('%d %b, %Y'), end.strftime('%d %b, %Y'))
    else:
        logger.error('Unknown source')
        sys.exit(1)

    if df.empty:
        logger.error('No data downloaded.')
        sys.exit(1)

    df = create_labels(df)
    out_path = os.path.join(DATA_DIR, f'{args.pair}_{args.interval}_{args.source}.csv')
    df.to_csv(out_path, index=False)
    logger.info(f'Saved {len(df)} labelled rows to {out_path}')
    logger.info(f'Label distribution:\n{df["label"].value_counts()}')


if __name__ == '__main__':
    main()
