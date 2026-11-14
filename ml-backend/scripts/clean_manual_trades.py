import sqlite3
import os
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'trading_bot.db')
CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'rolling_30d_learning_memory.csv')

def clean_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT count(*) FROM trades WHERE mode = 'MANUAL'")
    manual_count = c.fetchone()[0]
    print(f"Manual trades before: {manual_count}")

    c.execute("SELECT count(*) FROM learning_samples WHERE source = 'live_trade'")
    live_samples = c.fetchone()[0]
    print(f"Live trade samples before: {live_samples}")

    c.execute("DELETE FROM trades WHERE mode = 'MANUAL'")
    deleted_trades = c.rowcount
    print(f"Deleted {deleted_trades} MANUAL trades from trades table.")

    c.execute("DELETE FROM learning_samples WHERE source = 'live_trade'")
    deleted_samples = c.rowcount
    print(f"Deleted {deleted_samples} live_trade samples from learning_samples table.")

    # Rebuild daily_stats based on remaining trades (pure AI predictions)
    c.execute("DELETE FROM daily_stats")
    c.execute("""
        SELECT date(timestamp), count(*), 
               sum(case when result = 'WIN' then 1 else 0 end),
               sum(case when result = 'LOSS' then 1 else 0 end),
               sum(pnl)
        FROM trades
        WHERE timestamp IS NOT NULL
        GROUP BY date(timestamp)
    """)
    daily_rows = c.fetchall()
    for d, total, wins, losses, pnl in daily_rows:
        wins = wins or 0
        losses = losses or 0
        pnl = round(pnl or 0.0, 2)
        wr = round(wins / total * 100, 2) if total > 0 else 0.0
        c.execute("""
            INSERT INTO daily_stats (date, total_trades, wins, losses, win_rate, total_pnl)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (d, total, wins, losses, wr, pnl))

    conn.commit()

    c.execute("SELECT count(*), mode FROM trades GROUP BY mode")
    print("Remaining trades by mode:", c.fetchall())

    c.execute("SELECT count(*), source FROM learning_samples GROUP BY source")
    print("Remaining learning samples by source:", c.fetchall())

    conn.close()

def clean_csv():
    if os.path.exists(CSV_PATH):
        df = pd.read_csv(CSV_PATH)
        initial_len = len(df)
        if 'source' in df.columns:
            df_filtered = df[df['source'] != 'live_trade']
            removed = initial_len - len(df_filtered)
            df_filtered.to_csv(CSV_PATH, index=False)
            print(f"Filtered {removed} live_trade rows from rolling CSV. Remaining: {len(df_filtered)}")
        else:
            print("No source column found in rolling CSV.")

if __name__ == '__main__':
    clean_database()
    clean_csv()
