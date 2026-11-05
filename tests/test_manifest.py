import json
from pathlib import Path

import pytest

from car_knowledge_rag.manifest import build_manifest, duplicate_report, main


def save_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def make_run(root, name="run-one", status="success"):
    directory = root / name
    page_dir = directory / "10" / "config"
    page_dir.mkdir(parents=True)
    names = (
        ["response.html", "rendered.html", "text.txt"]
        if status == "success"
        else ["response.html"]
    )
    page = {
        "model_info_id": "10",
        "model_year_code": "V1",
        "kind": "config",
        "requested_url": "https://www.zeekrlife.com/zh-cn/config",
        "status": status,
        "files": names,
    }
    for filename in names:
        (page_dir / filename).write_bytes(
            b"response" if filename == "response.html" else b"same"
        )
    save_json(page_dir / "receipt.json", page)
    save_json(directory / "source-catalog.json", {"models": []})
    summary = {
        "run_id": name,
        "total": 1,
        "failed": int(status == "failed"),
        "pages": [page],
    }
    save_json(directory / "run.json", summary)
    return directory, page_dir, summary


def test_inventory_hashes_files_and_keeps_source(tmp_path):
    _, page_dir, _ = make_run(tmp_path)
    result = build_manifest(tmp_path)
    assert result["issues"] == []
    assert len(result["files"]) == 6
    assert all(not Path(entry["path"]).is_absolute() for entry in result["files"])
    assert result["pages"][0]["requested_url"].startswith("https://")
    assert (page_dir / "rendered.html").read_bytes() == b"same"
    duplicates = duplicate_report(result)
    assert duplicates["duplicate_groups"] == 1
    assert duplicates["extra_copies"] == 1
    assert duplicates["groups"][0]["paths"] == [
        "run-one/10/config/rendered.html",
        "run-one/10/config/text.txt",
    ]


def test_failed_capture_is_preserved_even_if_file_readable(tmp_path):
    make_run(tmp_path, status="failed")
    result = build_manifest(tmp_path)
    assert result["issues"] == []
    assert result["runs"][0]["failed"] == 1
    assert result["pages"][0]["capture_status"] == "failed"
    content = next(
        entry for entry in result["files"] if entry["role"] == "page_content"
    )
    assert content["file_status"] == "registered"
    assert content["capture_status"] == "failed"


def test_missing_file_is_reported_not_hashed(tmp_path):
    _, page_dir, _ = make_run(tmp_path)
    (page_dir / "rendered.html").unlink()
    result = build_manifest(tmp_path)
    missing = next(
        entry for entry in result["files"] if entry["path"].endswith("rendered.html")
    )
    assert missing["file_status"] == "missing"
    assert "sha256" not in missing
    assert any(issue["code"] == "missing_file" for issue in result["issues"])


def test_empty_success_file_is_reported(tmp_path):
    _, page_dir, _ = make_run(tmp_path)
    (page_dir / "text.txt").write_bytes(b"")
    assert any(
        issue["code"] == "empty_success_content"
        for issue in build_manifest(tmp_path)["issues"]
    )


def test_summary_and_page_disagreement_keeps_both_states(tmp_path):
    _, page_dir, summary = make_run(tmp_path)
    receipt = {**summary["pages"][0], "status": "failed"}
    save_json(page_dir / "receipt.json", receipt)
    result = build_manifest(tmp_path)
    assert result["pages"][0]["capture_status"] == "success"
    assert result["pages"][0]["page_receipt_status"] == "failed"
    assert result["pages"][0]["receipt_matches_summary"] is False
    assert any(issue["code"] == "page_receipt_mismatch" for issue in result["issues"])


def test_malformed_json_does_not_become_success(tmp_path):
    directory, _, _ = make_run(tmp_path)
    (directory / "run.json").write_text("{", encoding="utf-8")
    result = build_manifest(tmp_path)
    assert result["runs"] == []
    assert any(issue["code"] == "invalid_run_receipt" for issue in result["issues"])


def test_unreferenced_file_is_reported(tmp_path):
    directory, _, _ = make_run(tmp_path)
    (directory / "extra.txt").write_text("unexpected", encoding="utf-8")
    result = build_manifest(tmp_path)
    assert any(issue["code"] == "unreferenced_file" for issue in result["issues"])


def test_inconsistent_run_counts_are_reported(tmp_path):
    directory, _, summary = make_run(tmp_path)
    summary["total"] = 2
    save_json(directory / "run.json", summary)
    assert any(
        issue["code"] == "run_count_mismatch"
        for issue in build_manifest(tmp_path)["issues"]
    )


def test_incomplete_success_declaration_still_checks_required_files(tmp_path):
    directory, page_dir, summary = make_run(tmp_path)
    summary["pages"][0]["files"].remove("text.txt")
    save_json(directory / "run.json", summary)
    save_json(page_dir / "receipt.json", summary["pages"][0])
    result = build_manifest(tmp_path)
    assert any(
        issue["code"] == "incomplete_success_receipt" for issue in result["issues"]
    )
    assert any(entry["path"].endswith("text.txt") for entry in result["files"])


def test_path_from_receipt_cannot_escape_root(tmp_path):
    raw = tmp_path / "raw"
    directory, _, summary = make_run(raw)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    summary["pages"][0]["files"].append("../../../../outside.txt")
    save_json(directory / "run.json", summary)
    result = build_manifest(raw)
    assert any(
        issue["code"] == "unexpected_page_filename" for issue in result["issues"]
    )
    assert all("outside.txt" not in entry["path"] for entry in result["files"])
    assert outside.read_text() == "outside"


def test_empty_root_reports_no_runs(tmp_path):
    assert build_manifest(tmp_path)["issues"] == [
        {"code": "no_valid_runs", "path": "."}
    ]


def test_cli_writes_new_outputs_and_preserves_old_results(tmp_path, monkeypatch):
    raw, output = tmp_path / "raw", tmp_path / "output"
    make_run(raw)
    monkeypatch.setattr(
        "sys.argv", ["manifest", "--raw-root", str(raw), "--output-root", str(output)]
    )
    for _ in range(2):
        with pytest.raises(SystemExit) as raised:
            main()
        assert raised.value.code == 0
    assert len(list(output.glob("*/manifest.json"))) == 2
    assert len(list(output.glob("*/duplicates.json"))) == 2


def test_cli_reports_issues_with_exit_one(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    _, page_dir, _ = make_run(raw)
    (page_dir / "text.txt").unlink()
    monkeypatch.setattr(
        "sys.argv",
        ["manifest", "--raw-root", str(raw), "--output-root", str(tmp_path / "output")],
    )
    with pytest.raises(SystemExit) as raised:
        main()
    assert raised.value.code == 1


def test_cli_rejects_output_inside_raw(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    make_run(raw)
    output = raw / "manifest"
    monkeypatch.setattr(
        "sys.argv", ["manifest", "--raw-root", str(raw), "--output-root", str(output)]
    )
    with pytest.raises(SystemExit) as raised:
        main()
    assert raised.value.code == 2
    assert not output.exists()
