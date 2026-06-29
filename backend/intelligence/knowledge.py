import os
import re
import html
import httpx
import urllib.parse
import hashlib
from datetime import datetime, timezone
import chromadb
import pypdf

# ─── Embedding with Ollama → Gemini fallback ─────────────────────────────────

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL     = "nomic-embed-text"

async def _ollama_embedding(text: str) -> list[float] | None:
    """Try Ollama nomic-embed-text for local embeddings."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/embed",
                json={"model": EMBED_MODEL, "input": text}
            )
            response.raise_for_status()
            return response.json()["embeddings"][0]
        except Exception:
            try:
                response = await client.post(
                    f"{OLLAMA_BASE_URL}/api/embeddings",
                    json={"model": EMBED_MODEL, "prompt": text}
                )
                response.raise_for_status()
                return response.json()["embedding"]
            except Exception:
                return None

async def _gemini_embedding(text: str) -> list[float] | None:
    """Fallback: use Gemini text-embedding-004 via Google GenAI SDK."""
    try:
        from google import genai
        gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        result = gemini_client.models.embed_content(
            model="text-embedding-004",
            contents=text
        )
        return result.embeddings[0].values
    except Exception as e:
        print(f"[ARIS KB] Gemini embedding fallback failed: {e}")
        return None

async def get_embedding(text: str) -> list[float] | None:
    """Get embedding vector: try Ollama first, fall back to Gemini."""
    vec = await _ollama_embedding(text)
    if vec:
        return vec
    vec = await _gemini_embedding(text)
    if vec:
        return vec
    print("[ARIS KB] All embedding providers unavailable")
    return None

# Setup ChromaDB
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

knowledge_collection = chroma_client.get_or_create_collection(
    name="aris_knowledge",
    metadata={"hnsw:space": "cosine"}
)

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """Split text into overlapping chunks for semantic retrieval."""
    chunks = []
    if not text:
        return chunks
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        # If we reached the end of the text, stop
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks

async def extract_text_from_url(url: str) -> str:
    """Fetch URL and extract clean, readable text/markdown from the HTML body."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        html_content = resp.text
        
    # Remove script and style tags
    html_content = re.sub(r'<(script|style|header|footer|nav)[^>]*>.*?</\1>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', ' ', html_content)
    # Decode HTML entities
    text = html.unescape(text)
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a local PDF file using pypdf."""
    reader = pypdf.PdfReader(file_path)
    text_parts = []
    for page in reader.pages:
        txt = page.extract_text()
        if txt:
            text_parts.append(txt)
    return "\n\n".join(text_parts)

async def add_document(source_type: str, content: str, title: str = "") -> dict:
    """
    Extract, chunk, and index content into the ChromaDB knowledge base.
    source_type: 'file' | 'url' | 'text'
    content: local file path, URL string, or raw text.
    """
    try:
        source_name = ""
        text_content = ""
        
        if source_type == "file":
            if not os.path.exists(content):
                return {"status": "error", "message": f"File does not exist: {content}"}
            source_name = os.path.basename(content)
            if not title:
                title = source_name
                
            ext = os.path.splitext(content)[1].lower()
            if ext == ".pdf":
                text_content = extract_text_from_pdf(content)
            else:
                with open(content, "r", encoding="utf-8", errors="ignore") as f:
                    text_content = f.read()
                    
        elif source_type == "url":
            source_name = content
            if not title:
                parsed = urllib.parse.urlparse(content)
                title = parsed.netloc or content
            text_content = await extract_text_from_url(content)
            
        elif source_type == "text":
            source_name = f"raw_text_{hashlib.md5(content[:100].encode()).hexdigest()[:8]}"
            if not title:
                title = f"Note: {content[:30]}..."
            text_content = content
            
        else:
            return {"status": "error", "message": f"Invalid source_type: {source_type}"}
            
        if not text_content.strip():
            return {"status": "error", "message": "No text content could be extracted."}
            
        chunks = chunk_text(text_content)
        stored_chunks = 0
        
        # We delete existing chunks for this source to allow clean updates/re-indexing
        delete_document(source_name)
        
        for idx, chunk in enumerate(chunks):
            embedding = await get_embedding(chunk)
            if not embedding:
                continue
                
            chunk_id = f"{hashlib.md5(source_name.encode()).hexdigest()}_{idx}"
            metadata = {
                "source": source_name,
                "title": title,
                "chunk_index": idx,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": source_type
            }
            
            knowledge_collection.upsert(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk],
                metadatas=[metadata]
            )
            stored_chunks += 1
            
        return {
            "status": "success",
            "source": source_name,
            "title": title,
            "chunks_indexed": stored_chunks
        }
    except Exception as e:
        print(f"[ARIS KB] Error adding document: {e}")
        return {"status": "error", "message": str(e)}

async def search_knowledge(query: str, limit: int = 4) -> list:
    """Perform a semantic vector search across the knowledge base."""
    try:
        embedding = await get_embedding(query)
        if not embedding:
            return []
            
        res = knowledge_collection.query(
            query_embeddings=[embedding],
            n_results=limit
        )
        
        matches = []
        if res and res.get("documents") and len(res["documents"][0]) > 0:
            docs = res["documents"][0]
            metas = res["metadatas"][0]
            distances = res["distances"][0] if res.get("distances") else [0.0] * len(docs)
            
            for idx in range(len(docs)):
                # cosine distance (smaller is more similar, 0.0 is perfect, 1.0/2.0 is dissimilar)
                score = round(1.0 - distances[idx], 3)
                matches.append({
                    "text": docs[idx],
                    "source": metas[idx].get("source", ""),
                    "title": metas[idx].get("title", ""),
                    "chunk_index": metas[idx].get("chunk_index", 0),
                    "score": score
                })
        return matches
    except Exception as e:
        print(f"[ARIS KB] Error searching KB: {e}")
        return []

def list_documents() -> list:
    """List all unique document sources stored in the knowledge base."""
    try:
        # Retrieve all items in collection
        res = knowledge_collection.get()
        if not res or not res.get("metadatas"):
            return []
            
        unique_sources = {}
        for meta in res["metadatas"]:
            src = meta.get("source")
            if src and src not in unique_sources:
                unique_sources[src] = {
                    "source": src,
                    "title": meta.get("title", src),
                    "type": meta.get("type", "unknown"),
                    "chunks": 0,
                    "added_at": meta.get("timestamp", "")
                }
            if src in unique_sources:
                unique_sources[src]["chunks"] += 1
                
        return list(unique_sources.values())
    except Exception as e:
        print(f"[ARIS KB] Error listing documents: {e}")
        return []

def delete_document(source: str) -> dict:
    """Delete a document source (and all its chunks) from the knowledge base."""
    try:
        # Query matching IDs for source
        res = knowledge_collection.get(
            where={"source": source}
        )
        if res and res.get("ids"):
            knowledge_collection.delete(ids=res["ids"])
            return {"status": "success", "deleted_count": len(res["ids"])}
        return {"status": "success", "deleted_count": 0}
    except Exception as e:
        print(f"[ARIS KB] Error deleting document: {e}")
        return {"status": "error", "message": str(e)}
