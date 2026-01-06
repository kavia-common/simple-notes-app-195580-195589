import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _normalize_sqlalchemy_postgres_url(url: str) -> str:
    """
    Normalize a Postgres URL into a SQLAlchemy psycopg2 URL.

    Accepts:
    - postgresql://...
    - postgresql+psycopg2://...

    Returns:
    - postgresql+psycopg2://...
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _read_db_connection_txt() -> str | None:
    """
    Read a connection string from a sibling database container's db_connection.txt if available.

    The expected format is:
      psql postgresql://user:pass@host:port/dbname
    """
    # This backend container lives at: <workspace>/notes_backend/src/db.py
    # The database container is a sibling workspace: simple-notes-app-.../database/db_connection.txt
    # We try a relative walk-up to the common code-generation root, then locate any matching path.
    # If this path structure changes, env vars (POSTGRES_URL etc.) should be used instead.
    here = Path(__file__).resolve()
    workspace_root = here.parents[3]  # .../simple-notes-app-195580-195589
    codegen_root = workspace_root.parent  # .../code-generation

    # Known path from this task context:
    candidate = codegen_root / "simple-notes-app-195580-195590" / "database" / "db_connection.txt"
    if not candidate.exists():
        return None

    raw = candidate.read_text(encoding="utf-8").strip()
    if not raw:
        return None

    # Allow either "psql <url>" or just "<url>"
    if raw.startswith("psql "):
        raw = raw[len("psql ") :].strip()

    if raw.startswith("postgresql://") or raw.startswith("postgresql+psycopg2://"):
        return _normalize_sqlalchemy_postgres_url(raw)

    return raw


def _build_database_url() -> str:
    """
    Build a SQLAlchemy database URL.

    Preference order:
    1) POSTGRES_URL (SQLAlchemy-compatible or postgresql:// URL)
    2) POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB/POSTGRES_PORT (compose a URL)
    3) Read ../database/db_connection.txt from the database container workspace (if present)
    4) Final fallback: localhost:5001 (matches the running Postgres container port in this environment)

    Notes:
    - Do not read .env directly; runtime env is injected by the orchestrator.
    """
    postgres_url = os.getenv("POSTGRES_URL")
    if postgres_url:
        # Accept either "postgresql://..." or "postgresql+psycopg2://..."
        if postgres_url.startswith("postgresql://") or postgres_url.startswith("postgresql+psycopg2://"):
            return _normalize_sqlalchemy_postgres_url(postgres_url)
        # If something else is provided, return as-is; SQLAlchemy will validate.
        return postgres_url

    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    db = os.getenv("POSTGRES_DB")
    port = os.getenv("POSTGRES_PORT")
    if user and password and db and port:
        # Host is localhost because the DB is exposed to this environment on a forwarded local port.
        return f"postgresql+psycopg2://{user}:{password}@localhost:{port}/{db}"

    db_txt_url = _read_db_connection_txt()
    if db_txt_url:
        return db_txt_url

    # Default to the running Postgres container port for this environment.
    # (Database container is exposed on TCP port 5001 per work item context.)
    return "postgresql+psycopg2://appuser:dbuser123@localhost:5001/myapp"


DATABASE_URL = _build_database_url()

# Engine + session configuration
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# PUBLIC_INTERFACE
def get_db():
    """FastAPI dependency that yields a database session and ensures it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
