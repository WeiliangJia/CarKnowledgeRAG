"""Normalize the B4 9X table without guessing configuration conditions."""

import argparse
import hashlib
import json
import re
from pathlib import Path

STATUS = {"●": "standard", "○": "optional", "-": "unavailable", "−": "unavailable"}
NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?")
NAMES = {
    "长度(mm)": "车身长度",
    "宽度(mm)": "车身宽度",
    "高度(mm)": "车身高度",
    "混动专属电池包(kWh)": "电池容量",
}


def normalize_cell(raw, unit):
    value = raw.strip()
    result = {"raw": raw, "status": "unknown", "number": None, "qualifier": None}
    if not value:
        return result, "empty_value"
    if value in STATUS:
        result["status"] = STATUS[value]
        return result, None
    if (unit and "/" in value) or ("●" in value and "○" in value):
        return result, "multiple_values_or_conditions"
    if value[0] in "●○":
        result.update(status=STATUS[value[0]], qualifier=value[1:].strip())
        return result, "check_qualifier"
    candidate = value.removesuffix("人") if unit == "人" else value
    if unit and NUMBER.fullmatch(candidate):
        result["number"] = float(candidate) if "." in candidate else int(candidate)
        return result, None
    if unit:
        return result, "unparsed_numeric_value"
    return result, None


def normalize_table(table):
    if table["schema_version"] != 1 or table["source"]["model_info_id"] != "10":
        raise ValueError("Expected the B4 9X schema")
    source, columns, notes = table["source"], table["columns"], table["footnotes"]
    if not columns or not table["rows"]:
        raise ValueError("Expected nonempty columns and rows")
    indexes = list(range(1, len(columns) + 1))
    if [column["index"] for column in columns] != indexes:
        raise ValueError("Unexpected version column indexes")
    if [row["index"] for row in table["rows"]] != list(
        range(1, len(table["rows"]) + 1)
    ):
        raise ValueError("Unexpected row indexes")
    legend = " ".join(table["notices"])
    if any(
        token not in legend for token in ("“●”为标配", "“○”为选装", "“−”为无该配置")
    ):
        raise ValueError("Expected the 9X status legend")
    fields, records, review = [], [], []
    for row in table["rows"]:
        index, label = row["index"], row["label"]
        unit = "人" if label == "乘坐人数" else row["unit"]
        field_id = f"{source['model_year_code']}:row-{index}"
        metric = re.fullmatch(r"(CLTC|WLTC)(纯电|综合)工况续航里程\(km\)", label)
        fields.append(
            {
                "field_id": field_id,
                "row_index": index,
                "source_label": label,
                "raw_label": row["raw"],
                "name": "续航里程" if metric else NAMES.get(label, label),
                "test_cycle": metric[1] if metric else None,
                "range_type": metric[2] if metric else None,
                "unit": unit,
                "value_type": "number_or_raw" if unit else "status_or_text",
                "section": row["section"],
                "description": row["description"],
                "footnote_ids": row["footnote_ids"],
            }
        )
        if [cell["column_index"] for cell in row["cells"]] != indexes:
            raise ValueError(f"Unexpected cell column indexes at row {index}")
        context = [*row["section"], row]
        if row["description"]:
            context.append(row["description"])
        for cell in row["cells"]:
            column = cell["column_index"]
            refs = list(
                dict.fromkeys(
                    ref for part in [*context, cell] for ref in part["footnote_ids"]
                )
            )
            if any(ref not in notes for ref in refs):
                raise ValueError(f"Unknown footnote at row {index}, column {column}")
            parsed, reason = normalize_cell(cell["raw"], unit)
            record = {
                "field_id": field_id,
                "row_index": index,
                "column_index": column,
                "unit": unit,
                **parsed,
                "footnote_ids": refs,
            }
            records.append(record)
            if reason:
                review.append({**record, "reason": reason})
    return fields, records, review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, help="New directory under data/normalized")
    args = parser.parse_args()
    root = (Path(__file__).resolve().parents[1] / "data/normalized").resolve()
    output = args.output.resolve()
    if output == root or not output.is_relative_to(root):
        parser.error("Output must be a new subdirectory of data/normalized")
    try:
        data = args.input.read_bytes()
        table = json.loads(data)
        fields, records, review = normalize_table(table)
        common = {
            "schema_version": 1,
            "source": table["source"],
            "input_sha256": hashlib.sha256(data).hexdigest(),
            "footnotes": table["footnotes"],
            "notices": table["notices"],
            "columns": table["columns"],
        }
        outputs = {
            "fields.json": {
                "fields": fields,
                "statuses": sorted({*STATUS.values(), "unknown"}),
            },
            "normalized.json": {"records": records},
            "review.json": {"items": review},
        }
        output.mkdir(parents=True, exist_ok=False)
        for filename, payload in outputs.items():
            with (output / filename).open("x", encoding="utf-8") as stream:
                json.dump({**common, **payload}, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Cannot normalize snapshot: {error}\n")
    print(f"fields={len(fields)} records={len(records)} review={len(review)}")


if __name__ == "__main__":
    main()
