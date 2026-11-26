"""Measure Top-K evidence coverage and Ultra version mixing in the 9X index."""

import argparse
import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from time import perf_counter

from pydantic import ValidationError

from car_knowledge_rag.evaluate import read_dataset
from car_knowledge_rag.index_9x import (
    VECTOR_CONFIG,
    QdrantError,
    load_chunks,
    request,
    stored_ids,
)
from car_knowledge_rag.map_retrieval_evidence import map_evidence
from car_knowledge_rag.openai_models import (
    EMBEDDING_MODEL,
    OpenAIError,
    OpenAISettings,
    embed,
)

TOP_K = (5, 10)
ULTRA = "Ultra版"
ULTRA_GROUPS = {"五": "9X五座版", "六": "9X六座版"}
OPPOSITE_GROUP = {
    ULTRA_GROUPS["五"]: ULTRA_GROUPS["六"],
    ULTRA_GROUPS["六"]: ULTRA_GROUPS["五"],
}
SHARED_KINDS = ["product", "product_notice", "configuration_notice"]


def query_text(case):
    context = case.get("context")
    return (
        f"上下文：{context}\n问题：{case['question']}" if context else case["question"]
    )


def ultra_group(case, text):
    """Select only explicit, unambiguous Ultra references for the pairwise test."""
    if case["category"] in {"comparison", "filter"}:
        return None
    text = text.replace("5座", "五座").replace("6座", "六座")
    explicit = set(
        re.findall(r"([五六])座(?:版)?\s*Ultra(?![a-z0-9_+])", text, re.IGNORECASE)
    )
    seats = set(re.findall(r"([五六])座", text))
    if (
        len(explicit) == 1
        and seats == explicit
        and not re.search(
            r"Hyper|Max|[五六]座(?:版)?\s*曜黑|曜黑版|Ultra\+", text, re.IGNORECASE
        )
    ):
        return ULTRA_GROUPS[next(iter(explicit))]
    return None


def version_filter(group):
    return {
        "should": [
            {"key": "kind", "match": {"any": SHARED_KINDS}},
            {
                "must": [
                    {"key": "kind", "match": {"value": "configuration"}},
                    {"key": "version.label", "match": {"value": ULTRA}},
                    {"key": "version.group", "match": {"value": group}},
                ]
            },
        ]
    }


def verify_index(api, path, metadata, chunks):
    config = api("GET", path)["config"]
    vectors = config["params"]["vectors"]
    if config["metadata"] != metadata or not all(
        vectors.get(key) == value for key, value in VECTOR_CONFIG.items()
    ):
        raise QdrantError("Qdrant metadata or vector configuration differs from D8")
    expected = {chunk["id"]: chunk for chunk in chunks}
    if stored_ids(api, path, expected) != expected.keys():
        raise QdrantError("D8 collection is incomplete")


def load_inputs(chunks_file, labels_file):
    cases, dataset_digest = read_dataset("dev")
    collection, chunks, metadata = load_chunks(chunks_file.read_bytes())
    labels = json.loads(labels_file.read_bytes())
    if (
        labels["schema_version"] != 1
        or labels["split"] != "dev"
        or labels["dataset_sha256"] != dataset_digest
        or labels["chunks_sha256"] != metadata["chunks_sha256"]
        or labels["cases"]
        != map_evidence(cases, {"schema_version": 1, "chunks": chunks})
    ):
        raise ValueError("D5 labels do not match the development dataset and D4 chunks")
    return cases, labels, collection, chunks, metadata


def retrieve(api, path, vector, *, group=None):
    body = {
        "query": vector,
        "limit": max(TOP_K),
        "params": {"exact": True},
        "with_payload": ["source", "kind", "locator", "version", "source_url"],
        "with_vector": False,
    }
    if group is not None:
        body["filter"] = version_filter(group)
    started = perf_counter()
    points = api("POST", f"{path}/points/query", body)["points"]
    return points, round((perf_counter() - started) * 1000, 1)


def score_top_k(points, evidence, k, *, group=None):
    top = points[:k]
    found = {point["id"] for point in top}
    missing = [
        {key: value for key, value in unit.items() if key != "chunk_ids"}
        for unit in evidence
        if found.isdisjoint(unit["chunk_ids"])
    ]
    result = {
        "returned": len(top),
        "evidence_units": len(evidence),
        "hit_units": len(evidence) - len(missing),
        "complete": not missing if evidence else None,
        "missing_evidence": missing,
    }
    if group is not None:
        opposite = OPPOSITE_GROUP[group]
        result["opposite_ultra_points"] = [
            point["id"]
            for point in top
            if point["payload"]["kind"] == "configuration"
            and point["payload"]["version"]["label"] == ULTRA
            and point["payload"]["version"]["group"] == opposite
        ]
    return result


