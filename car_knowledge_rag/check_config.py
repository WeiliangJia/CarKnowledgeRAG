"""Audit the B7 bundle against its B4 input without changing either."""

import argparse
import hashlib
import json
from pathlib import Path

from car_knowledge_rag.normalize_config import STATUS, normalize_table


def audit(data: bytes, bundle: dict) -> dict:
    table = json.loads(data)
    fields, records, review = normalize_table(table)
    columns = {column["index"]: column for column in table["columns"]}
    source = table["source"]
    issues = []
    metadata = {
        "schema_version": 1,
        "source": source,
        "input_sha256": hashlib.sha256(data).hexdigest(),
        **{key: table[key] for key in ("footnotes", "notices", "columns")},
    }

    def same(left, right):
        return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)

    def issue(code, filename, row=None, column=None, **details):
        issues.append(
            {
                "code": code,
                "file": filename,
                "row_index": row,
                "column_index": column,
                "version": columns.get(column),
                **details,
            }
        )

    for filename, key, expected in (
        ("fields.json", "fields", fields),
        ("normalized.json", "records", records),
        ("review.json", "items", review),
    ):
        document = bundle.get(filename)
        if not isinstance(document, dict):
            issue("missing_or_invalid_document", filename)
            continue
        for name, value in metadata.items():
            if not same(document.get(name), value):
                issue("metadata_mismatch", filename, member=name)
        if key == "fields" and not same(
            document.get("statuses"), sorted({*STATUS.values(), "unknown"})
        ):
            issue("metadata_mismatch", filename, member="statuses")
        items = document.get(key)
        if not isinstance(items, list):
            issue("invalid_items", filename)
            continue
        expected_by_key = {
            (item["row_index"], item.get("column_index")): item for item in expected
        }
        seen = {}
        for item in items:
            if (
                not isinstance(item, dict)
                or type(item.get("row_index")) is not int
                or (key != "fields" and type(item.get("column_index")) is not int)
            ):
                issue("invalid_position", filename)
                continue
            position = (
                item["row_index"],
                None if key == "fields" else item["column_index"],
            )
            if position in seen:
                code = "duplicate" if same(seen[position], item) else "conflict"
                issue(code, filename, *position)
            seen.setdefault(position, item)
            reference = expected_by_key.get(position)
            if reference is None:
                issue("unexpected_position", filename, *position)
            elif not same(item, reference):
                changed = sorted(
                    name
                    for name in item.keys() | reference.keys()
                    if name not in item
                    or name not in reference
                    or not same(item[name], reference[name])
                )
                issue("content_mismatch", filename, *position, members=changed)
        for position in sorted(expected_by_key.keys() - seen.keys()):
            issue("missing_position", filename, *position)

    return {
        "ok": not issues,
        "source": source,
        "expected_fields": len(fields),
        "expected_records": len(records),
        "expected_pending_review": len(review),
        "issues": issues,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="B4 JSON")
    parser.add_argument(
        "bundle", type=Path, help="Directory with the three B7 JSON files"
    )
    args = parser.parse_args()
    try:
        bundle = {}
        for name in ("fields.json", "normalized.json", "review.json"):
            try:
                bundle[name] = json.loads((args.bundle / name).read_bytes())
            except (OSError, ValueError):
                bundle[name] = None
        report = audit(args.input.read_bytes(), bundle)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        parser.error(f"Invalid B4 input: {error}")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
