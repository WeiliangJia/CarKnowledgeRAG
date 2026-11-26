"""Build text retrieval chunks from the D1–D3 corpus."""

import argparse
import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

DEFAULT_MAX_CHARS = 600


def product_blocks(blocks):
    grouped = []
    for block in blocks:
        lines = block["lines"]
        if not lines:
            raise ValueError("Product block has no lines")
        is_note = all(line["text"].startswith(("*", "＊")) for line in lines)
        # The 9X DOM sometimes renders a feature's note as a separate block.
        if is_note and grouped and grouped[-1]["section"] == block["section"]:
            grouped[-1]["lines"].extend(lines)
        else:
            grouped.append({**block, "lines": list(lines)})
    return grouped


def chunks_from_corpus(corpus, max_chars=DEFAULT_MAX_CHARS):
    if corpus["schema_version"] != 1:
        raise ValueError("Expected a version 1 D1–D3 corpus")
    if max_chars < 1:
        raise ValueError("Character limit must be positive")

    model = corpus["model"]
    config = corpus["configuration"]
    fields = {field["field_id"]: field for field in config["fields"]}
    sources = corpus["sources"]
    chunks = []

    def add(source_id, kind, text, locator, **metadata):
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Empty evidence at {source_id} {locator}")
        if len(text) > max_chars:
            raise ValueError(
                f"Evidence at {source_id} {locator} has {len(text)} characters "
                f"(limit {max_chars}); increase the limit or split at a source boundary"
            )
        source = sources[source_id]
        item = {
            "kind": kind,
            "text": text,
            "source": source_id,
            "source_url": source["url"],
            "source_text_sha256": source["files"]["text.txt"]["sha256"],
            "captured_at": source["captured_at"],
            "capture": corpus["capture"],
            "model_info_id": model["model_info_id"],
            "model_year_code": model["model_year_code"],
            "locator": locator,
            **metadata,
        }
        identity = json.dumps(
            item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        chunks.append({"id": str(uuid5(NAMESPACE_URL, identity)), **item})

    for block in product_blocks(corpus["product"]["blocks"]):
        lines = block["lines"]
        section = block["section"]
        heading = " / ".join(
            [model["name"], *(part for part in section if part != model["name"])]
        )
        add(
            "S2",
            "product",
            "\n".join([heading, *(line["text"] for line in lines)]),
            {"lines": [line["line"] for line in lines], "anchor": block["anchor"]},
            section=section,
        )

    for notice in corpus["product"]["notices"]:
        add(
            "S2",
            "product_notice",
            f"{model['name']}\n{notice['text']}",
            {"lines": [notice["line"]]},
        )

    for record in config["records"]:
        field = fields[record["field_id"]]
        if (
            field["row_index"] != record["row_index"]
            or config["snapshot_id"] != record["snapshot_id"]
        ):
            raise ValueError(
                "Configuration evidence does not match its field or snapshot"
            )
        add(
            "S1",
            "configuration",
            f"{model['name']}\n{record['text']}",
            {"row_index": record["row_index"], "column_index": record["column_index"]},
            snapshot_id=config["snapshot_id"],
            field_id=record["field_id"],
            test_cycle=field["test_cycle"],
            range_type=field["range_type"],
            version=record["version"],
            raw=record["raw"],
            number=record["number"],
            unit=record["unit"],
            status=record["status"],
            qualifier=record["qualifier"],
            footnote_ids=record["footnote_ids"],
            footnotes=record["footnotes"],
            pending_reason=record["pending_reason"],
            review_status=record["review_status"],
            review_evidence=record["review_evidence"],
        )
    for index, notice in enumerate(config["notices"], 1):
        add(
            "S1",
            "configuration_notice",
            f"{model['name']}\n{notice}",
            {"notice_index": index},
            snapshot_id=config["snapshot_id"],
        )

    if not chunks:
        raise ValueError("Corpus has no evidence to chunk")
    locators = {
        (chunk["source"], json.dumps(chunk["locator"], sort_keys=True))
        for chunk in chunks
    }
    if len(locators) != len(chunks):
        raise ValueError("Duplicate source locators in corpus")
    return chunks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path, help="D1–D3 JSON corpus")
    parser.add_argument(
        "--output", required=True, type=Path, help="New JSON output file"
    )
    parser.add_argument("--max-chars", default=DEFAULT_MAX_CHARS, type=int)
    args = parser.parse_args()
    try:
        data = args.corpus.read_bytes()
        chunks = chunks_from_corpus(json.loads(data), args.max_chars)
        payload = {
            "schema_version": 1,
            "corpus_sha256": hashlib.sha256(data).hexdigest(),
            "max_chars": args.max_chars,
            "chunks": chunks,
        }
        encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        stream = args.output.open("xb")
        try:
            with stream:
                stream.write(encoded)
        except OSError:
            args.output.unlink()
            raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(1, f"Cannot build chunks: {error}\n")
    print(f"chunks={len(chunks)} output={args.output}")


if __name__ == "__main__":
    main()
