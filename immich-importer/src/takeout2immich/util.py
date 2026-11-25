"""Small shared helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO

CHUNK = 4 * 1024 * 1024


def hash_stream(fh: BinaryIO, algo: str) -> str:
    h = hashlib.new(algo)
    while chunk := fh.read(CHUNK):
        h.update(chunk)
    return h.hexdigest()


def hash_file(path: Path, algo: str) -> str:
    with open(path, "rb") as fh:
        return hash_stream(fh, algo)


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
