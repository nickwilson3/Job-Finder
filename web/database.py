from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

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
