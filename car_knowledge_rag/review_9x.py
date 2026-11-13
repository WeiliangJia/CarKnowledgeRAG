"""Check selected 9X facts against the pinned official text snapshot."""

import argparse
import hashlib
import json
from pathlib import Path

from car_knowledge_rag.check_config import audit

TEXT_SHA256 = "8a02c63bc86283be0b4feadfff766ca0e2e47b22d308de044cb23c71c8ae0287"
# 1-based line numbers in the pinned snapshot, independently located in B9.
ROWS = {
    1: 47,
    2: 55,
    3: 63,
    4: 71,
    5: 79,
    6: 87,
    7: 95,
    9: 113,
    13: 145,
    14: 153,
    16: 169,
    18: 185,
    20: 201,
    21: 209,
    22: 217,
    23: 225,
    24: 233,
    25: 241,
    26: 249,
    205: 1711,
    206: 1719,
}
NOTES = {"1": 2317, "2": 2318, "11": 2327}
ROW_NOTES = {**dict.fromkeys((20, 21, 22, 23, 25), "1"), 24: "2", 205: "11", 206: "11"}


def classify(row, raw, agrees):
    if not agrees:
        return "difference", None
    if (row, raw) == (205, "●1082/○1050"):
        return "confirmed_conditions", {"H7": 1082, "H9": 1050}
    if (row, raw) == (206, "●2473/○2441"):
        return "confirmed_conditions", {"H7": 2473, "H9": 2441}
    return ("insufficient_evidence" if "/" in raw else "confirmed"), None


def review(text_bytes, fields, normalized, pending):
    if hashlib.sha256(text_bytes).hexdigest() != TEXT_SHA256:
        raise ValueError("Expected the pinned 9X text snapshot")
    lines = text_bytes.decode("utf-8").splitlines()
    columns = normalized["columns"]
    headers = [column["label"] for column in columns]
    groups = [column["group"] for column in columns]
    if headers != lines[31:45:2] or groups != [lines[26]] * 4 + [lines[27]] * 3:
        raise ValueError("Version headers differ from the pinned source")
    definitions = {field["row_index"]: field for field in fields["fields"]}
    records = {(r["row_index"], r["column_index"]): r for r in normalized["records"]}
    findings = []
    for row, line in ROWS.items():
        field = definitions[row]
        note = ROW_NOTES.get(row)
        for col, version in enumerate(columns, 1):
            record = records[row, col]
            raw = lines[line + col - 1]
            agrees = (
                lines[line - 1] == field["source_label"] + (note or "")
                and record["raw"] == raw
                and record["unit"] == field["unit"]
                and record["footnote_ids"] == ([note] if note else [])
                and (
                    not note or normalized["footnotes"][note] == lines[NOTES[note] - 1]
                )
            )
            status, conditions = classify(row, raw, agrees)
            findings.append(
                {
                    "row": row,
                    "version": version,
                    "label": field["source_label"],
                    "unit": record["unit"],
                    "source_raw": raw,
                    "normalized_raw": record["raw"],
                    "source_line": line + col,
                    "label_line": line,
                    "footnote_line": NOTES.get(note),
                    "status": status,
                    "five_seat_conditions": conditions,
                }
            )
    return {
        "source": normalized["source"],
        "text_sha256": TEXT_SHA256,
        "pending_review_count": len(pending["items"]),
        "findings": findings,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="B4 JSON")
    parser.add_argument("bundle", type=Path, help="B7 directory")
    parser.add_argument("text", type=Path, help="Pinned B2 text.txt")
    args = parser.parse_args()
    try:
        bundle = {
            name: json.loads((args.bundle / name).read_bytes())
            for name in ("fields.json", "normalized.json", "review.json")
        }
        if not audit(args.input.read_bytes(), bundle)["ok"]:
            raise ValueError("B8 consistency check failed")
        report = review(
            args.text.read_bytes(),
            bundle["fields.json"],
            bundle["normalized.json"],
            bundle["review.json"],
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    raise SystemExit(int(any(r["status"] == "difference" for r in report["findings"])))


if __name__ == "__main__":
    main()
