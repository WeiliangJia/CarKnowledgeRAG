import pytest

from car_knowledge_rag.normalize_config import normalize_cell, normalize_table


@pytest.mark.parametrize(
    ("raw", "unit", "status", "number", "qualifier", "reason"),
    [
        ("5239", "mm", "unknown", 5239, None, None),
        ("6人", "人", "unknown", 6, None, None),
        ("55/70", "kWh", "unknown", None, None, "multiple_values_or_conditions"),
        ("●1082/○1050", "L", "unknown", None, None, "multiple_values_or_conditions"),
        ("●(两侧座椅)", None, "standard", None, "(两侧座椅)", "check_qualifier"),
        ("○仅极夜黑可选", None, "optional", None, "仅极夜黑可选", "check_qualifier"),
        ("-", None, "unavailable", None, None, None),
        ("", None, "unknown", None, None, "empty_value"),
    ],
)
def test_normalize_cell(raw, unit, status, number, qualifier, reason):
    actual, issue = normalize_cell(raw, unit)
    assert actual == {
        "raw": raw,
        "status": status,
        "number": number,
        "qualifier": qualifier,
    }
    assert issue == reason


def test_normalize_table_preserves_scope_and_source_positions():
    table = {
        "schema_version": 1,
        "source": {"model_info_id": "10", "model_year_code": "sample"},
        "columns": [
            {"index": 1, "group": "六座", "label": "Ultra版"},
            {"index": 2, "group": "五座", "label": "Ultra版"},
        ],
        "footnotes": {"1": "测试条件", "2": "栏目条件"},
        "notices": ["标识“●”为标配配置，标识“−”为无该配置，标识“○”为选装配置。"],
        "rows": [
            {
                "index": 1,
                "label": "CLTC纯电工况续航里程(km)",
                "raw": "原表标签",
                "unit": "km",
                "section": [{"raw": "动力", "footnote_ids": ["2"]}],
                "description": None,
                "footnote_ids": ["1"],
                "cells": [
                    {"column_index": 1, "raw": "300", "footnote_ids": []},
                    {"column_index": 2, "raw": "288/380", "footnote_ids": ["1"]},
                ],
            }
        ],
    }
    fields, records, review = normalize_table(table)
    assert fields[0]["test_cycle"] == "CLTC"
    assert fields[0]["range_type"] == "纯电"
    assert records[0]["number"] == 300
    assert records[1]["footnote_ids"] == ["2", "1"]
    assert review[0]["column_index"] == 2
    table["rows"][0]["cells"].reverse()
    with pytest.raises(ValueError, match="column indexes"):
        normalize_table(table)
