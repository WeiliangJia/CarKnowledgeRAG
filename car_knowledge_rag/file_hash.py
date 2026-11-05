"""Read-only fingerprints for completed source files."""

import hashlib
from pathlib import Path

DEFAULT_CHUNK_SIZE = 1024 * 1024


def _fingerprint(path: Path, chunk_size: int) -> tuple[int, str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def sha256_file(path: Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """Hash file bytes in bounded chunks without changing the file."""
    return _fingerprint(path, chunk_size)[1]


def register_file(
    path: Path, *, root: Path, chunk_size: int = DEFAULT_CHUNK_SIZE
) -> dict[str, str | int]:
    """Return a root-relative identity for a file inside the supplied root."""
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    resolved = (root / path).resolve(strict=True)
    relative = resolved.relative_to(root)
    size, digest = _fingerprint(resolved, chunk_size)
    return {"path": relative.as_posix(), "size_bytes": size, "sha256": digest}
