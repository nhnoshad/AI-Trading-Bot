from sqlalchemy import create_engine, Column, Integer, Float, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={'check_same_thread': False} if 'sqlite' in settings.DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ── Models ──────────────────────────────────────────────────────────────────

class Signal(Base):
    __tablename__ = 'signals'
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    pair = Column(String(20), index=True)
    timeframe = Column(String(10))
    signal = Column(String(10))           # BUY / SELL / WAIT
    confidence = Column(Float)
    strength = Column(String(20))         # STRONG / MEDIUM / WEAK
    entry_price = Column(Float)
    analysis_ms = Column(Float, default=0.0)
    indicators_json = Column(Text)        # JSON blob
    features_json = Column(Text)          # 28 raw features JSON for outcome-based learning
    model_preds_json = Column(Text)       # Individual model probabilities (xgb, lgbm, rf)
    reasons_json = Column(Text)           # JSON blob
    recommended_duration = Column(Integer)
    verified_outcome = Column(String(10), nullable=True)  # WIN / LOSS
    trades = relationship('Trade', back_populates='signal_ref')


class Trade(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(Integer, ForeignKey('signals.id'), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    pair = Column(String(20), index=True)
    direction = Column(String(10))        # BUY / SELL
    amount = Column(Float)
    duration = Column(Integer)            # seconds
    entry_price = Column(Float)
    exit_price = Column(Float, nullable=True)
    result = Column(String(10), nullable=True)  # WIN / LOSS / PENDING
    pnl = Column(Float, nullable=True)
    mode = Column(String(10))             # AUTO / MANUAL
    signal_ref = relationship('Signal', back_populates='trades')


class DailyStat(Base):
    __tablename__ = 'daily_stats'
    id = Column(Integer, primary_key=True, index=True)
    date = Column(String(12), unique=True, index=True)
    total_trades = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)
    best_pair = Column(String(20), nullable=True)


class ModelPerformance(Base):
    __tablename__ = 'model_performance'
    id = Column(Integer, primary_key=True, index=True)
    model_version = Column(String(20))
    date = Column(String(25))
    accuracy = Column(Float)
    precision = Column(Float)
    recall = Column(Float)
    f1_score = Column(Float)
    total_predictions = Column(Integer, default=0)
    notes = Column(String(255), nullable=True)


class LearningSample(Base):
    """
    Stores at least 1 month (35+ days) of analyzed feature vectors paired with
    actual trade/market results so the AI continuously learns from real outcomes.
    """
    __tablename__ = 'learning_samples'
    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(Integer, index=True, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    pair = Column(String(20), index=True)
    timeframe = Column(String(10))
    predicted_direction = Column(Integer)      # 1 = BUY, 0 = SELL
    actual_label = Column(Integer)             # 1 = UP (BUY won), 0 = DOWN (SELL won)
    was_correct = Column(Boolean)
    confidence = Column(Float)
    features_json = Column(Text)               # 28 indicator values
    model_preds_json = Column(Text)            # {'xgb': 0.72, 'lgbm': 0.68, 'rf': 0.61}
    source = Column(String(20), default='live_trade')  # live_trade / auto_verify / historical


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
