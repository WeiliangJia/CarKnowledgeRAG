from pathlib import Path

import pytest

from car_knowledge_rag.file_hash import register_file, sha256_file

ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_known_digest_across_chunks(tmp_path):
    path = tmp_path / "sample.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == ABC_SHA256
    assert sha256_file(path, chunk_size=1) == ABC_SHA256
    assert path.read_bytes() == b"abc"


def test_empty_file_has_valid_digest(tmp_path):
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")
    assert sha256_file(path) == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert register_file(path, root=tmp_path)["size_bytes"] == 0


def test_content_not_filename_controls_digest(tmp_path):
    first, second = tmp_path / "one.bin", tmp_path / "two.bin"
    first.write_bytes(b"abc")
    second.write_bytes(b"abc")
    assert sha256_file(first) == sha256_file(second)
    second.write_bytes(b"abd")
    assert first.stat().st_size == second.stat().st_size
    assert sha256_file(first) != sha256_file(second)


def test_registration_is_relative_and_counts_bytes(tmp_path):
    path = tmp_path / "车型" / "text.txt"
    path.parent.mkdir()
    content = "极氪\r\n".encode("utf-8") + b"\x00\xff"
    path.write_bytes(content)
    record = register_file(Path("车型/text.txt"), root=tmp_path, chunk_size=3)
    assert record == {
        "path": "车型/text.txt",
        "size_bytes": len(content),
        "sha256": sha256_file(path),
    }
    assert path.read_bytes() == content


@pytest.mark.parametrize("chunk_size", [0, -1])
def test_invalid_chunk_size_is_rejected(tmp_path, chunk_size):
    path = tmp_path / "sample.bin"
    path.write_bytes(b"abc")
    with pytest.raises(ValueError, match="positive"):
        sha256_file(path, chunk_size=chunk_size)


def test_missing_file_is_not_registered(tmp_path):
    with pytest.raises(FileNotFoundError):
        register_file(Path("missing.html"), root=tmp_path)
    assert not (tmp_path / "missing.html").exists()


def test_directory_is_not_registered_as_file(tmp_path):
    with pytest.raises(OSError):
        register_file(tmp_path, root=tmp_path)


def test_root_must_be_directory(tmp_path):
    path = tmp_path / "sample.bin"
    path.write_bytes(b"abc")
    with pytest.raises(NotADirectoryError):
        register_file(path, root=path)


def test_path_outside_root_is_rejected(tmp_path):
    root = tmp_path / "snapshot"
    root.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"abc")
    for path in (outside, Path("../outside.bin")):
        with pytest.raises(ValueError):
            register_file(path, root=root)


def test_symlink_outside_root_is_rejected(tmp_path):
    root = tmp_path / "snapshot"
    root.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"abc")
    link = root / "link.bin"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symlinks is not available in this environment")
    with pytest.raises(ValueError):
        register_file(link, root=root)
