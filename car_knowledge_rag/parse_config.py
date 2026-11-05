"""Parse the grouped configuration table in a verified B2 snapshot."""

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup, Tag

from car_knowledge_rag.verify_manifest import Baseline

UNITS = {"mm", "m", "km", "km/h", "kW", "kWh", "L", "min", "N·m", "s"}


def required(node: Tag, selector: str) -> Tag:
    result = node.select_one(selector)
    if result is None:
        raise ValueError(f"Missing table element: {selector}")
    return result


def text(node: Tag) -> str:
    return node.get_text(" ", strip=True)


def annotated(node: Tag, notes: dict) -> dict:
    refs = [text(ref) for ref in node.select("sup")]
    for ref in refs:
        if ref not in notes:
            raise ValueError(f"Undefined footnote: {ref}")
    return {"raw": text(node), "footnote_ids": refs}


def parse_table(html: str, observed_columns: list[str]) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    table = required(soup, ".config-right")
    labels = [text(node) for node in table.select(".model-item > .title")]
    if not labels or labels != observed_columns or not all(labels):
        raise ValueError("Version headers do not match the capture receipt")
    groups = []
    for node in table.select(".version-wrapper > .version-item"):
        label = text(required(node, ".version-item-title"))
        span = re.search(
            r"(?:^|;)\s*flex:\s*([1-9]\d*)\s+1\s+0%;", node.get("style", "")
        )
        if not span or not label or int(span[1]) > len(labels) - len(groups):
            raise ValueError("Invalid version group span")
        groups.extend([label] * int(span[1]))
    if len(groups) != len(labels):
        raise ValueError("Version groups do not cover every column")
    columns = [
        {"index": index, "group": group, "label": label}
        for index, (group, label) in enumerate(zip(groups, labels, strict=True), 1)
    ]
    notes, notices = {}, []
    for node in soup.select(".config-tips > .tip-content"):
        raw = text(node)
        match = re.match(r'^标识[“"](\d+)[”"]', raw)
        if match:
            if match[1] in notes:
                raise ValueError(f"Duplicate footnote: {match[1]}")
            notes[match[1]] = raw
        elif raw:
            notices.append(raw)

    rows = []
    for index, row in enumerate(table.select(".parameterList-item"), 1):
        name = required(row, ":scope > .name > .el-tooltip")
        label = " ".join(
            value.strip() for value in name.strings if value.find_parent("sup") is None
        )
        if not label:
            raise ValueError(f"Row {index} has no parameter name")
        unit = re.search(r"[（(]([^()（）]+)[）)]$", label)
        description = row.select_one(":scope > .name > .desc")
        section = []
        for level in ("first", "second", "third"):
            parent = row.find_parent(class_=f"{level}-level")
            title = (
                parent.select_one(f":scope > .{level}-level-title") if parent else None
            )
            if title is not None:
                section.append(annotated(title, notes))
            elif level == "first":
                raise ValueError(f"Row {index} has no top-level section")
        cells = row.select(":scope > .value > .value-item")
        if len(cells) != len(columns):
            raise ValueError(
                f"Row {index} ({label}) has {len(cells)} cells, expected {len(columns)}"
            )
        rows.append(
            {
                "index": index,
                "section": section,
                "label": label,
                "unit": unit[1] if unit and unit[1] in UNITS else None,
                **annotated(name, notes),
                "description": annotated(description, notes)
                if description is not None
                else None,
                "cells": [
                    {"column_index": column, **annotated(cell, notes)}
                    for column, cell in enumerate(cells, 1)
                ],
            }
        )
    if not rows:
        raise ValueError("Configuration table has no parameter rows")
    return {"columns": columns, "rows": rows, "footnotes": notes, "notices": notices}


def parse_snapshot(root: Path, directory: Path, baseline: Baseline) -> dict:
    if baseline.issues:
        raise ValueError("Source manifest has unresolved issues")
    root = root.resolve(strict=True)
    entries = {entry.path: entry for entry in baseline.files}
    fingerprints = {}

    def verified_file(name: str) -> str:
        path = (root / directory / name).resolve(strict=True)
        key = path.relative_to(root).as_posix()
        entry = entries.get(key)
        if entry is None or entry.file_status != "registered":
            raise ValueError(f"Missing registered fingerprint: {key}")
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if (len(data), digest) != (entry.size_bytes, entry.sha256):
            raise ValueError(f"Source differs from manifest: {key}")
        fingerprints[name] = {"path": key, "sha256": digest}
        return data.decode("utf-8")

    receipt = json.loads(verified_file("receipt.json"))
    if receipt["kind"] != "config" or receipt["status"] != "success":
        raise ValueError("Expected a successful configuration receipt")
    url = urlsplit(receipt["final_url"])
    query = parse_qs(url.query)
    if (
        (url.scheme, url.netloc, url.path)
        != ("https", "www.zeekrlife.com", "/zh-cn/config")
        or query.get("modelInfoId") != [receipt["model_info_id"]]
        or query.get("modelYearCode") != [receipt["model_year_code"]]
    ):
        raise ValueError("Configuration source URL does not match receipt identity")
    table = parse_table(verified_file("rendered.html"), receipt["observed_columns"])
    return {
        "schema_version": 1,
        "source": {
            "url": receipt["final_url"],
            "model_info_id": receipt["model_info_id"],
            "model_year_code": receipt["model_year_code"],
            "captured_at": receipt["finished_at"],
            "files": fingerprints,
        },
        **table,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "snapshot", type=Path, help="Configuration directory relative to raw root"
    )
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/zeekr"))
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if (
        args.snapshot.is_absolute()
        or args.snapshot.drive
        or ".." in args.snapshot.parts
    ):
        parser.error("Snapshot must be relative to the raw root")
    if args.output.resolve().is_relative_to(args.raw_root.resolve()):
        parser.error("Output must be outside the raw root")
    try:
        baseline = Baseline.model_validate_json(args.manifest.read_bytes())
        result = parse_snapshot(args.raw_root, args.snapshot, baseline)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Cannot parse snapshot: {error}\n")
    print(
        f"columns={len(result['columns'])} rows={len(result['rows'])} output={args.output}"
    )


if __name__ == "__main__":
    main()
