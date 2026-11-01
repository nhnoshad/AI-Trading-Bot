from app.core.database import SessionLocal, Trade, DailyStat
from sqlalchemy import func
from datetime import datetime

def run_cleanup():
    db = SessionLocal()
    try:
        deleted = db.query(Trade).filter(Trade.direction.in_(['WAIT', 'wait'])).delete(synchronize_session=False)
        db.commit()
        print(f"Deleted {deleted} legacy WAIT trades.")

        # Re-sync all daily stats
        all_dates = db.query(func.date(Trade.timestamp)).distinct().all()
        for (d_str,) in all_dates:
            if not d_str:
                continue
            day_trades = db.query(Trade).filter(func.date(Trade.timestamp) == d_str).all()
            total = len(day_trades)
            wins = sum(1 for t in day_trades if t.result == 'WIN')
            losses = sum(1 for t in day_trades if t.result == 'LOSS')
            pnl = sum(t.pnl for t in day_trades if t.pnl is not None)
            wr = (wins / total * 100.0) if total > 0 else 0.0

            stat = db.query(DailyStat).filter(DailyStat.date == str(d_str)).first()
            if stat:
                stat.total_trades = total
                stat.wins = wins
                stat.losses = losses
                stat.win_rate = wr
                stat.total_pnl = pnl
            else:
                stat = DailyStat(
                    date=str(d_str),
                    total_trades=total,
                    wins=wins,
                    losses=losses,
                    win_rate=wr,
                    total_pnl=pnl
                )
                db.add(stat)
        db.commit()
        print("Successfully re-synchronized all DailyStat entries.")
    finally:
        db.close()

if __name__ == '__main__':
    run_cleanup()
