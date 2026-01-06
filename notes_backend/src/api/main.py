import logging
import os
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.db import Base, engine, get_db
from src.models import Note
from src.schemas import NoteCreate, NoteOut, NoteUpdate

logger = logging.getLogger(__name__)

openapi_tags = [
    {"name": "Health", "description": "Service health and readiness endpoints."},
    {"name": "Notes", "description": "CRUD operations for notes."},
]

app = FastAPI(
    title="Notes API",
    description="Simple Notes backend API supporting CRUD operations with PostgreSQL persistence.",
    version="1.0.0",
    openapi_tags=openapi_tags,
)


def _parse_allowed_origins() -> List[str]:
    """
    Parse comma-separated ALLOWED_ORIGINS from env.

    Falls back to localhost dev origins when not set.

    Note:
    - In Kavia preview environments, the frontend origin is typically a
      `https://vscode-internal-<id>-...:3000` URL, not `http://localhost:3000`.
      That origin must be allowed for browser requests to succeed.
    """
    raw = (os.getenv("ALLOWED_ORIGINS") or "").strip()
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]

    origins = [o.strip() for o in raw.split(",")]
    return [o for o in origins if o]


def _parse_allowed_origin_regex() -> str | None:
    """
    Return a regex that matches allowed origins for local development and preview environments.

    Env:
      ALLOWED_ORIGIN_REGEX: optional regex override.

    Default behavior:
      - Allow the Kavia preview domain pattern used by the running frontend:
        https://vscode-internal-<something>:3000
    """
    raw = (os.getenv("ALLOWED_ORIGIN_REGEX") or "").strip()
    if raw:
        return raw

    # Allow Kavia preview URLs running the React dev server on port 3000.
    # Example: https://vscode-internal-37437-qa.qa01.cloud.kavia.ai:3000
    return r"^https?://vscode-internal-[^:]+:3000$"


# React dev/preview runs on port 3000
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_allowed_origins(),
    allow_origin_regex=_parse_allowed_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Return JSON for unexpected errors.

    This prevents the frontend from seeing non-JSON bodies and helps surface real issues
    (DB errors, coding errors) instead of opaque 'failed to fetch' symptoms.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal Server Error"},
    )


@app.on_event("startup")
def _startup_create_tables() -> None:
    """
    Create database tables if they do not exist.

    Important: do NOT fail application startup if the DB is unavailable/misconfigured.
    The service should still bind to its port and expose /health/db to report readiness.
    """
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        logger.exception("Database initialization failed during startup (tables not created).")


# PUBLIC_INTERFACE
@app.get("/", tags=["Health"], summary="Health check", description="Returns a simple health payload.")
def health_check() -> Dict[str, str]:
    """Health check endpoint used by previews/monitoring."""
    return {"message": "Healthy"}


# PUBLIC_INTERFACE
@app.get(
    "/health/db",
    tags=["Health"],
    summary="Database health check",
    description=(
        "Verifies PostgreSQL connectivity by running a lightweight read-only query (SELECT 1). "
        "Returns status=up when the query succeeds, otherwise status=down with error details."
    ),
)
def health_check_db(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Database readiness endpoint used to verify DB connectivity."""
    try:
        # Use an explicit, short query to validate both connectivity and ability to execute statements.
        value = db.execute(text("SELECT 1")).scalar_one()
        return {"status": "up", "query": "SELECT 1", "result": int(value)}
    except Exception as exc:
        # Keep details for debugging; do not raise to avoid hiding error metadata behind generic FastAPI errors.
        return {"status": "down", "error": str(exc)}


# PUBLIC_INTERFACE
@app.get(
    "/notes",
    response_model=List[NoteOut],
    tags=["Notes"],
    summary="List notes",
    description="Return all notes ordered by most recent (highest id first).",
)
def list_notes(db: Session = Depends(get_db)) -> List[NoteOut]:
    """List all notes."""
    notes = db.query(Note).order_by(Note.id.desc()).all()
    return notes


# PUBLIC_INTERFACE
@app.post(
    "/notes",
    response_model=NoteOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Notes"],
    summary="Create note",
    description="Create a new note with a title and content.",
)
def create_note(payload: NoteCreate, db: Session = Depends(get_db)) -> NoteOut:
    """Create a note."""
    logger.info("Creating note title_len=%s content_len=%s", len(payload.title), len(payload.content))
    try:
        note = Note(title=payload.title.strip(), content=payload.content)
        db.add(note)
        db.commit()
        db.refresh(note)
        return note
    except Exception as exc:
        # Ensure error is logged; exception handler will convert unhandled exceptions to JSON.
        logger.exception("Failed creating note due to server error: %s", str(exc))
        raise


# PUBLIC_INTERFACE
@app.get(
    "/notes/{note_id}",
    response_model=NoteOut,
    tags=["Notes"],
    summary="Get note",
    description="Fetch a single note by ID.",
)
def get_note(note_id: int, db: Session = Depends(get_db)) -> NoteOut:
    """Get a note by id."""
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


# PUBLIC_INTERFACE
@app.put(
    "/notes/{note_id}",
    response_model=NoteOut,
    tags=["Notes"],
    summary="Update note",
    description="Update a note by ID (full update; any omitted fields remain unchanged).",
)
def update_note(note_id: int, payload: NoteUpdate, db: Session = Depends(get_db)) -> NoteOut:
    """Update a note by id."""
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if payload.title is not None:
        note.title = payload.title.strip()
    if payload.content is not None:
        note.content = payload.content

    db.add(note)
    db.commit()
    db.refresh(note)
    return note


# PUBLIC_INTERFACE
@app.delete(
    "/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Notes"],
    summary="Delete note",
    description="Delete a note by ID.",
)
def delete_note(note_id: int, db: Session = Depends(get_db)) -> Response:
    """Delete a note by id."""
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    db.delete(note)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
