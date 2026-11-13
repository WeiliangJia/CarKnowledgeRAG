import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from car_knowledge_rag.check_config import audit
from car_knowledge_rag.normalize_config import normalize_table
from car_knowledge_rag.parse_config import parse_table


@pytest.fixture
def sample():
    html = (Path(__file__).parent / "fixtures/grouped_config.html").read_text(
        encoding="utf-8"
    )
    table = {
        **parse_table(html, ["Ultra版", "Ultra版"]),
        "schema_version": 1,
        "source": {"model_info_id": "10", "model_year_code": "sample"},
        "notices": ["标识“●”为标配，标识“○”为选装，标识“−”为无该配置。"],
    }
    data = json.dumps(table).encode()
    fields, records, review = normalize_table(table)
    metadata = {
        **{
            key: table[key]
            for key in ("schema_version", "source", "columns", "footnotes", "notices")
        },
        "input_sha256": hashlib.sha256(data).hexdigest(),
    }
    return data, {
        "fields.json": {
            **metadata,
            "fields": fields,
            "statuses": ["optional", "standard", "unavailable", "unknown"],
        },
        "normalized.json": {**metadata, "records": records},
        "review.json": {**metadata, "items": review},
    }


def test_pending_values_and_same_named_versions_are_not_errors(sample):
    report = audit(*sample)
    assert report["ok"]
    assert report["expected_records"] == 4
    assert report["expected_pending_review"] == 1


def test_missing_duplicate_conflicting_and_wrong_fields(sample):
    data, bundle = sample
    records = bundle["normalized.json"]["records"]
    records.pop()
    records.append(deepcopy(records[0]))
    records.append({**records[0], "unit": "mm", "footnote_ids": ["bogus"]})
    report = audit(data, bundle)
    assert {item["code"] for item in report["issues"]} == {
        "missing_position",
        "duplicate",
        "conflict",
        "content_mismatch",
    }
    assert not report["ok"]


def test_missing_review_and_wrong_source(sample):
    data, bundle = sample
    bundle["review.json"]["items"].clear()
    bundle["review.json"]["input_sha256"] = "wrong"
    assert {item["code"] for item in audit(data, bundle)["issues"]} == {
        "missing_position",
        "metadata_mismatch",
    }
