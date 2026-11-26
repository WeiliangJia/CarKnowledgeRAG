"""Run a small OpenAI embedding and chunking experiment on the 9X snapshots."""

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from pydantic import ValidationError

from car_knowledge_rag.map_retrieval_evidence import (
    CONFIG_SNAPSHOT_ID,
    PRODUCT_TEXT_SHA256,
)
from car_knowledge_rag.openai_models import (
    OpenAIError,
    OpenAISettings,
    chunk_lines,
    embed,
)

# Use a small allowlist of excerpts from the two public snapshots.
DOCUMENTS = (
    ("suspension", "S2", 87, "闭式双腔空气悬架的最大调节行程是多少？"),
    ("massage", "S2", 182, "座椅按摩适用哪几排、哪些座位？"),
    ("six_seat_range", "S1", (20, 2), "六座 Ultra 的 CLTC 纯电续航是多少？"),
    ("five_seat_range", "S1", (20, 5), "五座 Ultra 的 CLTC 纯电续航是多少？"),
)
PRODUCT_SAMPLES = {
    "chassis": (
        (85, 97),
        {
            "suspension_travel": (85, 88),
            "damper_control": (89, 91),
            "stabilizer_specs": (92, 97),
        },
    ),
    "seat_and_display": (
        (176, 186),
        {"seat_functions_and_scope": (177, 182), "sliding_display_specs": (184, 186)},
    ),
}


def load_samples(corpus_data, chunk_data):
    corpus = json.loads(corpus_data)
    chunks = json.loads(chunk_data)
    if (
        corpus["schema_version"] != 1
        or chunks["schema_version"] != 1
        or chunks["corpus_sha256"] != hashlib.sha256(corpus_data).hexdigest()
        or corpus["configuration"]["snapshot_id"] != CONFIG_SNAPSHOT_ID
        or corpus["sources"]["S2"]["files"]["text.txt"]["sha256"] != PRODUCT_TEXT_SHA256
    ):
        raise ValueError(
            "Expected matching D1–D3 and D4 data for the pinned 9X snapshots"
        )

    documents = []
    for name, source, location, question in DOCUMENTS:
        if source == "S1":
            row, column = location
            matches = [
                chunk
                for chunk in chunks["chunks"]
                if chunk["source"] == source
                and chunk["kind"] == "configuration"
                and chunk["locator"]["row_index"] == row
                and chunk["locator"]["column_index"] == column
                and chunk["snapshot_id"] == CONFIG_SNAPSHOT_ID
            ]
        else:
            matches = [
                chunk
                for chunk in chunks["chunks"]
                if chunk["source"] == source
                and chunk["kind"] == "product"
                and location in chunk["locator"]["lines"]
                and chunk["source_text_sha256"] == PRODUCT_TEXT_SHA256
            ]
        if len(matches) != 1:
            raise ValueError(f"Expected one D4 chunk for {name}")
        chunk = matches[0]
        documents.append(
            {
                "name": name,
                "question": question,
                "text": chunk["text"],
                "chunk_id": chunk["id"],
                "source": source,
                "locator": chunk["locator"],
                "source_url": corpus["sources"][source]["url"],
            }
        )

    product_lines = {
        line["line"]: line["text"]
        for block in corpus["product"]["blocks"]
        for line in block["lines"]
    }
    excerpts = {
        name: [product_lines[line] for line in range(start, end + 1)]
        for name, ((start, end), _) in PRODUCT_SAMPLES.items()
    }
    return documents, excerpts


def compare_vectors(documents, vectors):
    count = len(documents)
    directions = [
        [value / norm for value in vector]
        for vector in vectors
        for norm in (math.hypot(*vector),)
    ]
    results = []
    for expected, query in zip(documents, directions[count:], strict=True):
        ranked = sorted(
            (
                (
                    document["name"],
                    math.fsum(a * b for a, b in zip(query, direction, strict=True)),
                )
                for document, direction in zip(
                    documents, directions[:count], strict=True
                )
            ),
            key=lambda item: (-item[1], item[0]),
        )
        results.append(
            {
                "question": expected["question"],
                "expected": expected["name"],
                "expected_rank": next(
                    rank
                    for rank, (name, _) in enumerate(ranked, 1)
                    if name == expected["name"]
                ),
                "ranked": [
                    {"document": name, "cosine": round(score, 6)}
                    for name, score in ranked
                ],
            }
        )
    return results


def check_chunk_boundaries(name, chunks):
    (start, end), required = PRODUCT_SAMPLES[name]
    ranges = [
        [start + chunk.start_line - 1, start + chunk.end_line - 1] for chunk in chunks
    ]
    return {
        "sample": name,
        "source": "S2",
        "input_lines": [start, end],
        "chunk_lines": ranges,
        "checks": {
            requirement: any(first <= left <= right <= last for first, last in ranges)
            for requirement, (left, right) in required.items()
        },
    }


def run_samples(documents, excerpts, settings):
    runs = []
    started = perf_counter()
    try:
        vectors, call = embed(
            [item["text"] for item in documents]
            + [item["question"] for item in documents],
            settings=settings,
        )
        runs.append(
            {
                "stage": "embedding",
                "status": "ok",
                **asdict(call),
                "vectors": len(vectors),
                "dimensions": len(vectors[0]),
                "results": compare_vectors(documents, vectors),
            }
        )
    except (OpenAIError, ValueError) as error:
        runs.append(
            {
                "stage": "embedding",
                "status": "error",
                "error": str(error),
                "elapsed_ms": round((perf_counter() - started) * 1000, 1),
            }
        )

    for name, lines in excerpts.items():
        started = perf_counter()
        try:
            chunks, call = chunk_lines(lines, settings=settings)
            runs.append(
                {
                    "stage": "chunking",
                    "status": "ok",
                    **asdict(call),
                    **check_chunk_boundaries(name, chunks),
                }
            )
        except (OpenAIError, ValueError) as error:
            runs.append(
                {
                    "stage": "chunking",
                    "sample": name,
                    "status": "error",
                    "error": str(error),
                    "elapsed_ms": round((perf_counter() - started) * 1000, 1),
                }
            )
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus", type=Path, default=Path("data/corpus/9x-d1-d3.json")
    )
    parser.add_argument(
        "--chunks", type=Path, default=Path("data/corpus/9x-d4-chunks.json")
    )
    parser.add_argument("--output", required=True, type=Path, help="New JSON report")
    args = parser.parse_args()
    try:
        corpus_data, chunk_data = args.corpus.read_bytes(), args.chunks.read_bytes()
        documents, excerpts = load_samples(corpus_data, chunk_data)
        settings = OpenAISettings()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            runs = run_samples(documents, excerpts, settings)
            report = {
                "schema_version": 1,
                "recorded_at": datetime.now(UTC).isoformat(),
                "corpus_sha256": hashlib.sha256(corpus_data).hexdigest(),
                "chunks_sha256": hashlib.sha256(chunk_data).hexdigest(),
                "documents": [
                    {key: value for key, value in item.items() if key != "text"}
                    for item in documents
                ],
                "runs": runs,
            }
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except ValidationError:
        parser.error("Invalid OpenAI settings in .env.openai or the environment")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.error(str(error))
    for run in runs:
        summary = {key: value for key, value in run.items() if key != "results"}
        print(json.dumps(summary, ensure_ascii=True))
    print(f"report={args.output}")
    return int(any(run["status"] == "error" for run in runs))


if __name__ == "__main__":
    raise SystemExit(main())
