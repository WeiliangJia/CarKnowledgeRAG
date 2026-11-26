import pytest

from car_knowledge_rag.map_retrieval_evidence import (
    CONFIG_SNAPSHOT_ID,
    PRODUCT_TEXT_SHA256,
    map_evidence,
)


def configuration(chunk_id, column, footnotes):
    return {
        "id": chunk_id,
        "source": "S1",
        "kind": "configuration",
        "snapshot_id": CONFIG_SNAPSHOT_ID,
        "locator": {"row_index": 20, "column_index": column},
        "footnotes": footnotes,
    }


def product_block(chunk_id, lines):
    return {
        "id": chunk_id,
        "source": "S2",
        "kind": "product",
        "source_text_sha256": PRODUCT_TEXT_SHA256,
        "locator": {"lines": lines},
    }


def test_maps_version_footnote_and_overlapping_product_lines():
    cases = {
        "Q01": {
            "id": "Q01",
            "category": "explanation",
            "evidence": [
                {"source": "S1", "rows": [20], "columns": [2], "notes": [1, "legend"]},
                {"source": "S2", "lines": [85, 87]},
                {"source": "S2", "scope": "snapshot"},
            ],
        },
    }
    payload = {
        "schema_version": 1,
        "chunks": [
            configuration("six-seat", 2, {"1": "续航条件"}),
            configuration("five-seat", 5, {"1": "续航条件"}),
            {
                "id": "legend",
                "source": "S1",
                "kind": "configuration_notice",
                "snapshot_id": CONFIG_SNAPSHOT_ID,
                "locator": {"notice_index": 1},
                "text": "标识“●”为标配，标识“−”为无该配置，标识“○”为选装",
            },
            product_block("first", [85, 86]),
            product_block("second", [86, 87]),
        ],
    }
    mapped = map_evidence(cases, payload)[0]
    assert [unit["chunk_ids"] for unit in mapped["evidence_units"]] == [
        ["six-seat"],
        ["six-seat"],
        ["legend"],
        ["first"],
        ["first", "second"],
        ["second"],
    ]
    assert mapped["scope_references"] == [{"source": "S2", "scope": "snapshot"}]


def test_reports_missing_evidence_and_rejects_different_snapshot():
    entry = configuration("result", 5, {"1": "续航条件"})
    cases = {
        "Q01": {
            "id": "Q01",
            "category": "lookup",
            "evidence": [
                {"source": "S1", "rows": [20], "columns": [2], "notes": [1]},
            ],
        }
    }
    payload = {"schema_version": 1, "chunks": [entry]}
    result = map_evidence(cases, payload)[0]
    assert [unit["chunk_ids"] for unit in result["evidence_units"]] == [[], []]
    entry["snapshot_id"] = "wrong"
    with pytest.raises(ValueError, match="different C7 configuration snapshot"):
        map_evidence(cases, payload)
