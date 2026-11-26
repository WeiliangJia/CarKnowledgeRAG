import pytest

from car_knowledge_rag.chunk_corpus import chunks_from_corpus


@pytest.fixture
def corpus():
    source = {
        "url": "https://example.invalid/9x",
        "captured_at": "2026-11-04T00:00:00Z",
        "files": {"text.txt": {"sha256": "a" * 64}},
    }
    return {
        "schema_version": 1,
        "model": {
            "name": "极氪 9X",
            "model_info_id": "10",
            "model_year_code": "GMY_9X_01",
        },
        "capture": "example",
        "sources": {"S1": source, "S2": source},
        "product": {
            "blocks": [
                {
                    "section": ["座舱"],
                    "anchor": "cabin",
                    "lines": [{"line": 181, "text": "22个按摩点位"}],
                },
                {
                    "section": ["座舱"],
                    "anchor": None,
                    "lines": [{"line": 182, "text": "* 仅限前排及二排两侧"}],
                },
                {
                    "section": ["安全"],
                    "anchor": "safety",
                    "lines": [{"line": 185, "text": "主驾座椅气囊"}],
                },
            ],
            "notices": [],
        },
        "configuration": {
            "snapshot_id": "9x-example",
            "fields": [
                {
                    "field_id": "range",
                    "row_index": 20,
                    "test_cycle": "CLTC",
                    "range_type": "纯电",
                }
            ],
            "records": [
                {
                    "snapshot_id": "9x-example",
                    "field_id": "range",
                    "row_index": 20,
                    "column_index": 2,
                    "version": {"group": "六座", "label": "Ultra"},
                    "raw": "288/380",
                    "number": None,
                    "unit": "km",
                    "status": "unknown",
                    "qualifier": None,
                    "footnote_ids": ["1"],
                    "footnotes": {"1": "工程开发模拟数据"},
                    "pending_reason": "multiple_values_or_conditions",
                    "review_status": "insufficient_evidence",
                    "review_evidence": {"source_line": 203},
                    "text": "六座 Ultra\nCLTC纯电：288/380 km\n工程开发模拟数据",
                }
            ],
            "notices": [],
        },
    }


def test_chunks_keep_notes_with_evidence_and_preserve_locators(corpus):
    chunks = chunks_from_corpus(corpus)
    cabin, safety, config = chunks
    assert cabin["locator"] == {"lines": [181, 182], "anchor": "cabin"}
    assert "22个按摩点位\n* 仅限前排及二排两侧" in cabin["text"]
    assert safety["locator"]["lines"] == [185]
    assert config["locator"] == {"row_index": 20, "column_index": 2}
    assert config["raw"] == "288/380" and config["number"] is None
    assert config["footnotes"] == {"1": "工程开发模拟数据"}
    assert config["review_evidence"] == {"source_line": 203}
    assert len(corpus["product"]["blocks"][0]["lines"]) == 1
    assert chunks == chunks_from_corpus(corpus, max_chars=800)


def test_rejects_limit_that_would_truncate_evidence(corpus):
    with pytest.raises(ValueError, match="characters"):
        chunks_from_corpus(corpus, max_chars=20)
