"""Pydantic schemas for request/response validation."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class Concept(BaseModel):
    slug: str
    title: str
    summary: str
    definition: str
    why_anger: str
    practice: str
    reflection: str
    tags: List[str] = []
    source_notes: Optional[str] = None
    order_index: int = 0

    class Config:
        from_attributes = True


class Resource(BaseModel):
    id: int
    title: str
    creator: Optional[str] = None
    type: str
    description: Optional[str] = None
    url: Optional[str] = None
    tags: List[str] = []
    beginner_level: bool = True
    related_concepts: List[str] = []

    class Config:
        from_attributes = True


class JournalEntryCreate(BaseModel):
    first_arrow: Optional[str] = None
    second_arrow: Optional[str] = None
    body_sensation: Optional[str] = None
    chosen_response: Optional[str] = None
    reflection: Optional[str] = None
    concept_slug: Optional[str] = None


class JournalEntry(JournalEntryCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
