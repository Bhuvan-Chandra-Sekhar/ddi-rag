"""
database.py — SQLAlchemy engine and session management.
"""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# pool_pre_ping: Supabase's pooler silently drops idle connections; without
# this, SQLAlchemy hands out a dead connection and the first query on it
# fails with psycopg2.OperationalError ("server closed the connection
# unexpectedly") instead of transparently reconnecting.
# pool_recycle: recycle connections proactively before the pooler's own
# idle timeout gets to them.
engine = create_engine(
    DATABASE_URL, connect_args=_connect_args,
    pool_pre_ping=True, pool_recycle=180,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def init_db() -> None:
    """Create all tables. Call once at startup, before serving requests."""
    import models  # noqa: F401 — registers models with Base before create_all
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
