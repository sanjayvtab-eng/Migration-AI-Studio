import os
import urllib.parse
from sqlalchemy import create_engine
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
    if os.getenv("DATABASE_USE_NULLPOOL", "false").lower() in ("true", "1", "yes"):
        engine_options["poolclass"] = NullPool
    else:
        engine_options["pool_size"] = int(os.getenv("DATABASE_POOL_SIZE", "30"))
        engine_options["max_overflow"] = int(os.getenv("DATABASE_MAX_OVERFLOW", "30"))
        engine_options["pool_timeout"] = int(os.getenv("DATABASE_POOL_TIMEOUT", "60"))
elif db_url.startswith("mysql"):
    engine_options["pool_pre_ping"] = True
    engine_options["pool_recycle"] = 300
    engine_options["pool_size"] = int(os.getenv("DATABASE_POOL_SIZE", "30"))
    engine_options["max_overflow"] = int(os.getenv("DATABASE_MAX_OVERFLOW", "30"))
    engine_options["pool_timeout"] = int(os.getenv("DATABASE_POOL_TIMEOUT", "60"))

engine = create_engine(db_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
