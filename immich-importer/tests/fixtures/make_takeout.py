"""Build small but realistic Google Takeout zips for tests and the local dev stack.

Each photo is a real, unique JPEG (so Immich accepts it) with a Takeout-style JSON sidecar.
Run directly to write a sample export:  python tests/fixtures/make_takeout.py OUT_DIR
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

EXPORT_ID = "takeout-20261125T120000Z"


@dataclass
class Item:
    folder: str  # e.g. "Photos from 2021"
    name: str  # e.g. "IMG_0001.jpg"
    zip_index: int = 1  # which part holds the media file
    sidecar_zip_index: int | None = None  # defaults to zip_index
    trashed: bool = False
    seed: int = 0


def jpeg_bytes(seed: int) -> bytes:
    color = ((seed * 67) % 256, (seed * 131) % 256, (seed * 199) % 256)
    img = Image.new("RGB", (16, 16), color)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90, comment=f"takeout2immich-fixture-{seed}".encode())
    return buf.getvalue()


def sidecar(item: Item, ts: int) -> bytes:
    meta = {
        "title": item.name,
        "photoTakenTime": {"timestamp": str(ts), "formatted": ""},
        "creationTime": {"timestamp": str(ts), "formatted": ""},
        "geoData": {"latitude": 0.0, "longitude": 0.0, "altitude": 0.0},
        "url": "https://photos.google.com/fake",
    }
    if item.trashed:
        meta["trashed"] = True
    return json.dumps(meta).encode()


def build_takeout(out_dir: Path, items: list[Item], export_id: str = EXPORT_ID) -> dict[str, str]:
    """Write the zips; return {"<folder>/<name>": sha1} for every media item."""
    out_dir.mkdir(parents=True, exist_ok=True)
    zips: dict[int, zipfile.ZipFile] = {}

    def zf(i: int) -> zipfile.ZipFile:
        if i not in zips:
            zips[i] = zipfile.ZipFile(out_dir / f"{export_id}-{i:03d}.zip", "w", zipfile.ZIP_STORED)
        return zips[i]

    hashes = {}
    for n, item in enumerate(items):
        data = jpeg_bytes(item.seed or n + 1)
        base = f"Takeout/Google Photos/{item.folder}"
        zf(item.zip_index).writestr(f"{base}/{item.name}", data)
        zf(item.sidecar_zip_index or item.zip_index).writestr(
            f"{base}/{item.name}.supplemental-metadata.json", sidecar(item, 1_600_000_000 + n * 86_400)
        )
        hashes[f"{item.folder}/{item.name}"] = hashlib.sha1(data).hexdigest()
    zf(1).writestr("Takeout/archive_browser.html", b"<html></html>")
    for z in zips.values():
        z.close()
    return hashes


def sample_items() -> list[Item]:
    return [
        Item("Photos from 2021", "IMG_0001.jpg", zip_index=1),
        Item("Photos from 2021", "IMG_0002.jpg", zip_index=1),
        Item("Photos from 2022", "IMG_0003.jpg", zip_index=2, sidecar_zip_index=1),
        Item("Photos from 2022", "IMG_0004.jpg", zip_index=2),
        Item("Photos from 2023", "IMG_0005.jpg", zip_index=2, trashed=True),
    ]


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "sample-takeout")
    build_takeout(target, sample_items())
    print(f"Wrote sample export to {target}")
