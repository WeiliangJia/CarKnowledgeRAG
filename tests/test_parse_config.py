import json
from pathlib import Path

import pytest

from car_knowledge_rag.file_hash import register_file
from car_knowledge_rag.parse_config import parse_snapshot, parse_table
from car_knowledge_rag.verify_manifest import Baseline

HTML = (Path(__file__).parent / "fixtures/grouped_config.html").read_text(
    encoding="utf-8"
)
HEADERS = ["Ultra版", "Ultra版"]


def test_grouped_table_keeps_positions_units_and_footnotes():
    result = parse_table(HTML, HEADERS)
    assert [column["group"] for column in result["columns"]] == ["六座", "五座"]
    battery, air = result["rows"]
    assert battery["label"] == "电池(kWh)"
    assert battery["unit"] == "kWh"
    assert battery["footnote_ids"] == ["1"]
    assert "示例条件" in result["footnotes"]["1"]
    assert [(cell["column_index"], cell["raw"]) for cell in battery["cells"]] == [
        (1, "55/70"),
        (2, "70"),
    ]
    assert air["unit"] is None
    assert [cell["raw"] for cell in air["cells"]] == ["●", "○"]


@pytest.mark.parametrize(
    ("html", "headers", "message"),
    [
        (HTML.replace('<span class="value-item">70</span>', ""), HEADERS, "cells"),
        (HTML.replace("<sup>1</sup>", "<sup>2</sup>"), HEADERS, "Undefined footnote"),
        (HTML.replace("flex: 1", "flex: 2", 1), HEADERS, "group span"),
        (HTML, ["Other", "Ultra版"], "headers"),
    ],
)
def test_rejects_ambiguous_tables(html, headers, message):
    with pytest.raises(ValueError, match=message):
        parse_table(html, headers)


def test_snapshot_provenance_and_tamper_detection(tmp_path):
    snapshot = tmp_path / "10/config"
    snapshot.mkdir(parents=True)
    html_path = snapshot / "rendered.html"
    html_path.write_text(HTML, encoding="utf-8")
    receipt = {
        "status": "success",
        "kind": "config",
        "model_info_id": "10",
        "model_year_code": "sample",
        "final_url": "https://www.zeekrlife.com/zh-cn/config?modelInfoId=10&modelYearCode=sample",
        "observed_columns": HEADERS,
        "finished_at": "2026-11-04T00:00:00Z",
    }
    receipt_path = snapshot / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    baseline = Baseline(
        schema_version=1,
        path_base="supplied_raw_root",
        issues=[],
        files=[
            {**register_file(path, root=tmp_path), "file_status": "registered"}
            for path in (html_path, receipt_path)
        ],
    )
    result = parse_snapshot(tmp_path, Path("10/config"), baseline)
    assert result["source"]["url"] == receipt["final_url"]
    assert (
        result["source"]["files"]["rendered.html"]["path"] == "10/config/rendered.html"
    )
    html_path.write_text(HTML.replace("55/70", "55/71"), encoding="utf-8")
    with pytest.raises(ValueError, match="differs from manifest"):
        parse_snapshot(tmp_path, Path("10/config"), baseline)
