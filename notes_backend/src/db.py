import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
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


def _env_postgres_url_if_usable() -> str | None:
    """
    Return a SQLAlchemy-ready URL from POSTGRES_URL, but only if it is usable.

    In this environment the orchestrator may inject a credential-less POSTGRES_URL such as:
      postgresql://localhost:5000/myapp

    psycopg2 will then default the username to the OS user (e.g. 'kavia'), causing:
      FATAL: role "kavia" does not exist

    To avoid startup failure, we only accept POSTGRES_URL when it includes credentials (user+password)
    OR when an explicit username is provided (password may still be handled by other means, but for
    this project we require both for reliability).
    """
    postgres_url = os.getenv("POSTGRES_URL")
    if not postgres_url:
        return None

    # Accept either "postgresql://..." or "postgresql+psycopg2://..."
    if postgres_url.startswith(("postgresql://", "postgresql+psycopg2://")):
        normalized = _normalize_sqlalchemy_postgres_url(postgres_url)
        try:
            parsed = make_url(normalized)
        except Exception:
            # If URL is malformed, let SQLAlchemy raise later by returning it as-is.
            return normalized

        # Require explicit credentials to avoid falling back to OS user.
        if parsed.username and parsed.password:
            return normalized

        # Credential-less URL is not usable in this project's setup.
        return None

    # If something else is provided, return as-is; SQLAlchemy will validate.
    return postgres_url


def _build_database_url() -> str:
    """
    Build a SQLAlchemy database URL.

    Preference order:
    1) POSTGRES_URL (only if it includes explicit credentials; see _env_postgres_url_if_usable)
    2) POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB/POSTGRES_PORT (compose a URL)
    3) Read ../database/db_connection.txt from the database container workspace (if present)
    4) Final fallback: localhost:5001

    Notes:
    - Do not read .env directly; runtime env is injected by the orchestrator.
    """
    usable_env_url = _env_postgres_url_if_usable()
    if usable_env_url:
        return usable_env_url

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

    # Final fallback (should be overridden by env in real deployments).
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
