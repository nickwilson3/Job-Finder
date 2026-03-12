import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_DATABASE_URL = os.environ.get("DATABASE_URL")

if _DATABASE_URL:
    # Production: external PostgreSQL (Supabase, etc.)
    # Supabase sometimes gives a "postgres://" URL — SQLAlchemy requires "postgresql://"
    if _DATABASE_URL.startswith("postgres://"):
        _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(_DATABASE_URL)
else:
    # Local development: SQLite
    DB_PATH = Path(__file__).parent.parent / "web_data" / "jobfinder.db"
    DB_PATH.parent.mkdir(exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from web.models import User, Run, Job  # noqa: F401 — ensure models are registered
    Base.metadata.create_all(bind=engine)

    # Add new columns to existing tables (safe to run on already-migrated DBs)
    from sqlalchemy import text
    new_cols = [
        ("runs", "progress_pct", "INTEGER DEFAULT 0"),
        ("runs", "status_message", "VARCHAR"),
        ("runs", "queue_position", "INTEGER DEFAULT 0"),
    ]
    with engine.connect() as conn:
        for table, col, col_def in new_cols:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))
                conn.commit()
            except Exception:
                conn.rollback()
