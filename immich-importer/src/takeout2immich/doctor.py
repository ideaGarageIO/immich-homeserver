"""Health checks shared by `takeout2immich doctor` and the TUI Test buttons."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

import httpx

from takeout2immich.config.models import AppConfig
from takeout2immich.config.store import read_secret
from takeout2immich.domain import Event, EventType
from takeout2immich.immich import ImmichClient
from takeout2immich.sources import build_source


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def check_immich(config: AppConfig) -> list[Check]:
    out: list[Check] = []
    try:
        key = read_secret(config.immich.api_key_file)
    except FileNotFoundError as exc:
        return [Check("Immich API key", False, str(exc))]
    try:
        with ImmichClient(config.immich.url, key, timeout=15) as c:
            out.append(Check("Immich reachable", c.ping(), f"{config.immich.url} v{c.version()}"))
            me = c.me()
            out.append(Check("Immich API key", True, f"user {me.get('email', me.get('name', '?'))}"))
            # Immich answers 500 to an empty list, so probe with one dummy checksum (SHA-1 of "").
            res = c.bulk_upload_check([("doctor-probe", "da39a3ee5e6b4b0d3255bfef95601890afd80709")])
            ok = len(res) == 1 and res[0].action in ("accept", "reject")
            out.append(Check("Immich bulk-upload-check", ok, "endpoint responds" if ok else f"unexpected: {res}"))
    except httpx.HTTPStatusError as exc:
        out.append(Check("Immich API", False, f"HTTP {exc.response.status_code} on {exc.request.url.path}"))
    except httpx.HTTPError as exc:
        out.append(Check("Immich reachable", False, f"{config.immich.url}: {exc}"))
    return out


def check_staging(config: AppConfig) -> Check:
    p = config.staging.path
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return Check("Staging dir", False, f"{p}: {exc}")
    if not os.access(p, os.W_OK):
        return Check("Staging dir", False, f"{p} is not writable")
    free_gb = shutil.disk_usage(p).free / 1024**3
    ok = free_gb > config.staging.min_free_gb
    return Check("Staging dir", ok, f"{p}: {free_gb:.0f} GB free (reserve {config.staging.min_free_gb} GB)")


def check_source(config: AppConfig) -> Check:
    try:
        ok, detail = build_source(config.source).check()
    except Exception as exc:
        ok, detail = False, str(exc)
    return Check(f"Source ({config.source.type})", ok, detail)


def _version(cmd: list[str]) -> Check:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        line = (proc.stdout or proc.stderr).strip().splitlines()[0] if (proc.stdout or proc.stderr) else ""
        return Check(cmd[0], proc.returncode == 0, line)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(cmd[0], False, str(exc))


def check_tools(config: AppConfig) -> list[Check]:
    out = [_version([config.importer.immich_go_binary, "version"])]
    if config.source.type == "drive":
        out.append(_version([config.source.rclone_binary, "version"]))
    return out


def check_notifications(config: AppConfig, send_test: bool = False) -> list[Check]:
    from takeout2immich.notifications.base import build_notifier

    out = []
    for cfg in config.notifications:
        n = build_notifier(cfg)
        if not send_test:
            if cfg.type == "homeassistant":
                ok = cfg.token_file.exists()
                out.append(Check("Home Assistant", ok, f"token file {'found' if ok else 'missing'}"))
            continue
        try:
            n.send(Event(type=EventType.ACTION_REQUIRED, message="Test notification from takeout2immich"))
            out.append(Check(f"Notify ({n.name})", True, "test sent"))
        except Exception as exc:
            out.append(Check(f"Notify ({n.name})", False, str(exc)))
    return out


def run_all(config: AppConfig, send_test: bool = False) -> list[Check]:
    return [
        *check_immich(config),
        check_staging(config),
        check_source(config),
        *check_tools(config),
        *check_notifications(config, send_test=send_test),
    ]