def retrieval_run(api, path, vector, evidence, target_group, *, filtered):
    points, elapsed_ms = retrieve(
        api, path, vector, group=target_group if filtered else None
    )
    return {
        "elapsed_ms": elapsed_ms,
        "points": points,
        "top_k": {
            str(k): score_top_k(points, evidence, k, group=target_group) for k in TOP_K
        },
    }


def summarize(rows, mode, k, *, paired=False):
    scores = [row[mode]["top_k"][str(k)] for row in rows]
    evaluated = [score for score in scores if score["complete"] is not None]
    complete = sum(score["complete"] for score in evaluated)
    result = {
        "questions": len(rows),
        "scored_questions": len(evaluated),
        "complete_hits": complete,
        "complete_hit_rate": complete / len(evaluated) if evaluated else None,
    }
    if paired:
        mixed = sum(bool(score["opposite_ultra_points"]) for score in scores)
        result.update(
            mixed_questions=mixed, mixing_rate=mixed / len(scores) if scores else None
        )
    return result


def compare_versions(rows):
    comparisons = {}
    for group in ("all", *ULTRA_GROUPS.values()):
        paired = [
            row
            for row in rows
            if "filtered" in row
            and (group == "all" or row["target_ultra_group"] == group)
        ]
        comparisons[group] = {
            str(k): {
                "unfiltered": summarize(paired, "unfiltered", k, paired=True),
                "filtered": summarize(paired, "filtered", k, paired=True),
                "gained_complete": [
                    r["id"]
                    for r in paired
                    if r["unfiltered"]["top_k"][str(k)]["complete"] is False
                    and r["filtered"]["top_k"][str(k)]["complete"] is True
                ],
                "lost_complete": [
                    r["id"]
                    for r in paired
                    if r["unfiltered"]["top_k"][str(k)]["complete"] is True
                    and r["filtered"]["top_k"][str(k)]["complete"] is False
                ],
            }
            for k in TOP_K
        }
    return comparisons


def evaluate(api, collection, cases, labels, embed_queries):
    path = f"/collections/{collection}"
    texts = [query_text(case) for case in cases.values()]
    vectors, call = embed_queries(texts)
    if call.model != EMBEDDING_MODEL or len(vectors) != len(cases):
        raise ValueError(
            "Query embeddings do not match the D8 index or development set"
        )
    rows = []
    for case, label, text, vector in zip(
        cases.values(), labels["cases"], texts, vectors, strict=True
    ):
        target_group = ultra_group(case, text)
        evidence = label["evidence_units"]
        row = {
            "id": case["id"],
            "category": case["category"],
            "question": case["question"],
            "target_ultra_group": target_group,
            "unfiltered": retrieval_run(
                api, path, vector, evidence, target_group, filtered=False
            ),
        }
        if target_group is not None:
            row["filtered"] = retrieval_run(
                api, path, vector, evidence, target_group, filtered=True
            )
        rows.append(row)

    groups = {
        "all": rows,
        "document_and_config": [row for row in rows if row["category"] != "filter"],
        "sql_filter": [row for row in rows if row["category"] == "filter"],
    }
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "split": "dev",
        "collection": collection,
        "dataset_sha256": labels["dataset_sha256"],
        "chunks_sha256": labels["chunks_sha256"],
        "search_params": {"exact": True, "top_k": list(TOP_K)},
        "embeddings": {"queries": len(vectors), **asdict(call)},
        "baseline": {
            name: {str(k): summarize(group, "unfiltered", k) for k in TOP_K}
            for name, group in groups.items()
        },
        "version_comparison": compare_versions(rows),
        "cases": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chunks", type=Path, default=Path("data/corpus/9x-d4-chunks.json")
    )
    parser.add_argument(
        "--labels", type=Path, default=Path("data/corpus/9x-d5-dev-labels.json")
    )
    parser.add_argument("--port", type=int, default=6333)
    parser.add_argument("--output", required=True, type=Path, help="New JSON report")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Invalid Qdrant port")
    try:
        cases, labels, collection, chunks, metadata = load_inputs(
            args.chunks, args.labels
        )
        api = partial(request, args.port)
        verify_index(api, f"/collections/{collection}", metadata, chunks)
        settings = OpenAISettings()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        stream = args.output.open("x", encoding="utf-8")
        try:
            with stream:
                report = evaluate(
                    api, collection, cases, labels, partial(embed, settings=settings)
                )
                json.dump(report, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        except (
            OSError,
            QdrantError,
            OpenAIError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
        ):
            args.output.unlink()
            raise
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
        parser.exit(1, f"Cannot evaluate 9X retrieval: {error}\n")
    print(
        json.dumps(
            {
                "baseline": report["baseline"],
                "version_comparison": report["version_comparison"]["all"],
                "output": str(args.output),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
