"""Import an audited 9X bundle as one immutable PostgreSQL snapshot."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from car_knowledge_rag.check_config import audit
from car_knowledge_rag.review_9x import review


def prepare(data, bundle, source_text):
    if not audit(data, bundle)["ok"]:
        raise ValueError("B8 consistency check failed")
    fields, normalized, pending = (
        bundle[name] for name in ("fields.json", "normalized.json", "review.json")
    )
    verified = review(source_text, fields, normalized, pending)
    if any(item["status"] == "difference" for item in verified["findings"]):
        raise ValueError("B9 source check found differences")
    source = normalized["source"]
    snapshot_id = normalized["input_sha256"]
    digest = hashlib.sha256(
        json.dumps([bundle, verified], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    snapshot = {
        "id": snapshot_id,
        "bundle_sha256": digest,
        "model_info_id": source["model_info_id"],
        "model_year_code": source["model_year_code"],
        "source_url": source["url"],
        "captured_at": source["captured_at"],
        "source": source,
        "footnotes": normalized["footnotes"],
        "notices": normalized["notices"],
    }
    versions = [
        {
            "snapshot_id": snapshot_id,
            "column_index": c["index"],
            "group_label": c["group"],
            "label": c["label"],
        }
        for c in normalized["columns"]
    ]
    definitions = [
        {
            "snapshot_id": snapshot_id,
            "definition": field,
            **{
                key: field[key]
                for key in (
                    "row_index",
                    "field_id",
                    "name",
                    "unit",
                    "test_cycle",
                    "range_type",
                )
            },
        }
        for field in fields["fields"]
    ]
    reasons = {
        (r["row_index"], r["column_index"]): r["reason"] for r in pending["items"]
    }
    evidence = {(r["row"], r["version"]["index"]): r for r in verified["findings"]}
    facts = []
    for record in normalized["records"]:
        key = (record["row_index"], record["column_index"])
        finding = evidence.get(key)
        facts.append(
            {
                "snapshot_id": snapshot_id,
                **{
                    name: record[name]
                    for name in (
                        "row_index",
                        "column_index",
                        "raw",
                        "number",
                        "status",
                        "qualifier",
                        "footnote_ids",
                    )
                },
                "pending_reason": reasons.get(key),
                "review_status": finding["status"] if finding else "not_reviewed",
                "review_evidence": finding,
            }
        )
    return snapshot, versions, definitions, facts


def store(connection, prepared):
    snapshot, *children = prepared
    metadata = MetaData()
    root = Table("config_snapshots", metadata, autoload_with=connection)
    inserted = connection.execute(
        insert(root)
        .values(snapshot)
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(root.c.id)
    ).scalar_one_or_none()
    if inserted is None:
        stored = connection.execute(
            select(root.c.bundle_sha256).where(root.c.id == snapshot["id"])
        ).scalar_one()
        if stored != snapshot["bundle_sha256"]:
            raise ValueError("Snapshot already exists with different import content")
        return False
    for name, rows in zip(
        ("config_versions", "config_fields", "config_facts"), children, strict=True
    ):
        table = Table(name, metadata, autoload_with=connection)
        connection.execute(table.insert(), rows)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="B4 JSON")
    parser.add_argument("bundle", type=Path, help="B7 directory")
    parser.add_argument("text", type=Path, help="Pinned B2 text.txt for B9")
    args = parser.parse_args()
    try:
        bundle = {
            name: json.loads((args.bundle / name).read_bytes())
            for name in ("fields.json", "normalized.json", "review.json")
        }
        prepared = prepare(args.input.read_bytes(), bundle, args.text.read_bytes())
        engine = create_engine(os.environ["DATABASE_URL"])
        with engine.begin() as connection:
            created = store(connection, prepared)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        SQLAlchemyError,
    ) as error:
        parser.exit(
            1,
            f"Import failed ({type(error).__name__}); check inputs, connection and migration.\n",
        )
    snapshot, versions, fields, facts = prepared
    print(
        f"snapshot={snapshot['id']} inserted={created} versions={len(versions)} fields={len(fields)} facts={len(facts)}"
    )


if __name__ == "__main__":
    main()
