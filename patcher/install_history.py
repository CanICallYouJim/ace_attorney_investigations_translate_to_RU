"""Keep the game files replaced by the last successful translation upgrade."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from uuid import uuid4

from local_state import digest, read_json, write_json


def game_file(game: Path, relative: str) -> Path:
    candidate = (game / relative).resolve()
    if not candidate.is_relative_to(game.resolve()) or candidate == game.resolve():
        raise ValueError("Недопустимый путь в истории установки.")
    return candidate


def link_or_copy(source: Path, target: Path):
    try:
        target.hardlink_to(source)
    except OSError:
        shutil.copy2(source, target)


class History:
    def __init__(self, game: Path, backup: Path, replace):
        self.game, self.backup, self.replace = game, backup, replace
        self.folder = backup / "versions"
        self.pending = self.folder / "pending.json"
        self.record = None

    def snapshot(self, id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", id):
            raise ValueError("Повреждена история установки.")
        return self.folder / id

    def begin(self, manifest: dict):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.record = {"id": uuid4().hex, "files": {}}
        snapshot = self.snapshot(self.record["id"])
        snapshot.mkdir()
        write_json(snapshot / "manifest.json", manifest)
        write_json(self.pending, self.record)

    def before_replace(self, target: Path, before: str, after: str):
        relative = target.relative_to(self.game).as_posix()
        files = self.record["files"]
        if relative not in files:
            snapshot = self.snapshot(self.record["id"])
            saved = game_file(snapshot, relative)
            saved.parent.mkdir(parents=True, exist_ok=True)
            # Game files are replaced atomically, so the link retains the old
            # bytes without copying a whole bundle on NTFS.
            link_or_copy(target, saved)
            if digest(saved) != before:
                raise ValueError(f"Файл изменился во время установки: {relative}")
            files[relative] = {"before": before, "after": [after]}
        else:
            files[relative]["after"].append(after)
        # Journal first so recovery also covers a crash during the replace.
        write_json(self.pending, self.record)

    def sources(self, record: dict, recovering: bool = False):
        snapshot = self.snapshot(record["id"])
        for relative, entry in record["files"].items():
            target = game_file(self.game, relative)
            current = digest(target)
            if recovering and current == entry["before"]:
                continue
            after = entry["after"] if recovering else entry["after"][-1:]
            saved = game_file(snapshot, relative)
            if current not in after or digest(saved) != entry["before"]:
                raise ValueError(f"Файл игры или резервная копия изменились: {relative}")
            yield target, saved, current, entry["before"]

    def recover(self, manifest: dict):
        record = read_json(self.pending)
        if record is not None:
            if manifest.get("transaction") != record["id"]:
                for target, saved, _, _ in list(self.sources(record, recovering=True)):
                    # If space ran out, recovery can still rename each saved
                    # file back. A retry skips any file already restored.
                    self.replace(saved, target)
            self.pending.unlink()
        self.collect(manifest)

    def restore_file(self, target: Path, saved: Path):
        stage = self.folder / "restore.part"
        try:
            link_or_copy(saved, stage)
            self.replace(stage, target)
        finally:
            stage.unlink(missing_ok=True)

    def rollback(self, manifest: dict, report):
        id = manifest.get("rollback")
        if not id:
            raise ValueError("Предыдущая версия перевода не сохранена.")
        snapshot = self.snapshot(id)
        record = read_json(snapshot / "files.json")
        previous = read_json(snapshot / "manifest.json")
        targets = list(self.sources(record))
        self.begin(manifest)
        for target, saved, current, prior in targets:
            self.before_replace(target, current, prior)
            self.restore_file(target, saved)
            report(f"  < вернул {target.relative_to(self.game)}")
        previous.pop("rollback", None)
        previous.pop("rollback_tag", None)
        return self.commit(previous)

    def commit(self, manifest: dict, previous: dict | None = None):
        id = self.record["id"]
        if previous is not None and self.record["files"]:
            write_json(self.snapshot(id) / "files.json", self.record)
            manifest["rollback"] = id
            manifest["rollback_tag"] = previous.get("release_tag")
        elif manifest.get("rollback") and self.record["files"]:
            merged = self.extend_checkpoint(manifest["rollback"])
            if merged:
                manifest["rollback"] = merged
            else:
                manifest.pop("rollback")
                manifest.pop("rollback_tag", None)
        manifest["transaction"] = id
        write_json(self.backup / "manifest.json", manifest)
        self.recover(manifest)
        return manifest

    def extend_checkpoint(self, previous_id: str) -> str | None:
        """Include later changes made by the same release in its rollback."""
        previous = self.snapshot(previous_id)
        old_files = read_json(previous / "files.json")["files"]
        new_files = self.record["files"]
        for relative in old_files.keys() & new_files.keys():
            if old_files[relative]["after"][-1] != new_files[relative]["before"]:
                return None

        id = uuid4().hex
        merged = self.snapshot(id)
        merged.mkdir()
        shutil.copy2(previous / "manifest.json", merged / "manifest.json")
        files = {}
        for relative in old_files.keys() | new_files.keys():
            source = previous if relative in old_files else self.snapshot(self.record["id"])
            saved = game_file(merged, relative)
            saved.parent.mkdir(parents=True, exist_ok=True)
            old = game_file(source, relative)
            link_or_copy(old, saved)
            files[relative] = {
                "before": (old_files.get(relative) or new_files[relative])["before"],
                "after": (new_files.get(relative) or old_files[relative])["after"][-1:],
            }
        write_json(merged / "files.json", {"id": id, "files": files})
        return id

    def collect(self, manifest: dict):
        if self.folder.is_dir():
            for path in self.folder.iterdir():
                if re.fullmatch(r"[0-9a-f]{32}", path.name) and path.name != manifest.get("rollback"):
                    shutil.rmtree(path, ignore_errors=True)


def has_legacy_translation(game: Path, manifest: dict) -> bool:
    for relative, entry in manifest.get("files", {}).items():
        current = game_file(game, relative)
        patched = entry.get("sha_patched")
        if patched and current.is_file() and digest(current) == patched:
            return True
    return False
