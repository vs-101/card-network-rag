"""One-off migration: tag already-ingested chunks with a 'sensitivity'
metadata field (general | restricted), based on keyword classification.

Needed because the collection was originally ingested before the RBAC
feature existed. New ingestions via ingest.py tag this automatically -
this script backfills existing data without re-embedding anything.

Usage: python tag_sensitivity.py
"""
from tqdm import tqdm

import rag


def main():
    collection = rag.get_collection()
    total = collection.count()
    print(f"Collection has {total} chunks. Fetching for classification...")

    all_data = collection.get(include=["documents", "metadatas"])
    ids = all_data["ids"]
    documents = all_data["documents"]
    metadatas = all_data["metadatas"]

    restricted_count = 0
    batch_size = 200
    for i in tqdm(range(0, len(ids), batch_size)):
        batch_ids = ids[i:i + batch_size]
        batch_docs = documents[i:i + batch_size]
        batch_metas = metadatas[i:i + batch_size]

        new_metas = []
        for doc, meta in zip(batch_docs, batch_metas):
            sensitivity = rag.classify_sensitivity(doc)
            if sensitivity == "restricted":
                restricted_count += 1
            new_meta = dict(meta)
            new_meta["sensitivity"] = sensitivity
            new_metas.append(new_meta)

        collection.update(ids=batch_ids, metadatas=new_metas)

    print(f"\nDone. {restricted_count}/{total} chunks tagged 'restricted', "
          f"{total - restricted_count} tagged 'general'.")


if __name__ == "__main__":
    main()
