#!/usr/bin/env python3
"""Quota-safe Figma snapshots for AI agents.

Reads a Figma file or node through the REST API, caches it locally, and reuses
it. One Tier-1 request per new target; repeat reads cost zero.

The cache is global (keyed by file key and node ID) and stays outside any
project. The monthly ledger is global per machine and defaults to the View-seat
cap of 20 Tier-1 requests.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"
API_BASE = "https://api.figma.com"
DEFAULT_BUDGET = 20
TOKEN_ENV = "FIGMA_ACCESS_TOKEN"
CACHE_ENV = "FIGMA_CACHE_HOME"
BUDGET_ENV = "FIGMA_MONTHLY_BUDGET"
API_ENV = "FIGMA_API_BASE"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BUDGET = 2
EXIT_AUTH = 3
EXIT_NOT_FOUND = 4
EXIT_TARGET = 5
EXIT_NETWORK = 6

FILE_KEY_RE = re.compile(r"^[A-Za-z0-9]{10,}$")
URL_RE = re.compile(
    r"^https?://(?:www\.)?figma\.com/"
    r"(?P<kind>design|file|proto|board|slides|make|buzz)/"
    r"(?P<key>[A-Za-z0-9]+)"
    r"(?:/[^?#]*)?"
    r"(?:\?(?P<query>[^#]*))?"
    r"(?:#.*)?$",
    re.IGNORECASE,
)
NODE_ID_RE = re.compile(r"^[A-Za-z0-9:;]+$")


class FigmaError(Exception):
    """A user-facing failure with a process exit code."""

    def __init__(self, message: str, code: int = EXIT_ERROR, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.detail = detail or {}


@dataclass(frozen=True)
class Target:
    file_key: str
    node_id: str | None
    kind: str
    url: str


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def reset_date() -> str:
    now = datetime.now(timezone.utc)
    if now.month == 12:
        return f"{now.year + 1}-01-01"
    return f"{now.year}-{now.month + 1:02d}-01"


def sanitize_id(node_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", node_id)


def image_key(node_id: str, fmt: str, scale: float) -> str:
    return f"{node_id}:{fmt}:{scale:g}"


def image_ext(fmt: str) -> str:
    return {"jpg": "jpg", "jpeg": "jpg", "png": "png", "svg": "svg", "pdf": "pdf"}[fmt]


def human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def parse_target(value: str) -> Target:
    """Parse a Figma URL or a bare file key into a Target."""

    value = value.strip()
    if not value:
        raise FigmaError("empty target", EXIT_TARGET)

    match = URL_RE.match(value)
    if match:
        kind = match.group("kind").lower()
        key = match.group("key")
        query = urllib.parse.parse_qs(match.group("query") or "")
        raw_node = (query.get("node-id") or [None])[0]
        node_id = normalize_node_id(raw_node) if raw_node else None
        return Target(file_key=key, node_id=node_id, kind=kind, url=value)

    if FILE_KEY_RE.match(value):
        return Target(file_key=value, node_id=None, kind="file", url=value)

    raise FigmaError(
        "not a Figma URL or file key. Expected "
        "https://www.figma.com/design/<key>/...?node-id=1-2 or a bare key.",
        EXIT_TARGET,
    )


def normalize_node_id(raw: str) -> str:
    node_id = raw.strip().replace("-", ":")
    if not NODE_ID_RE.match(node_id):
        raise FigmaError(f"invalid node id: {raw}", EXIT_TARGET)
    return node_id


def default_cache_home() -> Path:
    env = os.environ.get(CACHE_ENV)
    if env:
        return Path(env).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "figma-snapshot"
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "figma-snapshot"


def default_token_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "figma-snapshot" / "token"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "figma-snapshot" / "token"


def token_status() -> tuple[bool, str | None]:
    env = os.environ.get(TOKEN_ENV)
    if env and env.strip():
        return True, "env"
    path = default_token_path()
    try:
        if path.is_file() and path.read_text(encoding="utf-8").strip():
            return True, str(path)
    except OSError:
        pass
    return False, None


def read_token() -> str:
    env = os.environ.get(TOKEN_ENV)
    if env and env.strip():
        return env.strip()

    path = default_token_path()
    if not path.is_file():
        raise FigmaError(
            f"no Figma token. Set {TOKEN_ENV} or write a PAT to {path}. "
            "See references/token-setup.md.",
            EXIT_AUTH,
        )
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise FigmaError(f"cannot read token file {path}: {exc}", EXIT_AUTH) from None
    if not token:
        raise FigmaError(f"token file {path} is empty", EXIT_AUTH)

    if os.name != "nt":
        mode = path.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            print(f"warning: {path} is readable by others; run chmod 600 on it.", file=sys.stderr)
    return token


class Cache:
    """Global cache plus the monthly spend ledger."""

    def __init__(self, home: Path):
        self.home = home
        self.config_path = home / "config.json"
        self.usage_path = home / "usage.json"
        self.files_dir = home / "files"
        self.home.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)

    def _read_json(self, path: Path, default):
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return default

    def _write_json(self, path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, path)

    def budget(self) -> int:
        env = os.environ.get(BUDGET_ENV)
        if env:
            try:
                return max(0, int(env))
            except ValueError:
                pass
        config = self._read_json(self.config_path, {})
        try:
            return max(0, int(config.get("monthly_budget", DEFAULT_BUDGET)))
        except (TypeError, ValueError):
            return DEFAULT_BUDGET

    def set_budget(self, value: int) -> None:
        if value < 0:
            raise FigmaError("budget cannot be negative", EXIT_TARGET)
        config = self._read_json(self.config_path, {})
        config["monthly_budget"] = value
        self._write_json(self.config_path, config)

    def usage(self) -> dict:
        usage = self._read_json(self.usage_path, {})
        current = month_key()
        if usage.get("month") != current:
            usage = {"month": current, "spent": 0, "entries": []}
            self._write_json(self.usage_path, usage)
        usage.setdefault("spent", 0)
        usage.setdefault("entries", [])
        return usage

    def remaining(self) -> int:
        return max(0, self.budget() - int(self.usage().get("spent", 0)))

    def assert_budget(self, cost: int = 1) -> None:
        if self.remaining() < cost:
            usage = self.usage()
            raise FigmaError(
                f"monthly Figma budget exhausted ({usage['spent']}/{self.budget()}); "
                f"resets {reset_date()}. Cached targets remain readable with --offline.",
                EXIT_BUDGET,
            )

    def spend(self, kind: str, file_key: str, node_id: str | None = None, note: str | None = None) -> None:
        usage = self.usage()
        usage["spent"] = int(usage.get("spent", 0)) + 1
        usage["entries"].append(
            {
                "at": now_utc(),
                "kind": kind,
                "file_key": file_key,
                "node_id": node_id,
                "note": note,
            }
        )
        self._write_json(self.usage_path, usage)

    def record(self, spent: int) -> None:
        if spent < 0:
            raise FigmaError("recorded spend cannot be negative", EXIT_TARGET)
        usage = self.usage()
        usage["spent"] = spent
        usage["entries"].append(
            {"at": now_utc(), "kind": "reconcile", "file_key": None, "node_id": None, "note": spent}
        )
        self._write_json(self.usage_path, usage)

    def file_dir(self, file_key: str) -> Path:
        return self.files_dir / file_key

    def manifest_path(self, file_key: str) -> Path:
        return self.file_dir(file_key) / "manifest.json"

    def manifest(self, file_key: str) -> dict:
        return self._read_json(self.manifest_path(file_key), {})

    def update_manifest(
        self,
        file_key: str,
        *,
        kind: str,
        version: str | None,
        name: str | None = None,
        role: str | None = None,
        editor_type: str | None = None,
        last_modified: str | None = None,
        node_id: str | None = None,
        fmt: str | None = None,
        scale: float | None = None,
    ) -> dict:
        manifest = self.manifest(file_key)
        manifest["file_key"] = file_key
        if name:
            manifest["name"] = name
        if role:
            manifest["role"] = role
        if editor_type:
            manifest["editor_type"] = editor_type
        if last_modified:
            manifest["last_modified"] = last_modified
        if version:
            manifest["version"] = version
        manifest["updated_at"] = now_utc()
        entry = {"version": version, "fetched_at": now_utc()}
        if kind == "index":
            manifest["index"] = entry
        elif kind == "node":
            manifest.setdefault("nodes", {})[node_id] = entry
        elif kind == "image":
            manifest.setdefault("images", {})[image_key(node_id, fmt, scale)] = entry
        self._write_json(self.manifest_path(file_key), manifest)
        return manifest

    def entry_version(
        self,
        manifest: dict,
        kind: str,
        node_id: str | None = None,
        fmt: str | None = None,
        scale: float | None = None,
    ) -> str | None:
        if kind == "index":
            return (manifest.get("index") or {}).get("version")
        if kind == "node":
            return ((manifest.get("nodes") or {}).get(node_id) or {}).get("version")
        if kind == "image":
            return ((manifest.get("images") or {}).get(image_key(node_id, fmt, scale)) or {}).get("version")
        return None

    def index_path(self, file_key: str) -> Path:
        return self.file_dir(file_key) / "index.json"

    def node_path(self, file_key: str, node_id: str) -> Path:
        return self.file_dir(file_key) / "nodes" / f"{sanitize_id(node_id)}.json"

    def image_path(self, file_key: str, node_id: str, fmt: str, scale: float) -> Path:
        return self.file_dir(file_key) / "images" / f"{sanitize_id(node_id)}@{scale:g}x.{image_ext(fmt)}"

    def read_json_file(self, path: Path) -> dict:
        data = self._read_json(path, None)
        if data is None:
            raise FigmaError(f"cache file is missing or unreadable: {path}", EXIT_ERROR)
        return data

    def write_json_file(self, path: Path, data: dict) -> None:
        self._write_json(path, data)

    def write_bytes_file(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)

    def size(self) -> int:
        return sum(path.stat().st_size for path in self.home.rglob("*") if path.is_file())

    def manifests(self) -> list[dict]:
        result = []
        if not self.files_dir.exists():
            return result
        for directory in sorted(self.files_dir.iterdir()):
            if directory.is_dir():
                manifest = self._read_json(directory / "manifest.json", {})
                if manifest:
                    result.append(manifest)
        return result

    def prune(self, days: int) -> tuple[list[str], int]:
        if days <= 0:
            raise FigmaError("--days must be positive", EXIT_TARGET)
        cutoff = time.time() - days * 86400
        removed: list[str] = []
        freed = 0
        for directory in sorted(self.files_dir.iterdir()) if self.files_dir.exists() else []:
            if not directory.is_dir():
                continue
            files = [path for path in directory.rglob("*") if path.is_file()]
            latest = max((path.stat().st_mtime for path in files), default=0)
            if latest < cutoff:
                freed += sum(path.stat().st_size for path in files)
                shutil.rmtree(directory)
                removed.append(directory.name)
        return removed, freed


class FigmaClient:
    def __init__(self, token: str, api_base: str | None = None, timeout: float = 30.0):
        self.token = token
        self.api_base = (api_base or os.environ.get(API_ENV) or API_BASE).rstrip("/")
        self.timeout = timeout

    def _request(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.api_base}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={
                "X-Figma-Token": self.token,
                "User-Agent": f"figma-snapshot/{VERSION}",
            },
        )

        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    payload = {"err": body[:500]}
                status = exc.code
                headers = {key: value for key, value in exc.headers.items()}
                if status in (401, 403):
                    code = EXIT_AUTH
                elif status == 404:
                    code = EXIT_NOT_FOUND
                elif status == 400:
                    code = EXIT_TARGET
                elif status == 429 or 500 <= status < 600:
                    code = EXIT_NETWORK
                else:
                    code = EXIT_ERROR
                message = payload.get("err") or payload.get("message") or f"HTTP {status}"
                if status == 429:
                    retry = headers.get("Retry-After")
                    message = f"Figma rate limit hit{f'; retry after {retry}s' if retry else ''}."
                raise FigmaError(message, code, {"status": status, "headers": headers, "body": payload}) from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt == 2:
                    raise FigmaError(f"network error: {exc}", EXIT_NETWORK) from None
                time.sleep(0.5)

        raise FigmaError("network error", EXIT_NETWORK)

    def meta(self, file_key: str) -> dict:
        return self._request(f"/v1/files/{file_key}/meta").get("file") or {}

    def file_index(self, file_key: str) -> dict:
        return self._request(f"/v1/files/{file_key}", {"depth": 2})

    def file_nodes(self, file_key: str, node_id: str) -> dict:
        return self._request(f"/v1/files/{file_key}/nodes", {"ids": node_id})

    def image_urls(self, file_key: str, node_id: str, fmt: str, scale: float) -> dict:
        return self._request(
            f"/v1/images/{file_key}",
            {"ids": node_id, "format": fmt, "scale": scale},
        )

    def download(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": f"figma-snapshot/{VERSION}"})
        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:
                raise FigmaError(f"image download failed: HTTP {exc.code}", EXIT_NETWORK) from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt == 2:
                    raise FigmaError(f"image download failed: {exc}", EXIT_NETWORK) from None
                time.sleep(0.5)
        raise FigmaError("image download failed", EXIT_NETWORK)

    def whoami(self) -> dict:
        return self._request("/v1/me")


class SnapshotService:
    def __init__(
        self,
        cache: Cache,
        *,
        token: str | None = None,
        timeout: float = 30.0,
        offline: bool = False,
        dry_run: bool = False,
        force: bool = False,
    ):
        self.cache = cache
        self.token = token
        self.timeout = timeout
        self.offline = offline
        self.dry_run = dry_run
        self.force = force
        self._client: FigmaClient | None = None

    def client(self) -> FigmaClient:
        if self._client is None:
            self._client = FigmaClient(self.token or read_token(), timeout=self.timeout)
        return self._client

    def _check_flags(self) -> None:
        if self.offline and self.force:
            raise FigmaError("--offline and --force cannot be combined", EXIT_TARGET)
        if self.offline and self.dry_run:
            raise FigmaError("--offline and --dry-run cannot be combined", EXIT_TARGET)

    def _meta(self, file_key: str) -> dict:
        try:
            return self.client().meta(file_key)
        except FigmaError as exc:
            if exc.code == EXIT_AUTH:
                raise FigmaError(
                    f"{exc.message}. Cache freshness needs file_metadata:read; "
                    "use --offline to read the cached copy.",
                    exc.code,
                    exc.detail,
                ) from None
            raise

    def _result(self, action: str, target: Target, *, hit: bool, spent: int, path: Path | None, data: dict | None, summary: dict) -> dict:
        return {
            "action": action,
            "file_key": target.file_key,
            "node_id": target.node_id,
            "hit": hit,
            "spent": spent,
            "dry_run": self.dry_run,
            "path": str(path) if path else None,
            "data": data,
            "summary": summary,
            "budget": self.cache.budget(),
            "remaining": self.cache.remaining(),
            "resets": reset_date(),
        }

    def index(self, target: Target) -> dict:
        self._check_flags()
        path = self.cache.index_path(target.file_key)
        manifest = self.cache.manifest(target.file_key)

        if self.offline:
            if path.is_file():
                data = self.cache.read_json_file(path)
                return self._result("index", target, hit=True, spent=0, path=path, data=data, summary=summarize_index(data))
            raise FigmaError("target is not cached and --offline was given", EXIT_TARGET)

        cached_version = self.cache.entry_version(manifest, "index")
        if not self.force and path.is_file() and cached_version:
            if self._meta(target.file_key).get("version") == cached_version:
                data = self.cache.read_json_file(path)
                return self._result("index", target, hit=True, spent=0, path=path, data=data, summary=summarize_index(data))

        if self.dry_run:
            return self._result("index", target, hit=False, spent=1, path=None, data=None, summary={})

        self.cache.assert_budget()
        data = self.client().file_index(target.file_key)
        if data.get("err"):
            raise FigmaError(str(data["err"]), EXIT_ERROR)
        self.cache.write_json_file(path, data)
        version = data.get("version") or self._meta(target.file_key).get("version")
        self.cache.update_manifest(
            target.file_key,
            kind="index",
            version=version,
            name=data.get("name"),
            role=data.get("role"),
            editor_type=data.get("editorType"),
            last_modified=data.get("lastModified"),
        )
        self.cache.spend("index", target.file_key)
        return self._result("index", target, hit=False, spent=1, path=path, data=data, summary=summarize_index(data))

    def node(self, target: Target) -> dict:
        self._check_flags()
        if not target.node_id:
            raise FigmaError(
                "this command needs a node-id link. Add ?node-id=1-2 to the URL, "
                "or run `index` first and pass a frame link.",
                EXIT_TARGET,
            )
        path = self.cache.node_path(target.file_key, target.node_id)
        manifest = self.cache.manifest(target.file_key)

        if self.offline:
            if path.is_file():
                data = self.cache.read_json_file(path)
                return self._result("node", target, hit=True, spent=0, path=path, data=data, summary=summarize_node(data, target.node_id))
            raise FigmaError("target is not cached and --offline was given", EXIT_TARGET)

        cached_version = self.cache.entry_version(manifest, "node", node_id=target.node_id)
        if not self.force and path.is_file() and cached_version:
            if self._meta(target.file_key).get("version") == cached_version:
                data = self.cache.read_json_file(path)
                return self._result("node", target, hit=True, spent=0, path=path, data=data, summary=summarize_node(data, target.node_id))

        if self.dry_run:
            return self._result("node", target, hit=False, spent=1, path=None, data=None, summary={})

        self.cache.assert_budget()
        data = self.client().file_nodes(target.file_key, target.node_id)
        if data.get("err"):
            raise FigmaError(str(data["err"]), EXIT_ERROR)
        entry = (data.get("nodes") or {}).get(target.node_id)
        if entry is None:
            raise FigmaError(
                f"node {target.node_id} was not found in file {target.file_key}",
                EXIT_NOT_FOUND,
            )
        self.cache.write_json_file(path, data)
        version = data.get("version") or self._meta(target.file_key).get("version")
        self.cache.update_manifest(
            target.file_key,
            kind="node",
            version=version,
            name=data.get("name"),
            role=data.get("role"),
            editor_type=data.get("editorType"),
            last_modified=data.get("lastModified"),
            node_id=target.node_id,
        )
        self.cache.spend("node", target.file_key, target.node_id)
        return self._result("node", target, hit=False, spent=1, path=path, data=data, summary=summarize_node(data, target.node_id))

    def render(self, target: Target, fmt: str = "png", scale: float = 1.0) -> dict:
        self._check_flags()
        if not target.node_id:
            raise FigmaError("this command needs a node-id link", EXIT_TARGET)
        fmt = fmt.lower()
        if fmt == "jpeg":
            fmt = "jpg"
        if fmt not in ("png", "jpg", "svg", "pdf"):
            raise FigmaError("--format must be png, jpg, svg, or pdf", EXIT_TARGET)
        if not 0.01 <= scale <= 4:
            raise FigmaError("--scale must be between 0.01 and 4", EXIT_TARGET)

        path = self.cache.image_path(target.file_key, target.node_id, fmt, scale)
        manifest = self.cache.manifest(target.file_key)

        if self.offline:
            if path.is_file():
                data = {"format": fmt, "scale": scale}
                return self._result("image", target, hit=True, spent=0, path=path, data=data, summary={})
            raise FigmaError("image is not cached and --offline was given", EXIT_TARGET)

        cached_version = self.cache.entry_version(manifest, "image", node_id=target.node_id, fmt=fmt, scale=scale)
        meta = self._meta(target.file_key)
        if not self.force and path.is_file() and cached_version and meta.get("version") == cached_version:
            return self._result("image", target, hit=True, spent=0, path=path, data={"format": fmt, "scale": scale}, summary={})

        if self.dry_run:
            return self._result("image", target, hit=False, spent=1, path=None, data=None, summary={})

        self.cache.assert_budget()
        payload = self.client().image_urls(target.file_key, target.node_id, fmt, scale)
        if payload.get("err"):
            raise FigmaError(str(payload["err"]), EXIT_ERROR)
        url = (payload.get("images") or {}).get(target.node_id)
        if not url:
            raise FigmaError(f"Figma returned no render for node {target.node_id}", EXIT_NOT_FOUND)
        image = self.client().download(url)
        self.cache.write_bytes_file(path, image)
        self.cache.update_manifest(
            target.file_key,
            kind="image",
            version=meta.get("version"),
            name=meta.get("name"),
            role=meta.get("role"),
            editor_type=meta.get("editorType"),
            last_modified=meta.get("last_touched_at"),
            node_id=target.node_id,
            fmt=fmt,
            scale=scale,
        )
        self.cache.spend("image", target.file_key, target.node_id)
        return self._result("image", target, hit=False, spent=1, path=path, data={"format": fmt, "scale": scale}, summary={})


def walk(node: dict, limit: int = 5000):
    stack = [node]
    seen = 0
    while stack and seen < limit:
        current = stack.pop()
        seen += 1
        yield current
        stack.extend(current.get("children") or [])


def summarize_index(data: dict) -> dict:
    pages = []
    for page in (data.get("document") or {}).get("children") or []:
        pages.append(
            {
                "id": page.get("id"),
                "name": page.get("name"),
                "top_level": len(page.get("children") or []),
            }
        )
    pages.sort(key=lambda page: page["top_level"], reverse=True)
    return {
        "name": data.get("name"),
        "role": data.get("role"),
        "version": data.get("version"),
        "last_modified": data.get("lastModified"),
        "pages": pages,
        "total_top_level": sum(page["top_level"] for page in pages),
        "components": len(data.get("components") or {}),
        "component_sets": len(data.get("componentSets") or {}),
        "styles": len(data.get("styles") or {}),
    }


def summarize_node(data: dict, node_id: str) -> dict:
    entry = (data.get("nodes") or {}).get(node_id) or {}
    document = entry.get("document") or {}
    children = document.get("children") or []
    texts = []
    for node in walk(document):
        if node.get("type") == "TEXT" and node.get("characters"):
            texts.append(
                {
                    "id": node.get("id"),
                    "name": node.get("name"),
                    "characters": node["characters"][:120],
                }
            )
            if len(texts) >= 5:
                break
    return {
        "id": document.get("id"),
        "name": document.get("name"),
        "type": document.get("type"),
        "bbox": document.get("absoluteBoundingBox"),
        "child_count": len(children),
        "children": [
            {"id": child.get("id"), "name": child.get("name"), "type": child.get("type")}
            for child in children[:12]
        ],
        "texts": texts,
        "components": len(entry.get("components") or {}),
        "styles": len(entry.get("styles") or {}),
        "version": data.get("version"),
    }


def print_budget(cache: Cache) -> None:
    usage = cache.usage()
    print(
        f"Spent: {usage['spent']} / {cache.budget()} · "
        f"{cache.remaining()} left · resets {reset_date()}"
    )


def print_result(result: dict) -> None:
    action = result["action"]
    if result["dry_run"]:
        print(f"Would spend {result['spent']} request(s) on {action}; no network call made.")
        print(f"Remaining: {result['remaining']} / {result['budget']} · resets {result['resets']}")
        return

    if result["hit"]:
        print(f"Cache hit ({action}): {result['path']}")
    else:
        print(f"Snapshot ({action}): {result['path']}")

    summary = result.get("summary") or {}
    if action == "index" and summary:
        print(
            f"File: {summary.get('name')} ({summary.get('role')}, v{str(summary.get('version'))[:12]})"
        )
        print(
            f"Pages: {len(summary.get('pages') or [])} · "
            f"top-level: {summary.get('total_top_level')} · "
            f"components: {summary.get('components')} "
            f"({summary.get('component_sets')} sets) · "
            f"styles: {summary.get('styles')}"
        )
        for page in (summary.get("pages") or [])[:8]:
            print(f"  {page['name'][:40]:<42} {page['top_level']:>5}")
    elif action == "node" and summary:
        bbox = summary.get("bbox") or {}
        size = ""
        if bbox:
            size = f" · {bbox.get('width', 0):g}×{bbox.get('height', 0):g} at ({bbox.get('x', 0):g},{bbox.get('y', 0):g})"
        print(f"Node: {summary.get('name')} ({summary.get('type')} {summary.get('id')}){size}")
        print(f"Children: {summary.get('child_count')} · text: {len(summary.get('texts') or [])}")
        for child in summary.get("children") or []:
            print(f"  {child['id']:<12} {child['type']:<12} {child['name'][:48]}")
    elif action == "image" and result.get("path"):
        fmt = (result.get("data") or {}).get("format", "png")
        size = Path(result["path"]).stat().st_size
        print(f"Image: {fmt} · {human_bytes(size)}")

    print(f"Remaining: {result['remaining']} / {result['budget']} · resets {result['resets']}")


def cmd_status(args, cache: Cache) -> dict:
    present, source = token_status()
    manifests = cache.manifests()
    data = {
        "ok": True,
        "cache_home": str(cache.home),
        "cache_size": cache.size(),
        "files_cached": len(manifests),
        "token_present": present,
        "token_source": source,
        "budget": cache.budget(),
        "spent": cache.usage()["spent"],
        "remaining": cache.remaining(),
        "resets": reset_date(),
        "files": [
            {
                "file_key": manifest.get("file_key"),
                "name": manifest.get("name"),
                "role": manifest.get("role"),
                "version": manifest.get("version"),
                "indexed_at": (manifest.get("index") or {}).get("fetched_at"),
            }
            for manifest in manifests[:20]
        ],
    }
    if args.whoami:
        if not present:
            raise FigmaError(f"no Figma token. Set {TOKEN_ENV} or write {default_token_path()}.", EXIT_AUTH)
        data["account"] = FigmaClient(read_token(), timeout=args.timeout).whoami()

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return data

    print(f"Cache: {data['cache_home']} ({human_bytes(data['cache_size'])}, {data['files_cached']} files)")
    if present:
        print(f"Token: present ({source})")
    else:
        print(f"Token: missing; set {TOKEN_ENV} or write {default_token_path()}")
    print(f"Budget: {data['spent']} / {data['budget']} spent · {data['remaining']} left · resets {data['resets']}")
    for manifest in data["files"]:
        print(
            f"  {str(manifest['file_key'])[:24]:<24} "
            f"{str(manifest.get('name'))[:28]:<28} "
            f"v{str(manifest.get('version'))[:10]} "
            f"{manifest.get('indexed_at') or ''}"
        )
    if "account" in data:
        account = data["account"]
        print(f"Account: {account.get('handle')} <{account.get('email')}>")
    return data


def cmd_budget(args, cache: Cache) -> dict:
    if args.set is not None and args.record is not None:
        raise FigmaError("use --set or --record, not both", EXIT_TARGET)
    if args.set is not None:
        cache.set_budget(args.set)
    if args.record is not None:
        cache.record(args.record)
    data = {
        "ok": True,
        "budget": cache.budget(),
        "spent": cache.usage()["spent"],
        "remaining": cache.remaining(),
        "resets": reset_date(),
    }
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(f"Budget: {data['spent']} / {data['budget']} spent · {data['remaining']} left · resets {data['resets']}")
    return data


def cmd_prune(args, cache: Cache) -> dict:
    removed, freed = cache.prune(args.days)
    data = {"ok": True, "removed": removed, "freed": freed, "days": args.days}
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(f"Pruned {len(removed)} file(s), freed {human_bytes(freed)} (older than {args.days} days).")
        for file_key in removed:
            print(f"  {file_key}")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="figma-snapshot",
        description="Quota-safe Figma snapshots: one request per new target, zero on repeat.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--cache-home", type=Path, default=None, help="cache home (default: ~/.cache/figma-snapshot)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")

    sub = parser.add_subparsers(dest="command", required=True)

    resolve = sub.add_parser("resolve", help="parse a Figma URL without network")
    resolve.add_argument("target")

    status = sub.add_parser("status", help="token, cache, and budget")
    status.add_argument("--whoami", action="store_true", help="call /v1/me (requires current_user:read)")

    index = sub.add_parser("index", help="snapshot a file index (depth=2); costs 1 request")
    index.add_argument("target")
    index.add_argument("--force", action="store_true")
    index.add_argument("--offline", action="store_true")
    index.add_argument("--dry-run", action="store_true")

    node = sub.add_parser("node", help="snapshot one node subtree; costs 1 request")
    node.add_argument("target")
    node.add_argument("--force", action="store_true")
    node.add_argument("--offline", action="store_true")
    node.add_argument("--dry-run", action="store_true")

    render = sub.add_parser("render", help="render one node to an image; costs 1 request")
    render.add_argument("target")
    render.add_argument("--format", default="png", choices=("png", "jpg", "jpeg", "svg", "pdf"))
    render.add_argument("--scale", type=float, default=1.0)
    render.add_argument("--force", action="store_true")
    render.add_argument("--offline", action="store_true")
    render.add_argument("--dry-run", action="store_true")

    prune = sub.add_parser("prune", help="delete old snapshots")
    prune.add_argument("--days", type=int, default=30)

    budget = sub.add_parser("budget", help="show or edit the monthly cap")
    budget.add_argument("--set", type=int, default=None, help="set the monthly cap")
    budget.add_argument("--record", type=int, default=None, help="reconcile spent requests after using another machine")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cache = Cache(args.cache_home or default_cache_home())

    try:
        if args.command == "resolve":
            target = parse_target(args.target)
            data = {
                "ok": True,
                "file_key": target.file_key,
                "node_id": target.node_id,
                "kind": target.kind,
                "url": target.url,
            }
            if args.json:
                print(json.dumps(data, indent=2))
            else:
                print(f"file_key: {target.file_key}")
                print(f"node_id: {target.node_id or '(none)'}")
                print(f"kind: {target.kind}")
            return EXIT_OK

        if args.command == "status":
            cmd_status(args, cache)
            return EXIT_OK

        if args.command == "budget":
            cmd_budget(args, cache)
            return EXIT_OK

        if args.command == "prune":
            cmd_prune(args, cache)
            return EXIT_OK

        target = parse_target(args.target)
        service = SnapshotService(
            cache,
            timeout=args.timeout,
            offline=getattr(args, "offline", False),
            dry_run=getattr(args, "dry_run", False),
            force=getattr(args, "force", False),
        )

        if args.command == "index":
            result = service.index(target)
        elif args.command == "node":
            result = service.node(target)
        elif args.command == "render":
            result = service.render(target, fmt=args.format, scale=args.scale)
        else:
            raise FigmaError(f"unknown command: {args.command}", EXIT_ERROR)

        if args.json:
            payload = {
                "ok": True,
                "action": result["action"],
                "hit": result["hit"],
                "spent": result["spent"],
                "dry_run": result["dry_run"],
                "path": result["path"],
                "remaining": result["remaining"],
                "budget": result["budget"],
                "resets": result["resets"],
                "summary": result["summary"],
            }
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print_result(result)
        return EXIT_OK
    except FigmaError as exc:
        if args.json:
            print(
                json.dumps(
                    {"ok": False, "error": exc.message, "code": exc.code, "detail": exc.detail},
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print(f"error: {exc.message}", file=sys.stderr)
            detail = exc.detail or {}
            if detail.get("status") == 429:
                for header in ("X-Figma-Rate-Limit-Type", "X-Figma-Plan-Tier", "X-Figma-Upgrade-Link"):
                    if header in detail.get("headers", {}):
                        print(f"  {header}: {detail['headers'][header]}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
