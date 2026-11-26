"""Map C7 evidence locations to the chunks that can satisfy them."""

import argparse
import hashlib
import json
from collections import defaultdict
from itertools import product
from pathlib import Path

from car_knowledge_rag.evaluate import read_dataset

CONFIG_SNAPSHOT_ID = "fa6836814b1b3d49400616ebb3f0cfb2b4c112f0fa7c5178dbffcd40e8823f37"
PRODUCT_TEXT_SHA256 = "8f42b87662ffbe50668ea804e1e7ef503e897a16f69349cf72ef0a9bccb9f15e"
LEGEND_MARKERS = ("“●”为标配", "“○”为选装", "“−”为无该配置")


def positive_integers(values):
    if (
        not isinstance(values, list)
        or not values
        or any(type(value) is not int or value < 1 for value in values)
        or len(values) != len(set(values))
    ):
        raise ValueError("Expected distinct positive integers in a source locator")
    return values


def index_chunks(payload):
    if payload["schema_version"] != 1 or not isinstance(payload["chunks"], list):
        raise ValueError("Expected a version 1 D4 chunk file")
    cells, lines = defaultdict(list), defaultdict(list)
    legend, seen = [], set()
    for chunk in payload["chunks"]:
        chunk_id, source, locator = chunk["id"], chunk["source"], chunk["locator"]
        if not isinstance(chunk_id, str) or not chunk_id or chunk_id in seen:
            raise ValueError("Chunk IDs must be nonempty and unique")
        seen.add(chunk_id)
        if source == "S1":
            if chunk["snapshot_id"] != CONFIG_SNAPSHOT_ID:
                raise ValueError(
                    "S1 chunk belongs to a different C7 configuration snapshot"
                )
            if chunk["kind"] == "configuration":
                row = positive_integers([locator["row_index"]])[0]
                column = positive_integers([locator["column_index"]])[0]
                cells[row, column].append(chunk)
            elif chunk["kind"] == "configuration_notice":
                if all(marker in chunk["text"] for marker in LEGEND_MARKERS):
                    legend.append(chunk_id)
            else:
                raise ValueError("Unknown S1 chunk kind")
        elif source == "S2":
            if chunk["source_text_sha256"] != PRODUCT_TEXT_SHA256:
                raise ValueError("S2 chunk belongs to a different C7 product capture")
            if chunk["kind"] not in {"product", "product_notice"}:
                raise ValueError("Unknown S2 chunk kind")
            for line in positive_integers(locator["lines"]):
                lines[line].append(chunk_id)
        else:
            raise ValueError("Unknown chunk source")
    return cells, lines, legend


def map_evidence(cases, payload):
    cells, lines, legend = index_chunks(payload)
    results = []
    for case in cases.values():
        units, scopes = {}, []

        def add(locator, candidates):
            key = json.dumps(locator, sort_keys=True)
            unit = units.setdefault(key, {**locator, "chunk_ids": set()})
            unit["chunk_ids"].update(candidates)

        try:
            for ref in case["evidence"]:
                source = ref["source"]
                if ref == {"source": "S2", "scope": "snapshot"}:
                    scopes.append(ref)
                elif source == "S1" and "scope" not in ref:
                    positions = list(
                        product(
                            positive_integers(ref["rows"]),
                            positive_integers(ref["columns"]),
                        )
                    )
                    for row, column in positions:
                        add(
                            {
                                "source": source,
                                "row_index": row,
                                "column_index": column,
                            },
                            (chunk["id"] for chunk in cells.get((row, column), ())),
                        )
                    for note in ref.get("notes", []):
                        if note == "legend":
                            add({"source": source, "note": note}, legend)
                        elif type(note) is int and note > 0:
                            add(
                                {"source": source, "note": note},
                                (
                                    chunk["id"]
                                    for position in positions
                                    for chunk in cells.get(position, ())
                                    if str(note) in chunk["footnotes"]
                                ),
                            )
                        else:
                            raise ValueError("Unknown configuration note")
                elif source == "S2" and "scope" not in ref:
                    start, end = ref["lines"]
                    if (
                        type(start) is not int
                        or type(end) is not int
                        or not 1 <= start <= end
                    ):
                        raise ValueError(
                            "Expected an inclusive product-page line range"
                        )
                    for line in range(start, end + 1):
                        add({"source": source, "line": line}, lines.get(line, ()))
                else:
                    raise ValueError("Unknown evidence source or scope")
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError(f"{case['id']}: {error}") from error

        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "evidence_units": [
                    {**unit, "chunk_ids": sorted(unit["chunk_ids"])}
                    for unit in units.values()
                ],
                "scope_references": scopes,
            }
        )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chunks", type=Path, help="D4 JSON chunk file")
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument(
        "--output", required=True, type=Path, help="New JSON output file"
    )
    args = parser.parse_args()
    try:
        cases, dataset_sha256 = read_dataset(args.split)
        chunk_data = args.chunks.read_bytes()
        labels = map_evidence(cases, json.loads(chunk_data))
        units = [unit for label in labels for unit in label["evidence_units"]]
        missing = sum(not unit["chunk_ids"] for unit in units)
        report = {
            "schema_version": 1,
            "split": args.split,
            "dataset_sha256": dataset_sha256,
            "chunks_sha256": hashlib.sha256(chunk_data).hexdigest(),
            "summary": {
                "cases": len(labels),
                "evidence_units": len(units),
                "unmapped_units": missing,
                "scope_references": sum(
                    len(label["scope_references"]) for label in labels
                ),
            },
            "cases": labels,
        }
        encoded = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        stream = args.output.open("xb")
        try:
            with stream:
                stream.write(encoded)
        except OSError:
            args.output.unlink()
            raise
    except (ValueError, OSError, TypeError, KeyError, AttributeError) as error:
        parser.error(str(error))
    print(
        f"cases={len(labels)} evidence_units={len(units)} unmapped={missing} output={args.output}"
    )
    return int(missing > 0)


if __name__ == "__main__":
    raise SystemExit(main())
