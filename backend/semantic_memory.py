"""
ARIS Semantic Memory
Uses ChromaDB + nomic-embed-text (Ollama) to store and retrieve
meaningful facts about the user across all sessions.
"""

import chromadb
import httpx
import json
import os
import hashlib
from datetime import datetime, timezone

# ─── CHROMADB SETUP ────────────────────────────────────────────────────────────

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

memory_collection = chroma_client.get_or_create_collection(
    name="aris_memories",
    metadata={"hnsw:space": "cosine"}
)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL     = "nomic-embed-text"

# ─── EMBEDDING ─────────────────────────────────────────────────────────────────

async def get_embedding(text: str) -> list[float] | None:
    """
    Convert text into a vector using nomic-embed-text via Ollama.
    Returns None if Ollama is unavailable — callers handle gracefully.

    Tries the new /api/embed endpoint first (Ollama 0.2+),
    falls back to /api/embeddings for older versions.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:

        # ✅ Try new endpoint first (Ollama 0.2+)
        try:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/embed",
                json={"model": EMBED_MODEL, "input": text}
            )
            response.raise_for_status()
            data = response.json()
            # New API returns {"embeddings": [[...]]}
            return data["embeddings"][0]
        except Exception:
            pass

        # ✅ Fallback: old endpoint (Ollama 0.1.x)
        try:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": text}
            )
            response.raise_for_status()
            return response.json()["embedding"]
        except Exception as e:
            print(f"[ARIS Memory] Embedding unavailable (Ollama down?): {e}")
            return None

# ─── MEMORY OPERATIONS ─────────────────────────────────────────────────────────

async def store_memory(fact: str, session_id: str, metadata: dict = None):
    """
    Store a single fact in ChromaDB with its vector embedding.
    Skips silently if Ollama is unavailable.
    """
    try:
        embedding = await get_embedding(fact)
        if embedding is None:
            return  # Ollama down — skip silently, don't crash

        mem_metadata = {
            "session_id": session_id,
            "timestamp" : datetime.now(timezone.utc).isoformat(),
            "fact"      : fact
        }
        if metadata:
            mem_metadata.update(metadata)

        fact_id = hashlib.md5(fact.encode()).hexdigest()

        memory_collection.upsert(
            ids=[fact_id],
            embeddings=[embedding],
            documents=[fact],
            metadatas=[mem_metadata]
        )
        print(f"[ARIS Memory] Stored: '{fact[:60]}'" if len(fact) > 60 else f"[ARIS Memory] Stored: '{fact}'")

    except Exception as e:
        print(f"[ARIS Memory] Failed to store: {e}")


async def search_memories(query: str, n_results: int = 3) -> list[str]:
    """
    Search ChromaDB for facts relevant to the current query.
    Returns empty list if Ollama is unavailable — chat still works fine.
    """
    try:
        if memory_collection.count() == 0:
            return []

        query_embedding = await get_embedding(query)
        if query_embedding is None:
            return []  # Ollama down — skip memory, don't crash chat

        results = memory_collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, memory_collection.count()),
            include=["documents", "metadatas", "distances"]
        )

        memories = []
        for doc, distance in zip(results["documents"][0], results["distances"][0]):
            if distance < 0.5:
                memories.append(doc)

        return memories

    except Exception as e:
        print(f"[ARIS Memory] Search failed: {e}")
        return []


async def extract_and_store_facts(user_message: str, aris_reply: str, session_id: str):
    """
    Extract memorable facts from a conversation turn and store them.
    Skips silently if Ollama is unavailable.
    """
    facts_to_store = []
    user_lower = user_message.lower()

    # Name
    for trigger in ["my name is", "i'm called", "call me", "i am called"]:
        if trigger in user_lower:
            facts_to_store.append(f"User's name: {user_message}")
            break

    # Preferences
    for trigger in ["i love", "i like", "i enjoy", "i prefer", "i hate",
                    "i dislike", "favourite", "favorite", "i'm a fan of"]:
        if trigger in user_lower:
            facts_to_store.append(f"User preference: {user_message}")
            break

    # Job
    for trigger in ["i work", "i'm a ", "i am a ", "my job", "my profession",
                    "i'm an ", "i am an ", "i work as", "my career"]:
        if trigger in user_lower:
            facts_to_store.append(f"User profession/role: {user_message}")
            break

    # Goals
    for trigger in ["i want to", "i'm trying to", "my goal", "i plan to",
                    "i need to", "i'm working on", "i hope to"]:
        if trigger in user_lower:
            facts_to_store.append(f"User goal/plan: {user_message}")
            break

    # Location
    for trigger in ["i live in", "i'm from", "i am from", "i'm based in",
                    "my city", "my country", "i'm located"]:
        if trigger in user_lower:
            facts_to_store.append(f"User location: {user_message}")
            break

    # Explicit remember commands
    for trigger in ["remember that", "remember this", "don't forget",
                    "keep in mind", "note that", "make a note"]:
        if trigger in user_lower:
            facts_to_store.append(f"Important note from user: {user_message}")
            break

    for fact in facts_to_store:
        await store_memory(fact, session_id)

    if facts_to_store:
        print(f"[ARIS Memory] Extracted {len(facts_to_store)} fact(s)")


def get_memory_stats() -> dict:
    """Return stats about semantic memory."""
    return {
        "total_memories": memory_collection.count(),
        "storage_path"  : CHROMA_PATH
    }