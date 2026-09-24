from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool
from .config import get_settings

class Base(DeclarativeBase): pass

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine_options = {"future": True, "connect_args": connect_args}
if settings.database_url in {"sqlite://", "sqlite:///:memory:"}:
    engine_options["poolclass"] = StaticPool
engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
