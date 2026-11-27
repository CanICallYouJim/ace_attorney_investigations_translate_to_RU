"""Find and start official Windows installer releases."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from local_state import digest, locked, read_json, write_json

REPO = "CanICallYouJim/ace_attorney_investigations_translate_to_RU"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
EXE = "AAI2-RU.exe"
CHECK_INTERVAL_MS = 60 * 60 * 1000
MAX_BYTES = 512 * 2**20
SHA = re.compile(r"[a-f0-9]{64}")
READY_ENV = "AAI2_UPDATE_READY"
TAG_ENV = "AAI2_UPDATE_EXPECTED_TAG"


def version(tag):
    if not isinstance(tag, str):
        return None
    match = re.fullmatch(r"v([0-9]{4}-[0-9]{2}-[0-9]{2})(?:\.([1-9][0-9]{0,3}))?", tag)
    if match:
        try:
            return date.fromisoformat(match[1]), int(match[2] or 0)
        except ValueError:
            pass
    return None


def release_tag(data: Path) -> str | None:
    try:
        tag = read_json(data / "version.json", {}).get("tag")
        return tag if version(tag) else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


@dataclass(frozen=True)
class Release:
    tag: str
    size: int
    sha: str

    @property
    def url(self):
        return f"https://github.com/{REPO}/releases/download/{self.tag}/{EXE}"


def latest(current: str) -> Release | None:
    request = Request(API, headers={"Accept": "application/vnd.github+json",
                                    "User-Agent": "AAI2-RU"})
    with urlopen(request, timeout=15) as response:
        info = json.loads(response.read(1024 * 1024))
    tag = info.get("tag_name")
    if (info.get("draft") or info.get("prerelease") or not version(tag)
            or version(tag) <= version(current)):
        return None
    for asset in info.get("assets", []):
        raw_digest = asset.get("digest") or ""
        sha = raw_digest.removeprefix("sha256:")
        size = asset.get("size")
        if (asset.get("name") == EXE and asset.get("state") == "uploaded"
                and raw_digest != sha and SHA.fullmatch(sha)
                and type(size) is int and 0 < size <= MAX_BYTES):
            return Release(tag, size, sha)
    return None


def cache_dir() -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    if local and sys.platform == "win32" and getattr(sys, "frozen", False):
        import ctypes
        # The user-writable installer cache must never be launched elevated.
        if ctypes.windll.shell32.IsUserAnAdmin():
            return None
        return Path(local) / "AAI2-RU" / "updates"
    return None


def cached_exe(folder: Path, entry: dict) -> Path:
    if not SHA.fullmatch(entry["sha"]):
        raise ValueError("Повреждена запись о версии установщика.")
    return folder / f"{entry['sha']}.exe"


def cache_state(folder: Path) -> dict:
    try:
        state = read_json(folder / "current.json", {})
    except ValueError:
        return {}
    if not isinstance(state, dict):
        return {}
    valid = {}
    for slot in ("active", "previous"):
        entry = state.get(slot)
        if (isinstance(entry, dict) and version(entry.get("tag"))
                and isinstance(entry.get("sha"), str) and SHA.fullmatch(entry["sha"])):
            valid[slot] = entry
    return valid


def collect(folder: Path, state: dict) -> None:
    keep = {entry["sha"] for entry in state.values() if entry}
    for path in folder.glob("*.exe"):
        if SHA.fullmatch(path.stem) and path.stem not in keep:
            try:
                path.unlink()
            except OSError:
                # Windows keeps running executables locked; retry next launch.
                pass


def start_exe(folder: Path, entry: dict, arguments: list[str]) -> None:
    exe = cached_exe(folder, entry)
    if digest(exe) != entry["sha"]:
        raise ValueError("Контрольная сумма установщика не совпала.")
    with tempfile.TemporaryDirectory(prefix="start-", dir=folder) as waiting:
        ready = Path(waiting) / "ready"
        env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1",
                   **{READY_ENV: str(ready), TAG_ENV: entry["tag"]})
        process = subprocess.Popen([str(exe), *arguments], env=env)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise OSError("Новый установщик завершился до открытия окна.")
            if ready.is_file():
                return
            time.sleep(.15)
        # PyInstaller may still be unpacking. The child will exit without
        # showing an extra window once it sees its readiness directory is gone.
        raise OSError("Новый установщик не открыл окно за минуту.")


def announce_ready(tag: str | None) -> bool:
    ready = os.environ.pop(READY_ENV, None)
    expected = os.environ.pop(TAG_ENV, None)
    if ready:
        if expected != tag:
            return False
        try:
            Path(ready).touch()
        except OSError:
            return False
    return True


def launch_cached(folder: Path, current: str, arguments: list[str]) -> bool:
    if READY_ENV in os.environ or not (folder / "current.json").is_file():
        return False
    try:
        with locked(folder):
            state = cache_state(folder)
            for slot in ("active", "previous"):
                entry = state.get(slot)
                if not entry or version(entry["tag"]) <= version(current):
                    continue
                try:
                    start_exe(folder, entry, arguments)
                except (OSError, ValueError):
                    continue
                try:
                    if slot == "previous":
                        state = {"active": entry}
                        write_json(folder / "current.json", state)
                    collect(folder, state)
                except OSError:
                    pass  # The replacement window is already open.
                return True
            collect(folder, state)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass  # The original standalone installer still opens.
    return False


def download_and_launch(folder: Path, release: Release, arguments: list[str], *, current: str) -> None:
    with locked(folder):
        state_path = folder / "current.json"
        state = cache_state(folder)
        active = state.get("active")
        if active and version(active["tag"]) > version(release.tag):
            start_exe(folder, active, arguments)
            return
        entry = {"tag": release.tag, "sha": release.sha}
        target = cached_exe(folder, entry)
        if not target.exists() or target.stat().st_size != release.size or digest(target) != release.sha:
            partial = folder / "download.part"
            try:
                request = Request(release.url, headers={"User-Agent": "AAI2-RU"})
                with urlopen(request, timeout=20) as source, partial.open("wb") as output:
                    remaining = release.size
                    deadline = time.monotonic() + 15 * 60
                    while chunk := source.read1(256 * 1024):
                        if time.monotonic() > deadline:
                            raise OSError("Не удалось скачать установщик за 15 минут.")
                        remaining -= len(chunk)
                        if remaining < 0:
                            raise ValueError("Получен неверный размер установщика.")
                        output.write(chunk)
                if remaining or digest(partial) != release.sha:
                    raise ValueError("Загрузка неполная или контрольная сумма не совпала.")
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
        if active != entry:
            next_state = {"active": entry}
            for prior in state.values():
                if version(prior["tag"]) <= version(current):
                    try:
                        intact = digest(cached_exe(folder, prior)) == prior["sha"]
                    except OSError:
                        intact = False
                    if intact:
                        next_state["previous"] = prior
                        break
            write_json(state_path, next_state)
            try:
                start_exe(folder, entry, arguments)
            except Exception:
                write_json(state_path, state)
                collect(folder, state)
                raise
        else:
            start_exe(folder, entry, arguments)
        try:
            collect(folder, cache_state(folder))
        except OSError:
            pass  # The update is already open.
