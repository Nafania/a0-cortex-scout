from __future__ import annotations

import atexit
import hashlib
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from urllib import request
from urllib.parse import urlparse

from .client import CortexScoutClient, CortexScoutError


PLUGIN_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE_VERSION = "v3.3.7"
DEFAULT_RELEASE_BASE = "https://github.com/cortex-works/cortex-scout/releases/download"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
CHECKSUMS = {
    "cortex-scout-3.3.7-linux-arm64.tar.gz": "b30f56cf0e1d15b2e3f7808ca312d525a40527d5d88ef250dbc9c3c31cb72ebb",
    "cortex-scout-3.3.7-macos-arm64.tar.gz": "0bb8045ff2158ba28be46b80318d48115d62cb3fc2e841a6f1d21197492d4550",
    "cortex-scout-3.3.7-windows-arm64.zip": "e305ff3ec57f73a773e6641c0d3656015505b470c8417e3e013edd0532e9df95",
    "cortex-scout-3.3.7-windows-x64.zip": "f55acf8be5ef824555b4f93c76333c0956885371db945179c9cfe73ab2b61a58",
}


_lock = threading.RLock()
_process: subprocess.Popen | None = None
_process_url = ""


def ensure_running(config: dict) -> None:
    base_url = str(config.get("base_url") or "http://127.0.0.1:5055").rstrip("/")
    timeout = float(config.get("timeout_seconds") or 120)
    if _healthy(base_url, timeout):
        return
    if not _bool(config.get("auto_start"), True):
        raise CortexScoutError(f"Cortex Scout is not running at {base_url}")

    parsed = urlparse(base_url)
    if parsed.hostname not in LOCAL_HOSTS:
        raise CortexScoutError(f"Cannot auto-start Cortex Scout for non-local URL {base_url}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    with _lock:
        if _healthy(base_url, timeout):
            return
        if _process and _process.poll() is None and _process_url != base_url:
            stop()
        binary = _find_binary(config)
        _start(binary, port, base_url, config)


def stop() -> None:
    global _process, _process_url
    with _lock:
        if not _process:
            return
        try:
            if _process.poll() is None:
                _process.terminate()
                try:
                    _process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _process.kill()
        finally:
            _process = None
            _process_url = ""


def _healthy(base_url: str, timeout: float) -> bool:
    try:
        data = CortexScoutClient(base_url, timeout_seconds=min(timeout, 3)).health()
        return data.get("status") == "healthy"
    except Exception:
        return False


def _find_binary(config: dict) -> Path:
    explicit = str(config.get("binary_path") or "").strip()
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return path
        raise CortexScoutError(f"Cortex Scout binary not found: {path}")

    local = _bin_dir(config) / _binary_name()
    if local.is_file():
        return local

    found = shutil.which("cortex-scout")
    if found:
        return Path(found)

    if _bool(config.get("auto_install"), True):
        return _install_binary(config)

    raise CortexScoutError(
        f"Cortex Scout binary not found. Put it at {local} or set binary_path."
    )


def _install_binary(config: dict) -> Path:
    bin_dir = _bin_dir(config)
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / _binary_name()

    version = str(config.get("release_version") or DEFAULT_RELEASE_VERSION)
    asset = str(config.get("asset_name") or "")
    if not asset:
        asset = _default_asset_name(version)

    url = str(config.get("download_url") or "")
    if not url:
        url = f"{DEFAULT_RELEASE_BASE}/{version}/{asset}"

    expected_sha = str(config.get("binary_sha256") or CHECKSUMS.get(asset, ""))
    if not expected_sha:
        raise CortexScoutError(
            f"No checksum configured for Cortex Scout asset {asset}; set binary_sha256."
        )

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / asset
        _download(url, archive)
        digest = _sha256(archive)
        if digest != expected_sha:
            raise CortexScoutError(
                f"Cortex Scout binary checksum mismatch: expected {expected_sha}, got {digest}"
            )
        _extract_binary(archive, target)

    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target


def _start(binary: Path, port: int, base_url: str, config: dict) -> None:
    global _process, _process_url
    if _process and _process.poll() is None and _process_url == base_url:
        return
    if _process and _process.poll() is not None:
        stop()

    runtime_dir = _runtime_dir(config)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_path = runtime_dir / "cortex-scout.log"
    env = os.environ.copy()
    if _bool(config.get("memory_disabled"), True):
        env["CORTEX_SCOUT_MEMORY_DISABLED"] = "1"

    log = open(log_path, "ab")
    try:
        _process = subprocess.Popen(
            [str(binary), "--port", str(port)],
            cwd=str(binary.parent),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    finally:
        log.close()
    _process_url = base_url

    deadline = time.monotonic() + float(config.get("startup_timeout_seconds") or 30)
    while time.monotonic() < deadline:
        if _process.poll() is not None:
            raise CortexScoutError(
                f"Cortex Scout exited during startup:\n{_tail(log_path)}"
            )
        if _healthy(base_url, float(config.get("timeout_seconds") or 120)):
            return
        time.sleep(0.25)

    stop()
    raise CortexScoutError(f"Cortex Scout did not become healthy:\n{_tail(log_path)}")


def _download(url: str, dest: Path) -> None:
    try:
        with request.urlopen(url, timeout=120) as response, open(dest, "wb") as out:
            shutil.copyfileobj(response, out)
    except Exception as exc:
        close = getattr(exc, "close", None)
        if callable(close):
            close()
        raise CortexScoutError(f"Failed to download Cortex Scout binary from {url}: {exc}") from exc


def _extract_binary(archive: Path, target: Path) -> None:
    names = {_binary_name(), "cortex-scout", "cortex-scout.exe"}
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if Path(info.filename).name in names and not info.is_dir():
                    with zf.open(info) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
                    return
    else:
        with tarfile.open(archive) as tf:
            for member in tf.getmembers():
                if Path(member.name).name in names and member.isfile():
                    src = tf.extractfile(member)
                    if src:
                        with src, open(target, "wb") as out:
                            shutil.copyfileobj(src, out)
                        return
    raise CortexScoutError(f"Cortex Scout binary not found inside archive {archive.name}")


def _default_asset_name(release_version: str = DEFAULT_RELEASE_VERSION) -> str:
    version = release_version.lstrip("v")
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux" and machine in {"aarch64", "arm64"}:
        return f"cortex-scout-{version}-linux-arm64.tar.gz"
    if system == "darwin" and machine in {"aarch64", "arm64"}:
        return f"cortex-scout-{version}-macos-arm64.tar.gz"
    if system == "windows" and machine in {"amd64", "x86_64"}:
        return f"cortex-scout-{version}-windows-x64.zip"
    if system == "windows" and machine in {"aarch64", "arm64"}:
        return f"cortex-scout-{version}-windows-arm64.zip"
    raise CortexScoutError(
        f"No Cortex Scout release binary for {system}-{machine}; set binary_path."
    )


def _binary_name() -> str:
    return "cortex-scout.exe" if platform.system().lower() == "windows" else "cortex-scout"


def _bin_dir(config: dict) -> Path:
    return Path(config.get("bin_dir") or PLUGIN_DIR / "bin")


def _runtime_dir(config: dict) -> Path:
    if config.get("runtime_dir"):
        return Path(config["runtime_dir"])
    if config.get("bin_dir"):
        return Path(config["bin_dir"]).parent / "runtime"
    return PLUGIN_DIR / "runtime"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tail(path: Path, max_lines: int = 20) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-max_lines:])
    except OSError:
        return ""


def _bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


atexit.register(stop)
