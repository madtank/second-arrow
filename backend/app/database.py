"""SQLite database setup using SQLAlchemy.

The database file lives next to the backend by default. Override with the
DATABASE_URL environment variable (see .env.example).
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Default to a file-based SQLite db in the backend directory.
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "second_arrow.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

# check_same_thread is required for SQLite when used with FastAPI's threadpool.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
