"""
deploy/migrate/copy_qdrant.py — copies the knowledge-base collection from
Qdrant Cloud to the self-hosted Qdrant (S50).

Recreates the collection with the same vector settings and payload indexes,
then copies every point (vectors and payload) in batches. Read-only on the old
side. Refuses to run if the collection already exists on the new side, so a
second run cannot mix two copies — delete it first if you mean to redo it.

Run inside the app image, from deploy/:

    docker compose run --rm -T \
        -e OLD_QDRANT_URL=https://<cluster>.eu-central-1-0.aws.cloud.qdrant.io:6333 \
        -e OLD_QDRANT_API_KEY=... \
        -v ./migrate:/migrate jobs python /migrate/copy_qdrant.py

The new side and the collection name come from deploy/.env (QDRANT_URL,
QDRANT_API_KEY, QDRANT_COLLECTION). Ends by comparing point counts.
"""

import os
import sys

from qdrant_client import QdrantClient, models

name = os.environ["QDRANT_COLLECTION"]
old = QdrantClient(url=os.environ["OLD_QDRANT_URL"], api_key=os.environ["OLD_QDRANT_API_KEY"], timeout=120)
new = QdrantClient(url=os.environ["QDRANT_URL"], api_key=os.environ["QDRANT_API_KEY"], timeout=120)

if new.collection_exists(name):
    sys.exit(f"'{name}' already exists on the new Qdrant — delete it first to redo the copy.")

info = old.get_collection(name)
params = info.config.params
new.create_collection(
    name,
    vectors_config=params.vectors,
    sparse_vectors_config=params.sparse_vectors,
    on_disk_payload=params.on_disk_payload,
)
for field, schema in (info.payload_schema or {}).items():
    new.create_payload_index(name, field, field_schema=schema.data_type)
print(f"Created '{name}' with {len(info.payload_schema or {})} payload indexes.")

copied, offset = 0, None
while True:
    points, offset = old.scroll(name, limit=256, offset=offset,
                                with_payload=True, with_vectors=True)
    if points:
        new.upsert(name, [models.PointStruct(id=p.id, vector=p.vector, payload=p.payload)
                          for p in points], wait=True)
        copied += len(points)
        print(f"   {copied} points")
    if offset is None:
        break

want = old.count(name, exact=True).count
got = new.count(name, exact=True).count
print(f"Old: {want} points, new: {got}.")
sys.exit(0 if want == got else 1)
