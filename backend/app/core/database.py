from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool
from .config import get_settings

class Base(DeclarativeBase): pass

settings = get_settings()

db_url = settings.database_url
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False, "timeout": 60} if db_url.startswith("sqlite") else {}
engine_options = {"future": True, "connect_args": connect_args}

if db_url in {"sqlite://", "sqlite:///:memory:"}:
    engine_options["poolclass"] = StaticPool
elif db_url.startswith("postgresql"):
    engine_options["pool_pre_ping"] = True
    engine_options["pool_recycle"] = 300

engine = create_engine(db_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
