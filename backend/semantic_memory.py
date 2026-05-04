"""
ARIS Semantic Memory
Uses ChromaDB + nomic-embed-text (Ollama) to store and retrieve
meaningful facts about the user across all sessions.
"""

import chromadb
import httpx
import json
import os
from datetime import datetime

# ─── CHROMADB SETUP ────────────────────────────────────────────────────────────

# ChromaDB will store its data in ARIS/backend/chroma_db/
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")

# Persistent client — data survives restarts (just like SQLite)
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

# A "collection" is like a table — we store all ARIS memories here
memory_collection = chroma_client.get_or_create_collection(
    name="aris_memories",
    metadata={"hnsw:space": "cosine"}   # Cosine similarity = best for text meaning
)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL     = "nomic-embed-text"    # Ollama embedding model

# ─── EMBEDDING ─────────────────────────────────────────────────────────────────

async def get_embedding(text: str) -> list[float]:
    """
    Convert text into a vector (list of numbers) using nomic-embed-text.
    Similar texts will have similar vectors — that's how semantic search works.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text}
        )
        response.raise_for_status()
        return response.json()["embedding"]

# ─── MEMORY OPERATIONS ─────────────────────────────────────────────────────────

async def store_memory(fact: str, session_id: str, metadata: dict = None):
    """
    Store a single fact in ChromaDB with its vector embedding.
    Each fact gets a unique ID based on content + timestamp.
    """
    try:
        embedding = await get_embedding(fact)

        # Build metadata to attach to this memory
        mem_metadata = {
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "fact": fact
        }
        if metadata:
            mem_metadata.update(metadata)

        # Use a hash of the fact as ID to avoid exact duplicates
        import hashlib
        fact_id = hashlib.md5(fact.encode()).hexdigest()

        memory_collection.upsert(       # upsert = update if exists, insert if not
            ids=[fact_id],
            embeddings=[embedding],
            documents=[fact],
            metadatas=[mem_metadata]
        )
        print(f"[ARIS Memory] Stored: '{fact[:60]}...' " if len(fact) > 60 else f"[ARIS Memory] Stored: '{fact}'")

    except Exception as e:
        print(f"[ARIS Memory] Failed to store memory: {e}")


async def search_memories(query: str, n_results: int = 3) -> list[str]:
    """
    Search ChromaDB for facts relevant to the current query.
    Returns the top N most semantically similar memories.
    """
    try:
        if memory_collection.count() == 0:
            return []   # No memories stored yet

        query_embedding = await get_embedding(query)

        results = memory_collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, memory_collection.count()),  # Can't request more than we have
            include=["documents", "metadatas", "distances"]
        )

        # Filter out low-relevance results (distance > 0.5 means not very similar)
        memories = []
        for doc, distance in zip(results["documents"][0], results["distances"][0]):
            if distance < 0.5:   # Lower distance = more similar
                memories.append(doc)

        return memories

    except Exception as e:
        print(f"[ARIS Memory] Search failed: {e}")
        return []


async def extract_and_store_facts(user_message: str, aris_reply: str, session_id: str):
    """
    Analyze a conversation turn and extract memorable facts to store.
    We look for personal info, preferences, goals, and important statements.
    
    This uses simple keyword detection — Step 5 keeps it reliable and fast.
    In a later phase we can use an LLM to extract facts more intelligently.
    """
    facts_to_store = []

    # Combine both turns for analysis
    combined = f"User: {user_message}\nARIS: {aris_reply}"
    user_lower = user_message.lower()

    # ── Detect personal facts worth remembering ──

    # Name mentions
    name_triggers = ["my name is", "i'm called", "call me", "i am called"]
    for trigger in name_triggers:
        if trigger in user_lower:
            facts_to_store.append(f"User's name: {user_message}")
            break

    # Preferences
    pref_triggers = ["i love", "i like", "i enjoy", "i prefer", "i hate",
                     "i dislike", "favourite", "favorite", "i'm a fan of"]
    for trigger in pref_triggers:
        if trigger in user_lower:
            facts_to_store.append(f"User preference: {user_message}")
            break

    # Job / profession
    job_triggers = ["i work", "i'm a ", "i am a ", "my job", "my profession",
                    "i'm an ", "i am an ", "i work as", "my career"]
    for trigger in job_triggers:
        if trigger in user_lower:
            facts_to_store.append(f"User profession/role: {user_message}")
            break

    # Goals and plans
    goal_triggers = ["i want to", "i'm trying to", "my goal", "i plan to",
                     "i need to", "i'm working on", "i hope to"]
    for trigger in goal_triggers:
        if trigger in user_lower:
            facts_to_store.append(f"User goal/plan: {user_message}")
            break

    # Location
    location_triggers = ["i live in", "i'm from", "i am from", "i'm based in",
                         "my city", "my country", "i'm located"]
    for trigger in location_triggers:
        if trigger in user_lower:
            facts_to_store.append(f"User location: {user_message}")
            break

    # Remember commands — explicit memory requests
    remember_triggers = ["remember that", "remember this", "don't forget",
                         "keep in mind", "note that", "make a note"]
    for trigger in remember_triggers:
        if trigger in user_lower:
            facts_to_store.append(f"Important note from user: {user_message}")
            break

    # Store all detected facts
    for fact in facts_to_store:
        await store_memory(fact, session_id)

    if facts_to_store:
        print(f"[ARIS Memory] Extracted {len(facts_to_store)} fact(s) from conversation")


def get_memory_stats() -> dict:
    """Return stats about what's stored in semantic memory."""
    count = memory_collection.count()
    return {
        "total_memories": count,
        "storage_path": CHROMA_PATH
    }