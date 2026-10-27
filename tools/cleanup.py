"""Remove only reproducible build files and download caches. Preview by default.

Run with project Python: tools/cleanup.py --apply [--now] [--user-caches].
Automatic runs retain files changed within seven days. No links are followed.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
BUILD_DIRS = ("work/build", "work/build_assets", "dist/.build")


def linked(path: Path) -> bool:
    s = path.lstat()
    return stat.S_ISLNK(s.st_mode) or bool(getattr(s, "st_file_attributes", 0) & 1024)


def files_under(root: Path):
    # Validate every parent before walking or deleting, including Windows junctions.
    if not root.exists():
        return
    if any(linked(p) for p in (root, *root.parents)):
        raise ValueError(f"Link/reparse point refused: {root}")
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not linked(Path(base) / d)]
        for name in files:
            p = Path(base) / name
            if not linked(p):
                yield p


def cleanup(apply=False, now=False, user_caches=False):
    cutoff = time.time() - 7 * 86400
    targets = [(PROJECT / rel, "build") for rel in BUILD_DIRS]
    # Derive the real profile from this checkout; LOCALAPPDATA may be redirected
    # by the execution sandbox. Never use a broad AppData/Temp deletion rule.
    if user_caches:
        profile = Path.home().resolve()
        targets += [(profile / "AppData/Local/pip/Cache", "download-cache"),
                    (profile / "AppData/Local/npm-cache/_cacache", "download-cache"),
                    (profile / "npm-cache/_cacache", "download-cache")]
        jetbrains = profile / "AppData/Local/JetBrains"
        if jetbrains.exists() and not linked(jetbrains):
            targets += [(p / "tmp/hprof-temp", "heap-dump")
                        for p in jetbrains.glob("PyCharm*") if p.is_dir() and not linked(p)]
    rows, errors = [], []
    for root, category in targets:
        root = root.absolute()
        if category == "build" and not root.resolve().is_relative_to(PROJECT):
            raise ValueError(f"Outside workspace: {root}")
        paths = list(files_under(root))
        # Keep the whole build directory if any file is recent: a build may be active.
        if not now and category == "build" and any(
                max(p.stat().st_mtime, p.stat().st_ctime) > cutoff for p in paths):
            continue
        for p in paths:
            try:
                if category == "heap-dump" and p.suffix.lower() != ".hprof":
                    continue
                s = p.stat()
                if not now and max(s.st_mtime, s.st_ctime) > cutoff:
                    continue
                if apply:
                    # Recheck parent chain immediately before mutation.
                    if any(linked(q) for q in (p, *p.parents)):
                        raise ValueError(f"Link refused: {p}")
                    p.unlink()
                rows.append({"path": str(p), "bytes": s.st_size, "category": category})
            except (OSError, ValueError) as exc:
                errors.append({"path": str(p), "error": str(exc)})
    result = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "applied": apply,
              "now": now, "bytes": sum(r["bytes"] for r in rows),
              "files": rows, "errors": errors}
    if apply:
        out = PROJECT / "work/cleanup"
        out.mkdir(parents=True, exist_ok=True)
        # One small latest report; reports themselves must not grow indefinitely.
        (out / "latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--now", action="store_true", help="manual cleanup, no seven-day grace")
    parser.add_argument("--user-caches", action="store_true")
    args = parser.parse_args()
    result = cleanup(args.apply, args.now, args.user_caches)
    print(json.dumps({k: v for k, v in result.items() if k != "files"}, ensure_ascii=True))
    print(f"Files: {len(result['files'])}; GiB: {result['bytes'] / 2**30:.3f}")
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
