"""Compare local snapshot files with a saved B3.2 manifest."""

import argparse
import json
from collections import Counter
from pathlib import Path, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from car_knowledge_rag.file_hash import register_file


class FileEntry(BaseModel):
    path: str
    file_status: Literal["registered", "missing", "unreadable_or_unsafe"]
    size_bytes: int | None = Field(default=None, ge=0, strict=True)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_entry(self):
        if any(
            not part or part.endswith((".", " ")) or PureWindowsPath(part).is_reserved()
            for part in self.path.split("/")
        ) or any(character in self.path for character in '\\:<>"|?*\0'):
            raise ValueError("Expected a portable relative file path")
        if self.file_status == "registered" and (
            self.size_bytes is None or self.sha256 is None
        ):
            raise ValueError("Registered file requires size and SHA-256")
        return self


class Baseline(BaseModel):
    schema_version: Literal[1]
    path_base: Literal["supplied_raw_root"]
    files: list[FileEntry] = Field(min_length=1)
    issues: list[dict]

    @model_validator(mode="after")
    def validate_paths(self):
        if len({Path(entry.path) for entry in self.files}) != len(self.files):
            raise ValueError("Duplicate file paths")
        return self


def verify(baseline: Baseline, root: Path) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    counts = Counter()
    problems = []
    for entry in baseline.files:
        status = "no_baseline"
        if entry.file_status == "registered":
            try:
                current = register_file(Path(entry.path), root=root)
            except FileNotFoundError:
                status = "missing"
            except (OSError, ValueError, RuntimeError):
                status = "unreadable_or_unsafe"
            else:
                status = (
                    "unchanged"
                    if (current["size_bytes"], current["sha256"])
                    == (entry.size_bytes, entry.sha256)
                    else "changed"
                )
        counts[status] += 1
        if status != "unchanged":
            problems.append({"path": entry.path, "status": status})
    return {
        "ok": not problems and not baseline.issues,
        "total": len(baseline.files),
        "counts": dict(counts),
        "baseline_issue_count": len(baseline.issues),
        "problems": problems,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data/raw/zeekr",
    )
    args = parser.parse_args()
    try:
        baseline = Baseline.model_validate_json(args.manifest.read_bytes())
        report = verify(baseline, args.raw_root)
    except (OSError, ValidationError, RuntimeError) as error:
        parser.error(f"Cannot verify manifest: {type(error).__name__}")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
