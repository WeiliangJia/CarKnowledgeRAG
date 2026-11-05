"""Inventory B2 receipts and file bytes without changing source snapshots."""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from car_knowledge_rag.file_hash import register_file

ROOT = Path(__file__).resolve().parents[1]
PAGE_FILES = {"response.html", "rendered.html", "text.txt"}


class PageReceipt(BaseModel):
    model_info_id: str = Field(pattern=r"^\d+$")
    model_year_code: str
    kind: str = Field(pattern=r"^(product|config|detail-[1-9]\d*)$")
    requested_url: str
    status: Literal["success", "failed"]
    files: list[str]


class RunReceipt(BaseModel):
    run_id: str
    total: int = Field(ge=0)
    failed: int = Field(ge=0)
    pages: list[PageReceipt]


def build_manifest(root: Path) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    files, pages, runs, issues = [], [], [], []
    seen = set()

    def issue(code: str, path: Path) -> None:
        issues.append({"code": code, "path": path.as_posix()})

    def add_file(path: Path, role: str, capture_status=None, source_url=None) -> None:
        key = path.as_posix()
        if key in seen:
            return
        seen.add(key)
        entry = {
            "path": key,
            "run_id": path.parts[0],
            "role": role,
            "capture_status": capture_status,
            "source_url": source_url,
        }
        try:
            fingerprint = register_file(path, root=root)
            entry.update(
                size_bytes=fingerprint["size_bytes"],
                sha256=fingerprint["sha256"],
                file_status="registered",
            )
            if (
                role == "page_content"
                and capture_status == "success"
                and fingerprint["size_bytes"] == 0
            ):
                issue("empty_success_content", path)
        except FileNotFoundError:
            entry["file_status"] = "missing"
            issue("missing_file", path)
        except (OSError, ValueError):
            entry["file_status"] = "unreadable_or_unsafe"
            issue("unreadable_or_unsafe_file", path)
        files.append(entry)

    def read_json(path: Path):
        try:
            resolved = (root / path).resolve(strict=True)
            resolved.relative_to(root)
            return json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            issue("invalid_or_unreadable_json", path)
            return None

    for directory in sorted(root.iterdir()):
        relative = Path(directory.name)
        if not directory.is_dir() or directory.is_symlink():
            add_file(relative, "unreferenced")
            issue("unexpected_root_entry", relative)
            continue
        summary_path = relative / "run.json"
        add_file(summary_path, "run_receipt")
        add_file(relative / "source-catalog.json", "source_catalog")
        read_json(relative / "source-catalog.json")
        raw = read_json(summary_path)
        try:
            run = RunReceipt.model_validate(raw)
        except ValidationError:
            issue("invalid_run_receipt", summary_path)
            run = None
        if run is not None:
            runs.append(
                {
                    "path": summary_path.as_posix(),
                    "declared_run_id": run.run_id,
                    "total": run.total,
                    "failed": run.failed,
                    "not_attempted": raw.get("not_attempted"),
                    "fatal_error_type": raw.get("fatal_error_type"),
                }
            )
            if run.run_id != directory.name:
                issue("run_id_mismatch", summary_path)
            if run.total != len(run.pages) or run.failed != sum(
                p.status == "failed" for p in run.pages
            ):
                issue("run_count_mismatch", summary_path)
            page_paths = set()
            for index, page in enumerate(run.pages):
                page_dir = relative / page.model_info_id / page.kind
                receipt_path = page_dir / "receipt.json"
                if receipt_path.as_posix() in page_paths:
                    issue("duplicate_page_reference", receipt_path)
                    continue
                page_paths.add(receipt_path.as_posix())
                add_file(receipt_path, "page_receipt", page.status, page.requested_url)
                receipt = read_json(receipt_path)
                matches = receipt == raw["pages"][index]
                if not matches:
                    issue("page_receipt_mismatch", receipt_path)
                pages.append(
                    {
                        "run_id": directory.name,
                        "receipt_path": receipt_path.as_posix(),
                        "capture_status": page.status,
                        "page_receipt_status": receipt.get("status")
                        if isinstance(receipt, dict)
                        else None,
                        "model_info_id": page.model_info_id,
                        "model_year_code": page.model_year_code,
                        "kind": page.kind,
                        "requested_url": page.requested_url,
                        "final_url": raw["pages"][index].get("final_url"),
                        "started_at": raw["pages"][index].get("started_at"),
                        "finished_at": raw["pages"][index].get("finished_at"),
                        "receipt_matches_summary": matches,
                    }
                )
                if len(page.files) != len(set(page.files)):
                    issue("duplicate_filename", receipt_path)
                if set(page.files) - PAGE_FILES:
                    issue("unexpected_page_filename", receipt_path)
                expected = set(page.files) & PAGE_FILES
                if page.status == "success":
                    if expected != PAGE_FILES:
                        issue("incomplete_success_receipt", receipt_path)
                    expected |= PAGE_FILES
                for filename in sorted(expected):
                    add_file(
                        page_dir / filename,
                        "page_content",
                        page.status,
                        page.requested_url,
                    )
        for path in sorted(directory.rglob("*")):
            if path.is_file() or path.is_symlink():
                relative_path = path.relative_to(root)
                if relative_path.as_posix() not in seen:
                    add_file(relative_path, "unreferenced")
                    issue("unreferenced_file", relative_path)
    if not runs:
        issue("no_valid_runs", Path("."))
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "path_base": "supplied_raw_root",
        "runs": runs,
        "pages": pages,
        "files": files,
        "issues": issues,
    }


def duplicate_report(manifest: dict) -> dict:
    groups = defaultdict(list)
    for entry in manifest["files"]:
        if entry["file_status"] == "registered":
            groups[(entry["sha256"], entry["size_bytes"])].append(entry["path"])
    duplicates = [
        {"sha256": digest, "size_bytes": size, "paths": sorted(paths)}
        for (digest, size), paths in sorted(groups.items())
        if len(paths) > 1
    ]
    return {
        "comparison": "exact file bytes, all registered file roles",
        "groups": duplicates,
        "duplicate_groups": len(duplicates),
        "extra_copies": sum(len(group["paths"]) - 1 for group in duplicates),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=ROOT / "data/raw/zeekr")
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "data/manifests/zeekr"
    )
    args = parser.parse_args()
    raw_root = args.raw_root.resolve(strict=True)
    output_root = args.output_root.resolve()
    if output_root.is_relative_to(raw_root):
        parser.error("Output must be outside the raw snapshot root")
    manifest = build_manifest(raw_root)
    report = duplicate_report(manifest)
    output = output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    for name, data in [("manifest.json", manifest), ("duplicates.json", report)]:
        with (output / name).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(
        f"files={len(manifest['files'])} issues={len(manifest['issues'])} duplicate_groups={report['duplicate_groups']} output={output}"
    )
    raise SystemExit(1 if manifest["issues"] else 0)


if __name__ == "__main__":
    main()
