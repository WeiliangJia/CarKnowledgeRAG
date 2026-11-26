"""Embed D4 chunks and resume an insert into a local Qdrant collection."""

import argparse
import hashlib
import json
import sys
from contextlib import closing
from dataclasses import asdict
from functools import partial
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from car_knowledge_rag.map_retrieval_evidence import index_chunks
from car_knowledge_rag.openai_models import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    OpenAIError,
    OpenAISettings,
    embed,
)

VECTOR_CONFIG = {"size": EMBEDDING_DIMENSIONS, "distance": "Cosine"}
PAYLOAD_INDEXES = {
    "model_info_id": "keyword",
    "model_year_code": "keyword",
    "kind": "keyword",
    "snapshot_id": "keyword",
    "version.group": "keyword",
    "version.label": "keyword",
    "locator.column_index": "integer",
}


class QdrantError(RuntimeError):
    pass


def request(port, method, path, payload=None):
    data = (
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if payload is not None
        else None
    )
    try:
        with closing(HTTPConnection("127.0.0.1", port, timeout=45)) as connection:
            connection.request(
                method, path, body=data, headers={"Content-Type": "application/json"}
            )
            response = connection.getresponse()
            status = response.status
            raw = response.read()
    except (OSError, HTTPException) as error:
        raise QdrantError(
            f"Cannot reach local Qdrant on port {port} ({type(error).__name__})"
        ) from None
    if not 200 <= status < 300:
        raise QdrantError(f"Qdrant returned HTTP {status} for {method} {path}")
    try:
        body = json.loads(raw)
        if body["status"] != "ok":
            raise ValueError("Request did not complete")
        return body["result"]
    except (ValueError, KeyError, TypeError):
        raise QdrantError(f"Invalid Qdrant response for {method} {path}") from None


def load_chunks(data):
    payload = json.loads(data)
    index_chunks(payload)
    chunks = payload["chunks"]
    if not chunks:
        raise ValueError("Expected nonempty D4 chunks")
    for chunk in chunks:
        if (
            str(UUID(chunk["id"])) != chunk["id"]
            or chunk["model_info_id"] != "10"
            or not isinstance(chunk["text"], str)
            or not chunk["text"].strip()
        ):
            raise ValueError("Expected canonical UUIDs and nonempty 9X evidence")
    digest = hashlib.sha256(data).hexdigest()
    collection = f"zeekr_9x_d4_openai_small_{EMBEDDING_DIMENSIONS}_{digest[:16]}"
    return (
        collection,
        chunks,
        {
            "chunks_sha256": digest,
            "corpus_sha256": payload["corpus_sha256"],
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dimensions": EMBEDDING_DIMENSIONS,
            "expected_points": len(chunks),
        },
    )


def ensure_collection(api, path, metadata):
    if not api("GET", f"{path}/exists")["exists"]:
        api("PUT", path, {"vectors": VECTOR_CONFIG, "metadata": metadata})
    info = api("GET", path)
    config = info["config"]
    vectors = config["params"]["vectors"]
    if (
        not all(vectors.get(key) == value for key, value in VECTOR_CONFIG.items())
        or config["metadata"] != metadata
    ):
        raise QdrantError(
            "Existing collection has incompatible vectors or source metadata"
        )
    for name, kind in PAYLOAD_INDEXES.items():
        existing = info["payload_schema"].get(name)
        if existing is None:
            api(
                "PUT",
                f"{path}/index?wait=true",
                {"field_name": name, "field_schema": kind},
            )
        elif existing["data_type"] != kind:
            raise QdrantError(f"Existing payload index has the wrong type: {name}")


def stored_ids(api, path, expected):
    seen = set()
    query = {"limit": 256, "with_payload": True, "with_vector": False}
    while True:
        result = api("POST", f"{path}/points/scroll", query)
        for point in result["points"]:
            point_id = point["id"]
            if (
                point_id in seen
                or point_id not in expected
                or point["payload"] != expected[point_id]
            ):
                raise QdrantError(
                    f"Unexpected point or payload in collection: {point_id}"
                )
            seen.add(point_id)
        offset = result["next_page_offset"]
        if offset is None:
            break
        if offset == query.get("offset"):
            raise QdrantError("Qdrant scroll did not advance")
        query["offset"] = offset
    if api("POST", f"{path}/points/count", {"exact": True})["count"] != len(seen):
        raise QdrantError("Point count changed during collection verification")
    return seen


def index(api, collection, chunks, metadata, embed_batch, *, batch_size=96, limit=None):
    path = f"/collections/{collection}"
    ensure_collection(api, path, metadata)
    expected = {chunk["id"]: chunk for chunk in chunks}
    before = stored_ids(api, path, expected)
    planned = chunks[:limit]
    pending = [chunk for chunk in planned if chunk["id"] not in before]
    token_count, batch_count = 0, 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        vectors, call = embed_batch([chunk["text"] for chunk in batch])
        if call.model != EMBEDDING_MODEL:
            raise ValueError("OpenAI returned a different embedding model")
        token_count += call.input_tokens
        batch_count += 1
        print(
            json.dumps({"batch": batch_count, "points": len(batch), **asdict(call)}),
            file=sys.stderr,
            flush=True,
        )
        points = [
            {"id": chunk["id"], "payload": chunk, "vector": vector}
            for chunk, vector in zip(batch, vectors, strict=True)
        ]
        result = api(
            "PUT",
            f"{path}/points?wait=true",
            {
                "points": points,
                "update_mode": "insert_only",
            },
        )
        if result["status"] != "completed":
            raise QdrantError("Qdrant did not confirm completion of the batch")
    after = stored_ids(api, path, expected) if pending else before
    if not before <= after or any(chunk["id"] not in after for chunk in planned):
        raise QdrantError("Some planned points are missing after the import")
    return {
        "collection": collection,
        "expected_points": len(chunks),
        "points_before": len(before),
        "points_after": len(after),
        "remaining": len(chunks) - len(after),
        "embedding_requests": batch_count,
        "embedded_points": len(pending),
        "input_tokens": token_count,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chunks", type=Path, help="D4 JSON chunk file")
    parser.add_argument("--port", type=int, default=6333, help="Local Qdrant HTTP port")
    parser.add_argument("--batch-size", type=int, default=96)
    parser.add_argument(
        "--limit", type=int, help="Index only the first N points for a pilot"
    )
    args = parser.parse_args()
    if (
        not 1 <= args.port <= 65535
        or not 1 <= args.batch_size <= 256
        or (args.limit is not None and args.limit < 1)
    ):
        parser.error("Invalid port, batch size, or limit")
    try:
        collection, chunks, metadata = load_chunks(args.chunks.read_bytes())
        settings = OpenAISettings()
        result = index(
            partial(request, args.port),
            collection,
            chunks,
            metadata,
            partial(embed, settings=settings),
            batch_size=args.batch_size,
            limit=args.limit,
        )
    except ValidationError:
        parser.exit(1, "Invalid OpenAI settings in .env.openai or the environment\n")
    except (
        QdrantError,
        OpenAIError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
    ) as error:
        parser.exit(1, f"Cannot index 9X chunks: {error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
