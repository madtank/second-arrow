"""SQLAlchemy models for Second Arrow.

Tags and list-like fields are stored as JSON text for simplicity (this is a
small local app — no need for join tables yet).
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from .database import Base


class Concept(Base):
    __tablename__ = "concepts"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    definition = Column(Text, nullable=False)
    why_anger = Column(Text, nullable=False)
    practice = Column(Text, nullable=False)
    reflection = Column(Text, nullable=False)
    tags = Column(Text, nullable=False, default="[]")  # JSON array of strings
    source_notes = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=False, default=0)


class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    creator = Column(String, nullable=True)
    type = Column(String, nullable=False)  # book | website | youtube | podcast | talk | article | practice
    description = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    tags = Column(Text, nullable=False, default="[]")  # JSON array
    beginner_level = Column(Boolean, nullable=False, default=True)
    related_concepts = Column(Text, nullable=False, default="[]")  # JSON array of concept slugs


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    first_arrow = Column(Text, nullable=True)       # what happened
    second_arrow = Column(Text, nullable=True)      # the extra suffering / story
    body_sensation = Column(Text, nullable=True)    # where it's felt
    chosen_response = Column(Text, nullable=True)   # skillful response chosen
    reflection = Column(Text, nullable=True)        # reflection notes
    concept_slug = Column(String, nullable=True)    # optional related concept
