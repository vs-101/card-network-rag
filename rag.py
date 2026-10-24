"""Shared RAG primitives: embeddings, vector store access, sensitivity
classification, retrieval, and Claude generation.

Used by both the CLI (chat.py) and the Streamlit web UI (app.py) so the
retrieval/generation contract stays in one place.
"""
from pathlib import Path

import anthropic
import chromadb
from chromadb.utils import embedding_functions

CHROMA_DIR = str(Path(__file__).parent / "chroma_db")
COLLECTION_NAME = "card_network_docs"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
GENERATION_MODEL = "claude-haiku-4-5"
TOP_K = 5

SYSTEM_PROMPT = """You are Mastercard Spec Advisor, a knowledgeable assistant for card network \
rules and procedures. Your knowledge base currently covers the Mastercard Authorization guide. \
You are an independent reference tool and are not an official Mastercard product.

Answer questions using ONLY the retrieved context provided in the user's message. \
If the context doesn't contain enough information to answer, say so clearly rather \
than guessing or using outside knowledge.

Always cite your sources inline using the format (source, page X) right after the \
claim they support. If multiple chunks support an answer, cite each relevant page."""

# Keywords that mark a chunk as security-sensitive (PIN/key-management/data-
# compromise content). Chunks matching any of these are tagged
# sensitivity="restricted" at ingestion time and are only retrievable by
# roles with elevated clearance. Everything else is sensitivity="general".
RESTRICTED_KEYWORDS = [
    "pin block", "pin verification", "pin pad", "clear-text pin", "clear text pin",
    "cvc2", "cvv2", "cvc 2", "cvv 2",
    "track 2", "track2", "track 1 data", "sensitive authentication data",
    "cryptogram", "cryptographic key", "key management", "key injection",
    "zone master key", "working key", "derivation key", "hsm",
    "hardware security module", "encryption key",
    "data compromise", "compromised", "forensic", "account data breach",
    "unencrypted", "cardholder data breach",
]


def classify_sensitivity(text: str) -> str:
    """Tag a chunk as 'restricted' (security-sensitive) or 'general'."""
    lowered = text.lower()
    for keyword in RESTRICTED_KEYWORDS:
        if keyword in lowered:
            return "restricted"
    return "general"


_embed_fn = None
_collection = None
_claude_client = None


def get_embedding_fn():
    global _embed_fn
    if _embed_fn is None:
        _embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    return _embed_fn


def get_collection():
    global _collection
    if _collection is None:
        client_db = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = client_db.get_or_create_collection(
            name=COLLECTION_NAME, embedding_function=get_embedding_fn()
        )
    return _collection


def get_claude_client():
    global _claude_client
    if _claude_client is None:
        _claude_client = anthropic.Anthropic()
    return _claude_client


def format_context(results) -> str:
    docs = results["documents"][0]
    metadatas = results["metadatas"][0]
    parts = []
    for doc, meta in zip(docs, metadatas):
        parts.append(f"[Source: {meta['source']}, Page {meta['page']}]\n{doc}")
    return "\n\n---\n\n".join(parts)


def retrieve(question: str, allow_restricted: bool, top_k: int = TOP_K):
    """Query the collection, optionally filtered to only 'general' content.

    Also returns how many restricted-only hits were suppressed, so callers
    can show a transparent "N results hidden by your access level" notice.
    """
    collection = get_collection()

    if allow_restricted:
        results = collection.query(query_texts=[question], n_results=top_k)
        return results, 0

    # Run a wider unfiltered query once, so we can report how many
    # otherwise-relevant restricted hits got excluded.
    unfiltered = collection.query(query_texts=[question], n_results=top_k)
    restricted_in_unfiltered = sum(
        1 for meta in unfiltered["metadatas"][0] if meta.get("sensitivity") == "restricted"
    )

    filtered = collection.query(
        query_texts=[question],
        n_results=top_k,
        where={"sensitivity": "general"},
    )
    return filtered, restricted_in_unfiltered


def generate_answer(question: str, context: str):
    """Call Claude with the cached system prompt + uncached per-query context.

    Returns the answer text. Raises anthropic exceptions on failure.
    """
    claude = get_claude_client()
    response = claude.messages.create(
        model=GENERATION_MODEL,
        max_tokens=1024,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion: {question}",
        }],
    )
    return response.content[0].text
