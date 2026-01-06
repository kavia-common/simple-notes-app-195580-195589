import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _build_database_url() -> str:
    """
    Build a SQLAlchemy database URL.

    Preference order:
    1) POSTGRES_URL (if provided, assumed to be SQLAlchemy-compatible or a postgres URL)
    2) POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB/POSTGRES_PORT (compose a URL)
    3) Fallback to local dev connection matching database/db_connection.txt

    Notes:
    - The orchestrator should set these env vars in the container's .env.
    - We avoid reading .env directly; FastAPI runtime will load env.
    """
    postgres_url = os.getenv("POSTGRES_URL")
    if postgres_url:
        # Accept either "postgresql://..." or "postgresql+psycopg2://..."
        if postgres_url.startswith("postgresql://") or postgres_url.startswith("postgresql+psycopg2://"):
            if postgres_url.startswith("postgresql://"):
                return postgres_url.replace("postgresql://", "postgresql+psycopg2://", 1)
            return postgres_url
        # If something else is provided, return as-is; SQLAlchemy will validate.
        return postgres_url

    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    db = os.getenv("POSTGRES_DB")
    port = os.getenv("POSTGRES_PORT")
    if user and password and db and port:
        return f"postgresql+psycopg2://{user}:{password}@localhost:{port}/{db}"

    # Fallback that matches /database/db_connection.txt: psql postgresql://appuser:dbuser123@localhost:5000/myapp
    return "postgresql+psycopg2://appuser:dbuser123@localhost:5000/myapp"


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
