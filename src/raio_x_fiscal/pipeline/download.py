"""Download of the monthly NF-e zip from the Portal da Transparencia (idempotent)."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import requests

from raio_x_fiscal.config import DOWNLOAD_URL, Paths, validate_month

log = logging.getLogger(__name__)

CHUNK = 1 << 20  # 1 MiB


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def manifest_path(zip_path: Path) -> Path:
    return zip_path.with_suffix(".json")


def download_month(month: str, paths: Paths, force: bool = False, timeout: int = 900) -> Path:
    """Fetch <month>_NFe.zip into data/raw, skipping when a complete file already exists.

    The portal answers with a 302 to the CGU open-data bucket; `requests` follows it. The file
    is written to a `.part` path and renamed only when complete, so a crash never leaves a
    truncated zip that looks finished. A JSON manifest (url, size, sha256, timestamp) sits
    next to the zip for traceability.
    """
    validate_month(month)
    paths.ensure()
    target = paths.raw_zip(month)
    if target.exists() and target.stat().st_size > 0 and not force:
        log.info("download %s: ja existe (%d bytes), pulando", month, target.stat().st_size)
        if not manifest_path(target).exists():
            _write_manifest(target, DOWNLOAD_URL.format(month=month))
        return target

    url = DOWNLOAD_URL.format(month=month)
    part = target.with_suffix(".zip.part")
    log.info("download %s: %s", month, url)
    with requests.get(url, stream=True, timeout=timeout, allow_redirects=True) as resp:
        resp.raise_for_status()
        expected = int(resp.headers.get("Content-Length") or 0)
        written = 0
        with part.open("wb") as fh:
            for block in resp.iter_content(CHUNK):
                fh.write(block)
                written += len(block)
    if expected and written != expected:
        part.unlink(missing_ok=True)
        raise OSError(f"download {month}: esperado {expected} bytes, recebido {written}")
    part.rename(target)
    _write_manifest(target, url)
    log.info("download %s: ok (%d bytes)", month, written)
    return target


def _write_manifest(zip_path: Path, url: str) -> None:
    info = {
        "url": url,
        "file": zip_path.name,
        "size_bytes": zip_path.stat().st_size,
        "sha256": sha256_of(zip_path),
        "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "Portal da Transparencia / CGU (dados abertos)",
    }
    manifest_path(zip_path).write_text(json.dumps(info, indent=2, ensure_ascii=False))
