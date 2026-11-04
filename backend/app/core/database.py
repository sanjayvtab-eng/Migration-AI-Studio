import os
import urllib.parse
from sqlalchemy import create_engine, event
from sqlalchemy.exc import TimeoutError as DatabaseTimeout
from threading import BoundedSemaphore
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool, NullPool
from .config import get_settings

class Base(DeclarativeBase): pass

def sanitize_database_url(url: str) -> str:
    """
    Sanitizes database URL:
    - Strips wrapping quotes and whitespace
    - Replaces postgres:// with postgresql://
    - Handles passwords containing special characters (like '@' or accidental brackets from '[YOUR-PASSWORD]')
    """
    if not url:
        return url
    cleaned = url.strip().strip('"').strip("'").strip()
    if cleaned.startswith("postgres://"):
        cleaned = "postgresql://" + cleaned[11:]
    
    if not cleaned.startswith("postgresql://"):
        return cleaned
    
    prefix, rest = cleaned.split("://", 1)
    if "/" in rest:
        creds_and_host, path = rest.split("/", 1)
        path = "/" + path
    else:
        creds_and_host, path = rest, ""
    
    if "@" in creds_and_host:
        last_at = creds_and_host.rfind("@")
        creds = creds_and_host[:last_at]
        host_port = creds_and_host[last_at + 1:]
        
        # If Supabase pooler is used on port 5432 (Session mode with pool_size: 15 limit causing EMAXCONNSESSION),
        # automatically redirect to port 6543 (Transaction mode pooler designed for high concurrency).
        if "pooler.supabase.com" in host_port and ":5432" in host_port:
            host_port = host_port.replace(":5432", ":6543")

        if ":" in creds:
            user, pwd = creds.split(":", 1)
            # Remove accidental surrounding brackets left from [YOUR-PASSWORD] template
            if pwd.endswith("]") and not pwd.startswith("["):
                pwd = pwd[:-1]
            elif pwd.startswith("[") and pwd.endswith("]"):
                pwd = pwd[1:-1]
            elif pwd.startswith("["):
                pwd = pwd[1:]
            
            # URL-encode user and password
            user_enc = urllib.parse.quote_plus(urllib.parse.unquote_plus(user))
            pwd_enc = urllib.parse.quote_plus(urllib.parse.unquote_plus(pwd))
            creds = f"{user_enc}:{pwd_enc}"
        return f"postgresql://{creds}@{host_port}{path}"
    
    if "pooler.supabase.com:5432" in rest:
        rest = rest.replace("pooler.supabase.com:5432", "pooler.supabase.com:6543")
    return f"postgresql://{rest}"

settings = get_settings()

db_url = sanitize_database_url(settings.database_url)

connect_args = {"check_same_thread": False, "timeout": 60} if db_url.startswith("sqlite") else {}
engine_options = {"future": True, "connect_args": connect_args}

if db_url in {"sqlite://", "sqlite:///:memory:"}:
    engine_options["poolclass"] = StaticPool
elif db_url.startswith("postgresql") or db_url.startswith("postgres"):
    engine_options["pool_pre_ping"] = True
    engine_options["pool_recycle"] = 300
    connect_args.update({
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "connect_timeout": 15,
    })
    is_pooler = "pooler.supabase.com" in db_url or ":6543" in db_url
    if is_pooler or os.getenv("DATABASE_USE_NULLPOOL", "false").lower() in ("true", "1", "yes"):
        # Supabase Pooler / PgBouncer manages connection reuse at proxy layer.
        # NullPool ensures connections are freed immediately after query/tx without hoarding client sessions.
        engine_options["poolclass"] = NullPool
    else:
        engine_options["pool_size"] = int(os.getenv("DATABASE_POOL_SIZE", "5"))
        engine_options["max_overflow"] = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
        engine_options["pool_timeout"] = int(os.getenv("DATABASE_POOL_TIMEOUT", "30"))
elif db_url.startswith("mysql"):
    engine_options["pool_pre_ping"] = True
    engine_options["pool_recycle"] = 300
    engine_options["pool_size"] = int(os.getenv("DATABASE_POOL_SIZE", "5"))
    engine_options["max_overflow"] = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
    engine_options["pool_timeout"] = int(os.getenv("DATABASE_POOL_TIMEOUT", "30"))

engine = create_engine(db_url, **engine_options)

def install_connection_budget(target_engine, limit=25, timeout=30):
    # NullPool releases idle clients but does not bound active connections.
    # Budget is per process; operators must account for API replicas/workers.
    _connection_slots = BoundedSemaphore(max(1, limit))
    @event.listens_for(target_engine, "do_connect", retval=True)
    def bounded_connect(dialect, record, args, kwargs):
        if not _connection_slots.acquire(timeout=timeout):
            raise DatabaseTimeout("Control database connection budget exhausted; retry shortly")
        record.info["connection_budget_slot"] = True
        try:
            return dialect.connect(*args, **kwargs)
        except BaseException:
            record.info.pop("connection_budget_slot", None)
            try:
                _connection_slots.release()
            except ValueError:
                pass
            raise
    @event.listens_for(target_engine, "close")
    def release_connection_slot(connection, record):
        if record.info.pop("connection_budget_slot", False):
            try:
                _connection_slots.release()
            except ValueError:
                pass

    @event.listens_for(target_engine, "invalidate")
    def release_connection_slot_invalidate(connection, record, exception=None):
        if record.info.pop("connection_budget_slot", False):
            try:
                _connection_slots.release()
            except ValueError:
                pass

if engine_options.get("poolclass") is NullPool:
    install_connection_budget(
        engine,
        int(os.getenv("DATABASE_MAX_CONNECTIONS", "25")),
        timeout=int(os.getenv("DATABASE_CONNECT_TIMEOUT", "30")),
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
