# ARIS/integrations/relationships.py
# Relationship memory — store and recall people ARIS knows about
# Built on top of ChromaDB (already used for semantic memory)

import os
import json
import chromadb
from datetime import date, datetime
from chromadb.utils import embedding_functions

# ─── SETUP ─────────────────────────────────────────────────────────────────────

COLLECTION_NAME = "aris_relationships"

def _get_collection():
    """Get or create the relationships ChromaDB collection with absolute path."""
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.OllamaEmbeddingFunction(
        url="http://localhost:11434/api/embeddings",
        model_name="nomic-embed-text"
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"description": "People ARIS knows about"}
    )


# ─── ADD / UPDATE PERSON ───────────────────────────────────────────────────────

def save_person(
    name: str,
    relationship: str,
    birthday: str = None,
    notes: str = "",
    preferences: str = "",
    last_contact: str = None,
    contact_info: str = ""
) -> dict:
    """
    Save or update a person in relationship memory.
    Args:
        name:         Full name e.g. "Raj Sharma"
        relationship: e.g. "friend", "colleague", "family", "mentor"
        birthday:     ISO date string e.g. "1998-03-15" (optional)
        notes:        Free text history/context e.g. "Met at college, likes cricket"
        preferences:  Known preferences e.g. "Loves coffee, vegetarian"
        last_contact: ISO date string of last interaction
        contact_info: Phone/email/social
    """
    try:
        collection = _get_collection()
        person_id = f"person_{name.lower().replace(' ', '_')}"

        # Build a rich text document for semantic search
        doc_text = f"""
        Person: {name}
        Relationship: {relationship}
        Birthday: {birthday or 'unknown'}
        Notes: {notes}
        Preferences: {preferences}
        Contact: {contact_info}
        Last contact: {last_contact or 'unknown'}
        """.strip()

        metadata = {
            "name":         name,
            "relationship": relationship,
            "birthday":     birthday     or "",
            "notes":        notes,
            "preferences":  preferences,
            "last_contact": last_contact or "",
            "contact_info": contact_info,
            "updated_at":   date.today().isoformat(),
        }

        # Upsert — add if new, update if exists
        collection.upsert(
            ids=[person_id],
            documents=[doc_text],
            metadatas=[metadata]
        )
        return {"status": "saved", "person_id": person_id, "name": name}

    except Exception as e:
        print(f"[ARIS Relationships] Save failed (Ollama/Chroma down?): {e}")
        return {"status": "error", "error": "Relationship database or embedding service is currently offline."}


# ─── GET PERSON ────────────────────────────────────────────────────────────────

def get_person(name: str) -> dict | None:
    """Fetch a person by exact name."""
    try:
        collection = _get_collection()
        person_id  = f"person_{name.lower().replace(' ', '_')}"
        result = collection.get(ids=[person_id])
        if result and result["ids"]:
            return result["metadatas"][0]
    except Exception as e:
        print(f"[ARIS Relationships] Get failed: {e}")
    return None


# ─── GET ALL PEOPLE ────────────────────────────────────────────────────────────

def get_all_people() -> list[dict]:
    """Fetch all people stored in relationship memory."""
    try:
        collection = _get_collection()
        result     = collection.get()
        people = []
        for i, pid in enumerate(result["ids"]):
            meta = result["metadatas"][i]
            people.append(meta)
        return people
    except Exception as e:
        print(f"[ARIS Relationships] Get all failed: {e}")
        return []


# ─── SEARCH PEOPLE ─────────────────────────────────────────────────────────────

def search_people(query: str, n_results: int = 3) -> list[dict]:
    """
    Semantic search across relationship memory.
    e.g. "who likes cricket" or "my college friends"
    """
    try:
        collection = _get_collection()
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count())
        )
        if not results["ids"][0]:
            return []
        return results["metadatas"][0]
    except Exception as e:
        print(f"[ARIS Relationships] Search failed (Ollama/Chroma down?): {e}")
        return []


# ─── DELETE PERSON ─────────────────────────────────────────────────────────────

def delete_person(name: str) -> dict:
    """Remove a person from relationship memory."""
    try:
        collection = _get_collection()
        person_id  = f"person_{name.lower().replace(' ', '_')}"
        collection.delete(ids=[person_id])
        return {"status": "deleted", "name": name}
    except Exception as e:
        print(f"[ARIS Relationships] Delete failed: {e}")
        return {"status": "error", "error": str(e)}


# ─── UPDATE LAST CONTACT ───────────────────────────────────────────────────────

def update_last_contact(name: str, notes: str = "") -> dict:
    """
    Mark today as the last time you contacted this person.
    Optionally add notes about the interaction.
    """
    person = get_person(name)
    if not person:
        return {"status": "not_found", "name": name}

    today = date.today().isoformat()

    # Append interaction note to existing notes
    existing_notes = person.get("notes", "")
    if notes:
        updated_notes = f"{existing_notes}\n[{today}] {notes}".strip()
    else:
        updated_notes = existing_notes

    return save_person(
        name=person["name"],
        relationship=person["relationship"],
        birthday=person.get("birthday"),
        notes=updated_notes,
        preferences=person.get("preferences", ""),
        last_contact=today,
        contact_info=person.get("contact_info", "")
    )


# ─── NUDGE REMINDERS ───────────────────────────────────────────────────────────

def get_neglected_contacts(days_threshold: int = 14) -> list[dict]:
    """
    Find people you haven't contacted in over N days.
    Used by ARIS to nudge: "You haven't talked to Raj in 3 weeks."
    """
    people  = get_all_people()
    today   = date.today()
    neglected = []

    for person in people:
        last = person.get("last_contact", "")
        if not last:
            # Never contacted — always flag
            person["days_since_contact"] = None
            neglected.append(person)
            continue

        try:
            last_date = date.fromisoformat(last)
            delta     = (today - last_date).days
            if delta >= days_threshold:
                person["days_since_contact"] = delta
                neglected.append(person)
        except ValueError:
            continue

    return neglected


# ─── BIRTHDAY REMINDERS ────────────────────────────────────────────────────────

def get_upcoming_birthdays(days_ahead: int = 30) -> list[dict]:
    """
    Find people with birthdays in the next N days.
    """
    people   = get_all_people()
    today    = date.today()
    upcoming = []

    for person in people:
        bday_str = person.get("birthday", "")
        if not bday_str:
            continue
        try:
            bday = date.fromisoformat(bday_str)
            # Compare month/day only (ignore year)
            this_year_bday = bday.replace(year=today.year)
            if this_year_bday < today:
                this_year_bday = bday.replace(year=today.year + 1)
            delta = (this_year_bday - today).days
            if delta <= days_ahead:
                person["days_until_birthday"] = delta
                person["birthday_this_year"]  = this_year_bday.isoformat()
                upcoming.append(person)
        except ValueError:
            continue

    return sorted(upcoming, key=lambda x: x["days_until_birthday"])