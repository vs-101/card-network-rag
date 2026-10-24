"""Ingest PDF documents into a local Chroma vector store for RAG retrieval.

Usage: python ingest.py "/path/to/docs/dir/or/file.pdf"
"""
import sys
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader
from tqdm import tqdm

CHROMA_DIR = str(Path(__file__).parent / "chroma_db")
COLLECTION_NAME = "card_network_docs"
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def load_pdf_pages(pdf_path: Path):
    reader = PdfReader(str(pdf_path))
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            yield page_num, text


def chunk_text(text: str, chunk_size: int, overlap: int):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def build_chunks(pdf_path: Path):
    chunks, metadatas, ids = [], [], []
    for page_num, page_text in load_pdf_pages(pdf_path):
        for i, chunk in enumerate(chunk_text(page_text, CHUNK_SIZE, CHUNK_OVERLAP)):
            chunks.append(chunk)
            metadatas.append({
                "source": pdf_path.name,
                "page": page_num,
            })
            ids.append(f"{pdf_path.stem}_p{page_num}_c{i}")
    return chunks, metadatas, ids


def main():
    if len(sys.argv) < 2:
        print("Usage: python ingest.py <path-to-pdf-or-dir>")
        sys.exit(1)

    target = Path(sys.argv[1]).expanduser()
    pdf_paths = [target] if target.is_file() else sorted(target.glob("*.pdf"))
    if not pdf_paths:
        print(f"No PDFs found at {target}")
        sys.exit(1)

    print(f"Loading embedding model '{EMBEDDING_MODEL}' (runs locally, free, no API key needed)...")
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=embed_fn)

    for pdf_path in pdf_paths:
        print(f"\nProcessing {pdf_path.name} ...")
        chunks, metadatas, ids = build_chunks(pdf_path)
        print(f"  {len(chunks)} chunks extracted. Embedding + storing (batched)...")

        batch_size = 100
        for i in tqdm(range(0, len(chunks), batch_size)):
            collection.upsert(
                documents=chunks[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size],
                ids=ids[i:i + batch_size],
            )

    print(f"\nDone. Collection '{COLLECTION_NAME}' now has {collection.count()} chunks stored in {CHROMA_DIR}")


if __name__ == "__main__":
    main()
