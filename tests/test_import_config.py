import pytest

from car_knowledge_rag.import_config import prepare


def test_import_refuses_invalid_bundle():
    with pytest.raises((ValueError, KeyError)):
        prepare(b"{}", {}, b"")


def test_prepare_keeps_conditions_separate_from_numeric_values(monkeypatch):
    source = {
        "model_info_id": "10",
        "model_year_code": "sample",
        "url": "https://example.invalid/config",
        "captured_at": "2026-11-04T00:00:00Z",
    }
    column = {"index": 1, "group": "六座", "label": "Ultra版"}
    finding = {"row": 1, "version": column, "status": "insufficient_evidence"}
    monkeypatch.setattr(
        "car_knowledge_rag.import_config.audit", lambda *_: {"ok": True}
    )
    monkeypatch.setattr(
        "car_knowledge_rag.import_config.review", lambda *_: {"findings": [finding]}
    )
    bundle = {
        "fields.json": {
            "fields": [
                {
                    "row_index": 1,
                    "field_id": "sample:row-1",
                    "name": "电池容量",
                    "unit": "kWh",
                    "test_cycle": None,
                    "range_type": None,
                }
            ]
        },
        "normalized.json": {
            "source": source,
            "input_sha256": "a" * 64,
            "columns": [column],
            "footnotes": {},
            "notices": [],
            "records": [
                {
                    "row_index": 1,
                    "column_index": 1,
                    "raw": "55/70",
                    "number": None,
                    "status": "unknown",
                    "qualifier": None,
                    "footnote_ids": [],
                }
            ],
        },
        "review.json": {
            "items": [
                {
                    "row_index": 1,
                    "column_index": 1,
                    "reason": "multiple_values_or_conditions",
                }
            ]
        },
    }
    snapshot, versions, fields, facts = prepare(b"", bundle, b"")
    assert snapshot["source_url"] == source["url"]
    assert versions[0]["group_label"] == "六座"
    assert fields[0]["unit"] == "kWh"
    assert facts[0]["raw"] == "55/70"
    assert facts[0]["number"] is None
    assert facts[0]["pending_reason"] == "multiple_values_or_conditions"
    assert facts[0]["review_status"] == "insufficient_evidence"
    assert facts[0]["review_evidence"] == finding
    finding["status"] = "difference"
    with pytest.raises(ValueError, match="source check"):
        prepare(b"", bundle, b"")
