# Card Network RAG Chatbot

A Retrieval-Augmented Generation (RAG) CLI chatbot that answers questions about
card network rules, grounded in the **Mastercard Authorization System Guide**
(a 2,070-page reference PDF). Built as a small, self-contained demo of a
production-style RAG pattern: local/free retrieval + paid generation only
where it adds value.

## Why this architecture

The goal was to build something real and defensible, not a toy, while
keeping cost at (near) zero during development:

| Stage | Choice | Why |
|---|---|---|
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`), run locally | Free, no API key, no per-token cost, fast enough for a 4,700-chunk corpus |
| Vector store | `chromadb`, persisted to disk | Free, zero-ops, no server to run — a single `PersistentClient` directory |
| Chunking | Fixed-size (1,200 chars, 200 overlap), per-PDF-page | Simple, predictable, and preserves page numbers for citations — no need for a more complex semantic chunker at this scale |
| Generation | Claude API, `claude-haiku-4-5` | Only the final answer-generation step costs money; Haiku keeps per-query cost low while still producing grounded, well-cited answers |
| Prompt caching | `cache_control: ephemeral` on the system prompt | The system prompt (instructions, role) is static across every query — caching it cuts cost/latency on repeated calls. The retrieved context and question change every time, so they're deliberately left uncached |
| Citations | Chroma metadata (`source`, `page`) attached per chunk at ingest time | Lets the model cite `(source, page X)` instead of answering from parametric memory, and lets a user verify any claim against the source PDF |

This mirrors a real-world cost-conscious RAG design: free/local wherever
retrieval and storage are concerned, paid API only at the point where it's
actually earning its cost (natural-language generation).

## Architecture

```
PDF (Mastercard Authorization Guide)
        │
        ▼
   ingest.py
   ├─ pypdf: extract text per page
   ├─ chunk into 1,200-char windows (200 overlap)
   ├─ sentence-transformers: embed locally (free)
   └─ upsert into Chroma, tagged with {source, page}
        │
        ▼
   chroma_db/  (persistent local vector store, 4,706 chunks)
        │
        ▼
   chat.py
   ├─ embed the user's question (same local model)
   ├─ Chroma similarity search → top-5 chunks + metadata
   ├─ build prompt: cached system instructions + uncached context/question
   ├─ Claude API (claude-haiku-4-5) → grounded answer with citations
   └─ print to CLI
```

## Project structure

```
card-network-rag/
├── ingest.py           # One-time (or re-run-able) PDF → Chroma ingestion
├── chat.py             # Interactive CLI chatbot
├── requirements.txt    # Pinned dependencies
├── .env                # ANTHROPIC_API_KEY (gitignored, never commit)
├── .env.example         # Template for the above
├── .gitignore
├── chroma_db/           # Persistent vector store (gitignored)
├── data/                # (unused placeholder for future source docs)
└── venv/                # Python virtual environment (gitignored)
```

## Setup

```bash
cd card-network-rag
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Add your Anthropic API key:

```bash
cp .env.example .env
# then edit .env and replace the placeholder with your real key
# get a key at https://console.anthropic.com -> Settings -> API Keys
```

> **Note:** keys must be a Console API key (prefix `sk-ant-api03-...`).
> Never commit `.env` — it's already in `.gitignore`.

## Ingesting documents

```bash
source venv/bin/activate
python ingest.py "/path/to/your.pdf"          # single file
python ingest.py "/path/to/directory/"        # all PDFs in a directory
```

This is idempotent — chunk IDs are deterministic (`{filename}_p{page}_c{chunk}`),
so re-running `ingest.py` on the same file upserts rather than duplicates.

Currently ingested: `m_DMAS_en-us-2026-08-25.pdf` (Mastercard Authorization
System Guide), 2,070 pages → 4,706 chunks.

## Running the chatbot

```bash
source venv/bin/activate
python chat.py
```

```
Ready. Knowledge base: 4706 chunks from the Mastercard Authorization guide.
Ask a question (or type 'exit' to quit).

You: What is an authorization request?

Assistant: Based on the provided context, I can offer a limited answer:

An authorization request is a message used in card transactions.
Specifically, the context mentions the "Authorization Request/0100 message"
as an acquirer-generated message used in the Mastercard Dual Message
Authorization System (source, page 1795).

The context provides an example of an e-commerce authorization request
process where:
- A merchant requests authorization from the acquirer after receiving
  cardholder purchase information
- The acquirer then generates an Authorization Request/0100 message that
  includes cardholder payment data and appropriate data element values
  (source, page 1545)

However, the provided context does not contain a comprehensive definition...
```

Note the model also correctly declines to over-answer when the retrieved
context is thin — e.g. asked "What is a chargeback?" (a topic the
Authorization guide only mentions in passing, not the right source document
for), it says so explicitly rather than inventing an answer. That's the RAG
grounding working as intended, not a bug.

## Design notes / talking points

- **Grounded, not memorized**: the system prompt instructs Claude to answer
  only from retrieved context and to say when it doesn't know — this avoids
  hallucinated card-network rules, which matters a lot in a compliance-
  adjacent domain.
- **Citations by construction**: page numbers are captured once, at ingest
  time, as metadata — not inferred by the LLM — so citations are always
  accurate to the source document.
- **Cost control**: embeddings and vector search are fully local/free; the
  only metered cost is the final Haiku completion per query, with prompt
  caching reducing that further on repeated system-prompt reuse.
- **Scaling path**: swapping `chromadb` for a hosted vector DB (e.g.
  Pinecone/Weaviate) or moving the embedding step to an API-based model are
  both drop-in replacements — the retrieval/generation contract (`query()` →
  chunks → prompt) doesn't change.

## Future improvements

- Multi-document ingestion (dispute rules, Visa/Amex guides, etc.) to make
  this a true cross-network knowledge base.
- Re-ranking retrieved chunks before generation for higher precision.
- Conversation memory across turns (currently each question is independent).
- Swap the CLI for a lightweight web UI (Streamlit/FastAPI) once ready to
  demo beyond the terminal.
