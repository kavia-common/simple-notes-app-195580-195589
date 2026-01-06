from sqlalchemy import Column, Integer, Text, String

from src.db import Base


class Note(Base):
    """SQLAlchemy model representing a note."""
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
