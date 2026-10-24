"""CLI chatbot for answering card network questions using RAG over local docs.

Retrieves relevant chunks from the local Chroma vector store, then asks
Claude to answer using only that retrieved context, with citations.

This CLI always runs with full (unrestricted) access. For the role-based
access control demo (general user vs. compliance officer), use the
Streamlit web UI: `streamlit run app.py`.

Usage: python chat.py
Requires: ANTHROPIC_API_KEY environment variable.
"""
import os
import sys

import anthropic
from dotenv import load_dotenv

import rag

load_dotenv(override=True)


def main():
    if not os.environ.get("ANTHROPIC_API_KEY") or os.environ["ANTHROPIC_API_KEY"] == "sk-ant-your-key-here":
        print("Error: ANTHROPIC_API_KEY is not set. Edit the .env file in this project and add your key.")
        sys.exit(1)

    print(f"Loading embedding model '{rag.EMBEDDING_MODEL}'...")
    collection = rag.get_collection()

    if collection.count() == 0:
        print(f"Collection '{rag.COLLECTION_NAME}' is empty. Run ingest.py first.")
        sys.exit(1)

    print(f"\nReady. Knowledge base: {collection.count()} chunks from the Mastercard Authorization guide.")
    print("Ask a question (or type 'exit' to quit).\n")

    while True:
        question = input("You: ").strip()
        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            break

        results, _ = rag.retrieve(question, allow_restricted=True)
        context = rag.format_context(results)

        try:
            answer = rag.generate_answer(question, context)
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
