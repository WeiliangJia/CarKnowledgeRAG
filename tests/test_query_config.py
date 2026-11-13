from decimal import Decimal

import pytest

from car_knowledge_rag.query_config import ConfigQuery, NumericCondition, SelectionError


@pytest.fixture
def query(monkeypatch):
    query = object.__new__(ConfigQuery)
    query.source = {"source_url": "https://example.invalid/config"}
    query.footnotes = {"1": "Official test conditions"}
    monkeypatch.setattr(
        query,
        "versions",
        lambda: [
            {"column_index": 2, "group_label": "9X六座版", "label": "Ultra版"},
            {"column_index": 5, "group_label": "9X五座版", "label": "Ultra版"},
            {"column_index": 6, "group_label": "9X五座版", "label": "Hyper版"},
        ],
    )
    monkeypatch.setattr(
        query,
        "fields",
        lambda: [
            {
                "row_index": 5,
                "field_id": "seats",
                "name": "乘坐人数",
                "source_label": "乘坐人数",
                "unit": "人",
            },
            {
                "row_index": 20,
                "field_id": "cltc",
                "name": "续航里程",
                "source_label": "CLTC纯电",
                "unit": "km",
            },
            {
                "row_index": 22,
                "field_id": "wltc",
                "name": "续航里程",
                "source_label": "WLTC纯电",
                "unit": "km",
            },
        ],
    )
    values = {
        (5, 2): "6",
        (5, 5): "5",
        (5, 6): "5",
        (20, 2): "288/380",
        (20, 5): "288/380",
        (20, 6): "355",
    }

    def rows(statement, *, rows, columns):
        return [
            {
                "row_index": row,
                "column_index": column,
                "raw": raw,
                "number": Decimal(raw) if raw.isdecimal() else None,
                "status": "unknown",
                "qualifier": None,
                "footnote_ids": ["1"] if row == 20 else [],
                "pending_reason": None
                if raw.isdecimal()
                else "multiple_values_or_conditions",
                "review_status": "confirmed"
                if raw.isdecimal()
                else "insufficient_evidence",
            }
            for (row, column), raw in values.items()
            if row in rows and column in columns
        ]

    monkeypatch.setattr(query, "_rows", rows)
    return query


def test_lookup_preserves_source_and_returns_candidates(query):
    with pytest.raises(SelectionError) as exc:
        query.lookup("cltc", "Ultra版")
    assert exc.value.result["status"] == "ambiguous"
    assert [item["column_index"] for item in exc.value.result["candidates"]] == [2, 5]
    with pytest.raises(SelectionError) as exc:
        query.lookup("续航里程", 2)
    assert [item["field_id"] for item in exc.value.result["candidates"]] == [
        "cltc",
        "wltc",
    ]
    result = query.lookup("CLTC纯电", "Ultra版", group="9X六座版")
    assert result["source"]["source_url"] == "https://example.invalid/config"
    assert result["fact"]["footnotes"] == {"1": "Official test conditions"}
    assert result["fact"]["raw"] == "288/380"
    assert result["fact"]["number"] is None


def test_compare_keeps_requested_order_and_field_identity(query):
    result = query.compare([5, 2], ["乘坐人数", "wltc"])
    assert [row["field"]["field_id"] for row in result["rows"]] == ["seats", "wltc"]
    assert [fact["number"] for fact in result["rows"][0]["facts"]] == [5, 6]
    assert result["rows"][1]["facts"] == [None, None]


def test_filter_applies_three_valued_and(query):
    result = query.filter(
        [
            NumericCondition("乘坐人数", "eq", 5, "人"),
            NumericCondition("cltc", "ge", 350, "km"),
        ]
    )
    for outcome, column in (("match", 6), ("no_match", 2), ("undetermined", 5)):
        assert [item["version"]["column_index"] for item in result[outcome]] == [column]
    assert result["undetermined"][0]["conditions"][1]["fact"]["raw"] == "288/380"
    with pytest.raises(ValueError, match="requires unit"):
        query.filter([NumericCondition("cltc", "ge", 350, "m")])
