from typing import List

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from src.db import Base, engine, get_db
from src.models import Note
from src.schemas import NoteCreate, NoteOut, NoteUpdate

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

# React dev/preview runs on port 3000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup_create_tables() -> None:
    """
    Create database tables if they do not exist.

    This keeps the project simple (no explicit migration tooling) and is safe for this app's scope.
    """
    Base.metadata.create_all(bind=engine)


# PUBLIC_INTERFACE
@app.get("/", tags=["Health"], summary="Health check", description="Returns a simple health payload.")
def health_check():
    """Health check endpoint used by previews/monitoring."""
    return {"message": "Healthy"}


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
    note = Note(title=payload.title.strip(), content=payload.content)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


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
