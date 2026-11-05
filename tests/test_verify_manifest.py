import json

import pytest
from pydantic import ValidationError

from car_knowledge_rag.file_hash import register_file
from car_knowledge_rag.verify_manifest import Baseline, main, verify


def baseline_data(root):
    files = []
    for name in ("same", "changed", "missing", "directory"):
        path = root / name
        path.write_bytes(b"abc")
        files.append({**register_file(path, root=root), "file_status": "registered"})
    return {
        "schema_version": 1,
        "path_base": "supplied_raw_root",
        "issues": [],
        "files": files,
    }


def test_detects_same_size_changes_and_missing_files(tmp_path):
    baseline = Baseline.model_validate(baseline_data(tmp_path))
    (tmp_path / "changed").write_bytes(b"abd")
    (tmp_path / "missing").unlink()
    (tmp_path / "directory").unlink()
    (tmp_path / "directory").mkdir()
    report = verify(baseline, tmp_path)
    assert report["counts"] == {
        "unchanged": 1,
        "changed": 1,
        "missing": 1,
        "unreadable_or_unsafe": 1,
    }
    assert not report["ok"]
    assert (tmp_path / "changed").read_bytes() == b"abd"


@pytest.mark.parametrize(
    "path", ["../outside", "/absolute", "C:outside", "x\\y", "NUL"]
)
def test_invalid_baseline_paths(tmp_path, path):
    data = baseline_data(tmp_path)
    data["files"][0]["path"] = path
    with pytest.raises(ValidationError):
        Baseline.model_validate(data)


def test_incomplete_baseline_is_not_clean(tmp_path):
    data = baseline_data(tmp_path)
    data["files"][0] = {"path": "same", "file_status": "missing"}
    data["issues"] = [{"code": "missing_file"}]
    report = verify(Baseline.model_validate(data), tmp_path)
    assert report["counts"]["no_baseline"] == 1
    assert report["baseline_issue_count"] == 1
    assert not report["ok"]


def test_cli_exit_codes_and_read_only_baseline(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "raw"
    raw.mkdir()
    path = tmp_path / "manifest.json"
    original = json.dumps(baseline_data(raw))
    path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv", ["verify_manifest", str(path), "--raw-root", str(raw)]
    )
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 0
    assert json.loads(capsys.readouterr().out)["counts"] == {"unchanged": 4}
    (raw / "changed").write_bytes(b"abd")
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 1
    assert path.read_text(encoding="utf-8") == original
    path.write_text("{", encoding="utf-8")
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 2
