"""CLI chatbot for answering card network questions using RAG over local docs.

Retrieves relevant chunks from the local Chroma vector store, then asks
Claude to answer using only that retrieved context, with citations.

Usage: python chat.py
Requires: ANTHROPIC_API_KEY environment variable.
"""
import os
import sys
from pathlib import Path

import anthropic
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

load_dotenv(override=True)

CHROMA_DIR = str(Path(__file__).parent / "chroma_db")
COLLECTION_NAME = "card_network_docs"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
GENERATION_MODEL = "claude-haiku-4-5"
TOP_K = 5

SYSTEM_PROMPT = """You are a knowledgeable assistant for card network rules and procedures. \
Your knowledge base currently covers the Mastercard Authorization guide.

Answer questions using ONLY the retrieved context provided in the user's message. \
If the context doesn't contain enough information to answer, say so clearly rather \
than guessing or using outside knowledge.

Always cite your sources inline using the format (source, page X) right after the \
claim they support. If multiple chunks support an answer, cite each relevant page."""


def format_context(results) -> str:
    docs = results["documents"][0]
    metadatas = results["metadatas"][0]
    parts = []
    for doc, meta in zip(docs, metadatas):
        parts.append(f"[Source: {meta['source']}, Page {meta['page']}]\n{doc}")
    return "\n\n---\n\n".join(parts)


def main():
    if not os.environ.get("ANTHROPIC_API_KEY") or os.environ["ANTHROPIC_API_KEY"] == "sk-ant-your-key-here":
        print("Error: ANTHROPIC_API_KEY is not set. Edit the .env file in this project and add your key.")
        sys.exit(1)

    print(f"Loading embedding model '{EMBEDDING_MODEL}'...")
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)

    client_db = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client_db.get_or_create_collection(name=COLLECTION_NAME, embedding_function=embed_fn)

    if collection.count() == 0:
        print(f"Collection '{COLLECTION_NAME}' is empty. Run ingest.py first.")
        sys.exit(1)

    claude = anthropic.Anthropic()

    print(f"\nReady. Knowledge base: {collection.count()} chunks from the Mastercard Authorization guide.")
    print("Ask a question (or type 'exit' to quit).\n")

    while True:
        question = input("You: ").strip()
        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            break

        results = collection.query(query_texts=[question], n_results=TOP_K)
        context = format_context(results)

        try:
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
            answer = response.content[0].text
            print(f"\nAssistant: {answer}\n")
        except anthropic.AuthenticationError:
            print("\nError: Invalid ANTHROPIC_API_KEY. Check your credentials.\n")
        except anthropic.RateLimitError:
            print("\nError: Rate limit hit. Wait a moment and try again.\n")
        except anthropic.APIStatusError as e:
            print(f"\nError: API returned an error ({e.status_code}): {e.message}\n")
        except anthropic.APIConnectionError:
            print("\nError: Could not connect to the Anthropic API. Check your network.\n")


if __name__ == "__main__":
    main()
