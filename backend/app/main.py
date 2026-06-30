"""Second Arrow FastAPI application.

Run locally with:
    uvicorn app.main:app --reload
"""
import json
import os
from contextlib import asynccontextmanager
from typing import List

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import models, schemas
from .database import Base, SessionLocal, engine, get_db
from .seed import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables and seed content on startup.
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Second Arrow API", version="0.1.0", lifespan=lifespan)

# Allow the Vite dev server (and configurable extra origins) to call the API.
default_origins = "http://localhost:5173,http://127.0.0.1:5173"
origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", default_origins).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Serializers (decode JSON-text columns into real lists) ---------------

def _concept_to_schema(c: models.Concept) -> schemas.Concept:
    return schemas.Concept(
        slug=c.slug,
        title=c.title,
        summary=c.summary,
        definition=c.definition,
        why_anger=c.why_anger,
        practice=c.practice,
        reflection=c.reflection,
        tags=json.loads(c.tags or "[]"),
        source_notes=c.source_notes,
        order_index=c.order_index,
    )


def _resource_to_schema(r: models.Resource) -> schemas.Resource:
    return schemas.Resource(
        id=r.id,
        title=r.title,
        creator=r.creator,
        type=r.type,
        description=r.description,
        url=r.url,
        tags=json.loads(r.tags or "[]"),
        beginner_level=r.beginner_level,
        related_concepts=json.loads(r.related_concepts or "[]"),
    )


# --- Routes ---------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "second-arrow"}


@app.get("/api/concepts", response_model=List[schemas.Concept])
def list_concepts(db: Session = Depends(get_db)):
    concepts = db.query(models.Concept).order_by(models.Concept.order_index).all()
    return [_concept_to_schema(c) for c in concepts]


@app.get("/api/concepts/{slug}", response_model=schemas.Concept)
def get_concept(slug: str, db: Session = Depends(get_db)):
    concept = db.query(models.Concept).filter(models.Concept.slug == slug).first()
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    return _concept_to_schema(concept)


@app.get("/api/resources", response_model=List[schemas.Resource])
def list_resources(db: Session = Depends(get_db)):
    resources = db.query(models.Resource).order_by(models.Resource.title).all()
    return [_resource_to_schema(r) for r in resources]


@app.get("/api/journal", response_model=List[schemas.JournalEntry])
def list_journal(db: Session = Depends(get_db)):
    return (
        db.query(models.JournalEntry)
        .order_by(models.JournalEntry.created_at.desc())
        .all()
    )


@app.post("/api/journal", response_model=schemas.JournalEntry, status_code=201)
def create_journal_entry(entry: schemas.JournalEntryCreate, db: Session = Depends(get_db)):
    db_entry = models.JournalEntry(**entry.model_dump())
    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)
    return db_entry


@app.get("/api/journal/{entry_id}", response_model=schemas.JournalEntry)
def get_journal_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(models.JournalEntry).filter(models.JournalEntry.id == entry_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return entry


@app.delete("/api/journal/{entry_id}", status_code=204)
def delete_journal_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(models.JournalEntry).filter(models.JournalEntry.id == entry_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    db.delete(entry)
    db.commit()
    return None
