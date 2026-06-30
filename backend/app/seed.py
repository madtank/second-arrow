"""Populate the database with seed concepts and resources on first run.

Idempotent: only inserts rows that don't already exist (matched by slug for
concepts, by title+type for resources).
"""
import json

from sqlalchemy.orm import Session

from . import models
from .seed_data import CONCEPTS, RESOURCES


def seed_database(db: Session) -> None:
    # Concepts — order_index follows list order; "the-second-arrow" is first.
    existing_slugs = {c.slug for c in db.query(models.Concept.slug).all()}
    for index, data in enumerate(CONCEPTS):
        if data["slug"] in existing_slugs:
            continue
        db.add(
            models.Concept(
                slug=data["slug"],
                title=data["title"],
                summary=data["summary"],
                definition=data["definition"],
                why_anger=data["why_anger"],
                practice=data["practice"],
                reflection=data["reflection"],
                tags=json.dumps(data.get("tags", [])),
                source_notes=data.get("source_notes"),
                order_index=index,
            )
        )

    # Resources — match on (title, type) to avoid duplicates.
    existing_resources = {(r.title, r.type) for r in db.query(models.Resource.title, models.Resource.type).all()}
    for data in RESOURCES:
        key = (data["title"], data["type"])
        if key in existing_resources:
            continue
        db.add(
            models.Resource(
                title=data["title"],
                creator=data.get("creator"),
                type=data["type"],
                description=data.get("description"),
                url=data.get("url"),
                tags=json.dumps(data.get("tags", [])),
                beginner_level=data.get("beginner_level", True),
                related_concepts=json.dumps(data.get("related_concepts", [])),
            )
        )

    db.commit()
