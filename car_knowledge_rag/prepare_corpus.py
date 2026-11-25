"""Export the pinned 9X product text and audited configuration evidence."""

import argparse
import hashlib
import json
from pathlib import Path

from bs4 import BeautifulSoup

from car_knowledge_rag.import_config import prepare
from car_knowledge_rag.parse_config import parse_table
from car_knowledge_rag.verify_manifest import Baseline

CAPTURE = Path("20261104T061714920392Z-70f8b89f/10")
MANIFEST = Path("manifests/zeekr/20261105T043319757600Z/manifest.json")
PARSED = Path("parsed/zeekr/9x-b4-verified.json")
NORMALIZED = Path("normalized/zeekr/9x-b7-v1")
MODEL = {"name": "极氪 9X", "model_info_id": "10", "model_year_code": "GMY_9X_01"}
CONFIG_URL = "https://www.zeekrlife.com/zh-cn/config"
PRODUCT_URL = "https://www.zeekrlife.com/zh-cn/zeekr9x"
STATUS_LABELS = {"standard": "标配", "optional": "选装", "unavailable": "无该配置"}


def fingerprint(data):
    return {"size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def read_page(root, baseline, kind, url):
    directory = CAPTURE / kind
    entries = {entry.path: entry for entry in baseline.files}
    files, content = {}, {}
    for name in ("receipt.json", "rendered.html", "text.txt"):
        path = (root / directory / name).resolve(strict=True)
        key = path.relative_to(root).as_posix()
        entry = entries.get(key)
        data = path.read_bytes()
        identity = fingerprint(data)
        if (
            entry is None
            or entry.file_status != "registered"
            or identity != entry.model_dump(include={"size_bytes", "sha256"})
        ):
            raise ValueError(f"File differs from the registered snapshot: {key}")
        files[name] = {"path": key, **identity}
        content[name] = data

    receipt = json.loads(content["receipt.json"])
    expected_url = f"{url}?modelInfoId=10&modelYearCode=GMY_9X_01"
    if (
        receipt["status"] != "success"
        or receipt["kind"] != kind
        or receipt["final_url"] != expected_url
        or any(receipt.get(key) != value for key, value in MODEL.items())
    ):
        raise ValueError(f"Unexpected 9X {kind} capture receipt")
    metadata = {
        "url": receipt["final_url"],
        "captured_at": receipt["finished_at"],
        "files": files,
    }
    return receipt, metadata, content


def extract_product(html, visible_text):
    soup = BeautifulSoup(html, "html.parser")
    roots = soup.select(".zeekr-001.top")
    if len(roots) != 1:
        raise ValueError("Expected one 9X product DOM container")
    root = roots[0]
    nodes = [
        node
        for node in root.find_all("div", recursive=False)
        if node.get_text(strip=True)
    ]
    lines = visible_text.splitlines()
    # shortcut: selectors describe the pinned 9X layout, review them for new page layouts.
    start = next(nodes[0].stripped_strings) if nodes else ""
    if not start or lines.count(start) != 1:
        raise ValueError("Cannot locate the start of the 9X product text")
    cursor = lines.index(start)
    blocks = []
    section = ["极氪 9X"]
    for node in nodes:
        if node.select_one(".consult-wrapper, .footer-wrapper"):
            break
        expected = "".join(node.get_text().split())
        begin = cursor
        actual = ""
        while cursor < len(lines) and len(actual) < len(expected):
            actual += "".join(lines[cursor].split())
            cursor += 1
        if actual != expected:
            raise ValueError(f"Product DOM and visible text differ at line {begin + 1}")

        heading = node.select_one(
            ".chapter-9x .title, .chapter-9x .topDesc, .chapter .title"
        )
        if "anchor" in node.get("class", []):
            if heading is None:
                raise ValueError(f"Missing product chapter title at line {begin + 1}")
            section = [heading.get_text(" ", strip=True)]
        elif heading is not None:
            section = [section[0], heading.get_text(" ", strip=True)]
        content = [
            {"line": index + 1, "text": lines[index].strip()}
            for index in range(begin, cursor)
            if lines[index].strip()
            not in {
                "",
                "预约试驾",
                "即刻预定",
                "查看 360° 外观，去选配",
                "查看 360° 内饰，去选配",
            }
        ]
        if content:
            blocks.append(
                {
                    "source": "S2",
                    "section": section,
                    "anchor": node.get("id"),
                    "lines": content,
                }
            )
    else:
        raise ValueError("Cannot locate the end of the 9X product text")

    notice = root.select_one(".consult-wrapper .extra-content")
    if notice is None:
        raise ValueError("Missing 9X product notice")
    notice_text = notice.get_text(" ", strip=True)
    notice_rows = [
        index + 1
        for index in range(cursor, len(lines))
        if lines[index].strip() == notice_text
    ]
    if len(notice_rows) != 1:
        raise ValueError("Cannot locate the 9X product notice in visible text")
    return {
        "blocks": blocks,
        "notices": [{"source": "S2", "line": notice_rows[0], "text": notice_text}],
    }


def configuration_evidence(prepared):
    snapshot, versions, definitions, facts = prepared
    columns = {version["column_index"]: version for version in versions}
    fields = {
        definition["row_index"]: definition["definition"] for definition in definitions
    }
    records = []
    for fact in facts:
        version = columns[fact["column_index"]]
        field = fields[fact["row_index"]]
        footnotes = {key: snapshot["footnotes"][key] for key in fact["footnote_ids"]}
        unit = f"（单位 {field['unit']}）" if field["unit"] else ""
        status = STATUS_LABELS.get(fact["status"])
        text = [
            " ".join(filter(None, (version["group_label"], version["label"]))),
            " / ".join(part["raw"] for part in field["section"]),
            f"{field['source_label']}：{fact['raw']}{unit}",
        ]
        if status:
            text.append(f"配置状态：{status}")
        if field["description"] and field["description"]["raw"]:
            text.append(field["description"]["raw"])
        text.extend(footnotes.values())
        review = fact["review_evidence"]
        if fact["review_status"] == "confirmed_conditions":
            conditions = review["five_seat_conditions"]
            text.append(
                "适用条件："
                + "、".join(
                    f"{option} 对应 {value} {field['unit']}"
                    for option, value in conditions.items()
                )
            )
        elif fact["pending_reason"] == "multiple_values_or_conditions":
            text.append("适用条件待核验，保留官方原值")
        records.append(
            {
                **fact,
                "source": "S1",
                "field_id": field["field_id"],
                "version": {"group": version["group_label"], "label": version["label"]},
                "unit": field["unit"],
                "footnotes": footnotes,
                "text": "\n".join(text),
            }
        )
    return {
        "snapshot_id": snapshot["id"],
        "bundle_sha256": snapshot["bundle_sha256"],
        "fields": list(fields.values()),
        "footnotes": snapshot["footnotes"],
        "notices": snapshot["notices"],
        "records": records,
    }


def prepare_corpus(data_root):
    manifest_data = (data_root / MANIFEST).read_bytes()
    baseline = Baseline.model_validate_json(manifest_data)
    if baseline.issues:
        raise ValueError("Source manifest has unresolved issues")
    raw_root = (data_root / "raw/zeekr").resolve(strict=True)
    receipt, config, config_files = read_page(raw_root, baseline, "config", CONFIG_URL)
    _, product, product_files = read_page(raw_root, baseline, "product", PRODUCT_URL)
    b4_data = (data_root / PARSED).read_bytes()
    parsed = {
        "schema_version": 1,
        "source": {
            "url": config["url"],
            "captured_at": config["captured_at"],
            "model_info_id": MODEL["model_info_id"],
            "model_year_code": MODEL["model_year_code"],
            "files": {
                name: {key: config["files"][name][key] for key in ("path", "sha256")}
                for name in ("receipt.json", "rendered.html")
            },
        },
        **parse_table(
            config_files["rendered.html"].decode("utf-8"), receipt["observed_columns"]
        ),
    }
    if json.loads(b4_data) != parsed:
        raise ValueError("B4 data differs from the verified configuration snapshot")
    inputs = {MANIFEST: manifest_data, PARSED: b4_data}
    bundle = {}
    for name in ("fields.json", "normalized.json", "review.json"):
        path = NORMALIZED / name
        inputs[path] = (data_root / path).read_bytes()
        bundle[name] = json.loads(inputs[path])
    prepared = prepare(b4_data, bundle, config_files["text.txt"])
    return {
        "schema_version": 1,
        "model": MODEL,
        "capture": CAPTURE.parent.as_posix(),
        "inputs": {path.as_posix(): fingerprint(data) for path, data in inputs.items()},
        "sources": {
            "S1": {"kind": "config", **config},
            "S2": {"kind": "product", **product},
        },
        "product": extract_product(
            product_files["rendered.html"].decode("utf-8"),
            product_files["text.txt"].decode("utf-8"),
        ),
        "configuration": configuration_evidence(prepared),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to((args.data_root / "raw").resolve()):
        parser.error("Output must be outside the raw capture directory")
    try:
        corpus = prepare_corpus(args.data_root)
        data = (json.dumps(corpus, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        stream = args.output.open("xb")
        try:
            with stream:
                stream.write(data)
        except OSError:
            args.output.unlink()
            raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(1, f"Cannot prepare corpus: {error}\n")
    print(
        f"product_blocks={len(corpus['product']['blocks'])} "
        f"configuration_records={len(corpus['configuration']['records'])} "
        f"output={args.output}"
    )


if __name__ == "__main__":
    main()
