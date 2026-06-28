"""
ARIS Database Layer
Handles SQLite storage of all conversations using SQLAlchemy ORM.
"""

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
import os

def utc_now():
    return datetime.now(timezone.utc)

# ─── DATABASE SETUP ────────────────────────────────────────────────────────────

# SQLite file will be created at ARIS/backend/aris.db
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'aris.db')}"

# The engine is the actual connection to the database file
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # Required for SQLite + FastAPI
)

# SessionLocal is a factory — call it to get a database session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class that all our database models will inherit from
Base = declarative_base()

# ─── DATABASE MODELS ───────────────────────────────────────────────────────────

class ConversationMessage(Base):
    """
    Represents a single message in a conversation.
    Each row = one message (either from user or from ARIS).
    """
    __tablename__ = "conversation_messages"

    id         = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(String(100), index=True, nullable=False)   # Which conversation
    role       = Column(String(10), nullable=False)                 # "user" or "model"
    text       = Column(Text, nullable=False)                       # The message content
    model_used = Column(String(50), nullable=True)                  # Which AI model replied (for model turns)
    timestamp  = Column(DateTime, default=utc_now)         # When it was sent

    def __repr__(self):
        preview = self.text[:40] + "..." if len(self.text) > 40 else self.text
        return f"<Message [{self.role}] session='{self.session_id}' text='{preview}'>"


class SessionSummary(Base):
    """
    Tracks metadata about each conversation session.
    Useful for listing past conversations, showing last active time, etc.
    """
    __tablename__ = "session_summaries"

    id           = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id   = Column(String(100), unique=True, index=True, nullable=False)
    created_at   = Column(DateTime, default=utc_now)
    last_active  = Column(DateTime, default=utc_now, onupdate=utc_now)
    message_count = Column(Integer, default=0)

    def __repr__(self):
        return f"<Session '{self.session_id}' messages={self.message_count}>"


# ─── DATABASE HELPERS ──────────────────────────────────────────────────────────

def init_db():
    """
    Create all tables in the database if they don't exist yet.
    Safe to call multiple times — won't overwrite existing data.
    """
    Base.metadata.create_all(bind=engine)
    print("[ARIS DB] Database initialized. Tables ready.")


def get_db():
    """
    Dependency injector for FastAPI routes.
    Yields a database session and ensures it's closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def save_message(session_id: str, role: str, text: str, model_used: str = None):
    """
    Save a single message to the database.
    Also updates (or creates) the session summary record.
    """
    db = SessionLocal()
    try:
        # Save the message
        msg = ConversationMessage(
            session_id=session_id,
            role=role,
            text=text,
            model_used=model_used
        )
        db.add(msg)

        # Update or create the session summary
        summary = db.query(SessionSummary).filter(
            SessionSummary.session_id == session_id
        ).first()

        if summary:
            summary.message_count += 1
            summary.last_active = utc_now()
        else:
            summary = SessionSummary(
                session_id=session_id,
                message_count=1
            )
            db.add(summary)

        db.commit()

    except Exception as e:
        db.rollback()
        print(f"[ARIS DB] Error saving message: {e}")
    finally:
        db.close()


def load_session_from_db(session_id: str) -> list[dict]:
    """
    Load all messages for a session from the database.
    Returns them in the same format our in-memory store uses.
    """
    db = SessionLocal()
    try:
        messages = db.query(ConversationMessage).filter(
            ConversationMessage.session_id == session_id
        ).order_by(ConversationMessage.timestamp).all()

        return [{"role": msg.role, "text": msg.text} for msg in messages]
    finally:
        db.close()


def load_all_sessions_from_db() -> dict[str, list[dict]]:
    """
    Load ALL conversations from the database into memory.
    Called once on server startup so ARIS remembers everything.
    """
    db = SessionLocal()
    try:
        all_messages = db.query(ConversationMessage).order_by(
            ConversationMessage.session_id,
            ConversationMessage.timestamp
        ).all()

        # Group messages by session_id
        sessions: dict[str, list[dict]] = {}
        for msg in all_messages:
            if msg.session_id not in sessions:
                sessions[msg.session_id] = []
            sessions[msg.session_id].append({"role": msg.role, "text": msg.text})

        print(f"[ARIS DB] Loaded {len(sessions)} session(s) from database.")
        return sessions
    finally:
        db.close()


def get_all_sessions() -> list[dict]:
    """Return a summary list of all known sessions."""
    db = SessionLocal()
    try:
        summaries = db.query(SessionSummary).order_by(
            SessionSummary.last_active.desc()
        ).all()
        return [
            {
                "session_id": s.session_id,
                "message_count": s.message_count,
                "created_at": s.created_at.isoformat(),
                "last_active": s.last_active.isoformat()
            }
            for s in summaries
        ]
    finally:
        db.close()