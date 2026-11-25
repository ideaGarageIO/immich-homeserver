"""Inventory the media inside Takeout zips: name, SHA-1, and Google's "trashed" flag.

Sidecar matching is deliberately simple: a media file is linked to the JSON sidecar in the same
folder whose `title` equals the media file name. It is only used to recognise items that Google
marks as trashed (which the importer skips by default). Anything that cannot be matched is
treated as a normal item, so mistakes here make validation stricter, never looser.
"""

from __future__ import annotations

import json
import posixpath
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass

from takeout2immich.util import hash_stream

MEDIA_EXTENSIONS = {
    # images
    ".jpg", ".jpeg", ".jpe", ".png", ".gif", ".heic", ".heif", ".webp", ".avif", ".jxl",
    ".tif", ".tiff", ".bmp",
    # raw
    ".dng", ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".raf", ".orf",
    ".rw2", ".pef", ".srw", ".raw", ".3fr", ".erf", ".kdc", ".mrw", ".x3f", ".iiq",
    # video
    ".mp4", ".m4v", ".mov", ".qt", ".3gp", ".3g2", ".avi", ".mkv", ".mts", ".m2ts", ".ts",
    ".webm", ".mpg", ".mpeg", ".wmv", ".flv", ".insv", ".mp", ".vob",
}


@dataclass(frozen=True)
class MediaEntry:
    zip: str
    entry: str
    sha1: str
    trashed: bool = False

    @property
    def id(self) -> str:
        return f"{posixpath.basename(self.zip)}:{self.entry}"


def is_media(name: str) -> bool:
    return posixpath.splitext(name)[1].lower() in MEDIA_EXTENSIONS


def _trashed_titles(zf: zipfile.ZipFile) -> dict[str, set[str]]:
    """folder -> set of titles that Google marks as trashed."""
    out: dict[str, set[str]] = {}
    for info in zf.infolist():
        if info.is_dir() or not info.filename.lower().endswith(".json"):
            continue
        try:
            with zf.open(info) as fh:
                meta = json.load(fh)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        if isinstance(meta, dict) and meta.get("trashed") is True and meta.get("title"):
            out.setdefault(posixpath.dirname(info.filename), set()).add(meta["title"])
    return out


def inventory(zip_paths: list[str]) -> Iterator[MediaEntry]:
    """Yield every media entry across all zips of an export set.

    Trashed flags are collected across all zips first, since a sidecar may sit in another part.
    """
    trashed: dict[str, set[str]] = {}
    for zp in zip_paths:
        with zipfile.ZipFile(zp) as zf:
            for folder, titles in _trashed_titles(zf).items():
                trashed.setdefault(folder, set()).update(titles)

    for zp in zip_paths:
        with zipfile.ZipFile(zp) as zf:
            for info in zf.infolist():
                if info.is_dir() or not is_media(info.filename):
                    continue
                with zf.open(info) as fh:
                    sha1 = hash_stream(fh, "sha1")
                folder = posixpath.dirname(info.filename)
                name = posixpath.basename(info.filename)
                yield MediaEntry(
                    zip=zp,
                    entry=info.filename,
                    sha1=sha1,
                    trashed=name in trashed.get(folder, set()),
                )
