from pydantic import BaseModel, Field, ConfigDict


class NoteBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Short note title (1-200 chars).")
    content: str = Field(..., min_length=1, description="Full note content (non-empty).")


class NoteCreate(NoteBase):
    """Schema for creating a note."""


class NoteUpdate(BaseModel):
    """Schema for updating a note (partial update)."""
    title: str | None = Field(None, min_length=1, max_length=200, description="Updated title (1-200 chars).")
    content: str | None = Field(None, min_length=1, description="Updated content (non-empty).")


class NoteOut(NoteBase):
    """Schema returned for a note."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Database ID of the note.")
