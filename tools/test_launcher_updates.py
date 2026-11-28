"""Exercise the release cache and game file rollback without touching Steam."""
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "patcher"))
import aai2ru
import launcher_update as updater
import locate
import steps
from local_state import digest, read_json, write_json


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.content = b"installer"
        self.release = updater.Release("v2026-11-27.10", len(self.content),
                                       hashlib.sha256(self.content).hexdigest())
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)

    def test_only_newer_published_exe_with_digest_is_offered(self):
        info = {"tag_name": self.release.tag, "assets": [
            {"name": updater.EXE, "state": "uploaded", "size": self.release.size,
             "digest": "sha256:" + self.release.sha}
        ]}
        with patch.object(updater, "urlopen", side_effect=lambda *a, **k:
                          io.BytesIO(json.dumps(info).encode())):
            self.assertEqual(updater.latest("v2026-11-27.2"), self.release)
            self.assertIsNone(updater.latest("v2026-11-28"))
            info["prerelease"] = True
            self.assertIsNone(updater.latest("v2026-11-27"))
            info["prerelease"] = False
            info["assets"][0]["digest"] = ""
            self.assertIsNone(updater.latest("v2026-11-27"))

    def test_wrong_bytes_never_launch_or_replace_the_active_version(self):
        with (patch.object(updater, "urlopen", return_value=io.BytesIO(b"i" * self.release.size)),
              patch.object(updater, "start_exe") as start):
            with self.assertRaises(ValueError):
                updater.download_and_launch(self.cache, self.release, [], current="v2026-11-27")
            start.assert_not_called()
        self.assertFalse((self.cache / "current.json").exists())
        self.assertFalse(list(self.cache.glob("*.exe")))
        self.assertFalse((self.cache / "download.part").exists())

    def test_failed_launch_keeps_active_and_success_removes_old_exe(self):
        prior_bytes = b"previous executable"
        prior = {"tag": "v2026-11-27.2", "sha": hashlib.sha256(prior_bytes).hexdigest()}
        older = {"tag": "v2026-11-27.1", "sha": "c" * 64}
        state = self.cache / "current.json"
        write_json(state, {"active": prior, "previous": older})
        updater.cached_exe(self.cache, prior).write_bytes(prior_bytes)
        updater.cached_exe(self.cache, older).touch()
        with (patch.object(updater, "urlopen", side_effect=lambda *a, **k: io.BytesIO(self.content)),
              patch.object(updater, "start_exe", side_effect=[OSError("failed"), None])):
            with self.assertRaises(OSError):
                updater.download_and_launch(self.cache, self.release, [], current=prior["tag"])
            self.assertEqual(read_json(state)["active"], prior)
            updater.download_and_launch(self.cache, self.release, [], current=prior["tag"])
        self.assertEqual(read_json(state)["previous"], prior)
        self.assertEqual(read_json(state)["active"]["sha"], self.release.sha)
        self.assertTrue(updater.cached_exe(self.cache, prior).exists())
        self.assertFalse(updater.cached_exe(self.cache, older).exists())

    def test_bootstrap_falls_back_to_previous_cached_exe(self):
        broken = {"tag": self.release.tag, "sha": self.release.sha}
        prior = {"tag": "v2026-11-27.2", "sha": "b" * 64}
        state = self.cache / "current.json"
        write_json(state, {"active": broken, "previous": prior})
        with patch.object(updater, "start_exe", side_effect=[OSError("failed"), None]) as start:
            self.assertTrue(updater.launch_cached(self.cache, "v2026-11-27", []))
        self.assertEqual(start.call_args.args[1], prior)
        self.assertEqual(read_json(state), {"active": prior})

    def test_broken_active_metadata_does_not_hide_previous_exe(self):
        prior = {"tag": "v2026-11-27.2", "sha": "b" * 64}
        write_json(self.cache / "current.json", {"active": {"sha": "a" * 64}, "previous": prior})
        with patch.object(updater, "start_exe") as start:
            self.assertTrue(updater.launch_cached(self.cache, "v2026-11-27", []))
        self.assertEqual(start.call_args.args[1], prior)

    def test_reused_download_must_match_reported_size_too(self):
        (self.cache / f"{self.release.sha}.exe").write_bytes(self.content)
        wrong = updater.Release(self.release.tag, self.release.size + 1, self.release.sha)
        with (patch.object(updater, "urlopen", return_value=io.BytesIO(self.content)),
              patch.object(updater, "start_exe") as start):
            with self.assertRaises(ValueError):
                updater.download_and_launch(self.cache, wrong, [], current="v2026-11-27")
        start.assert_not_called()

    def test_update_from_fallback_keeps_that_working_exe(self):
        prior_bytes = b"working fallback"
        prior = {"tag": "v2026-11-27.2", "sha": hashlib.sha256(prior_bytes).hexdigest()}
        broken = {"tag": "v2026-11-27.3", "sha": "a" * 64}
        write_json(self.cache / "current.json", {"active": broken, "previous": prior})
        updater.cached_exe(self.cache, prior).write_bytes(prior_bytes)
        updater.cached_exe(self.cache, broken).touch()
        with (patch.object(updater, "urlopen", return_value=io.BytesIO(self.content)),
              patch.object(updater, "start_exe")):
            updater.download_and_launch(self.cache, self.release, [], current=prior["tag"])
        self.assertEqual(read_json(self.cache / "current.json")["previous"], prior)
        self.assertTrue(updater.cached_exe(self.cache, prior).exists())


class RollbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / "game"
        self.data = self.root / "data"
        self.data.mkdir()
        (self.data / "strings.json").touch()
        (self.game / "GK12_Data").mkdir(parents=True)
        (self.game / "GK12_Data" / "data.unity3d").touch()
        self.text = self.game / "scripts.bundle"
        self.image = self.game / "art.bundle"
        self.text.write_bytes(b"original text")
        self.image.write_bytes(b"original image")
        self.backup = self.game / aai2ru.BACKUP_DIR
        self.args = SimpleNamespace(game_path=str(self.game), data=str(self.data), uninstall=False,
                                    bundle=None, build_only=None, no_graphics=False,
                                    full=False, gk1_graphics=False, backup_graphics=False)
        common = ModuleType("common")
        common.sha256 = digest
        for mock in (patch.dict(sys.modules, {"common": common}),
                     patch.object(locate, "find_game", return_value=self.game),
                     patch.object(aai2ru, "preflight", return_value=None),
                     patch.object(aai2ru, "say"), patch.object(steps, "strings", return_value=[]),
                     patch.object(steps, "fonts", return_value=[]),
                     patch.object(steps, "gk1_scripts", return_value=[])):
            mock.start()
            self.addCleanup(mock.stop)

    def install(self, tag, text, art, *, fail=False):
        if tag:
            write_json(self.data / "version.json", {"tag": tag})

        def change(stage, target, content):
            staged = stage / target.name
            staged.write_bytes(content)
            return steps.Change(target.name, target, staged, "done")

        def graphics(stage, *args, **kwargs):
            if fail:
                raise RuntimeError("broken build")
            yield change(stage, self.image, art)

        with (patch.object(steps, "scripts", side_effect=lambda s: [change(s, self.text, text)]),
              patch.object(steps, "graphics", side_effect=graphics)):
            return aai2ru.run(self.args)

    def rollback(self):
        self.args.rollback = True
        return aai2ru.run(self.args)

    def test_legacy_upgrade_restores_text_and_graphics_without_original_graphics_backup(self):
        self.install(None, b"old text", b"old image")
        self.install("v2026-11-27", b"new text", b"new image")
        self.assertFalse((self.backup / "art.bundle").exists())
        self.assertEqual(self.rollback(), 0)
        self.assertEqual(self.text.read_bytes(), b"old text")
        self.assertEqual(self.image.read_bytes(), b"old image")
        self.assertNotIn("rollback", aai2ru.load_manifest(self.backup))

    def test_failed_upgrade_recovers_files_and_keeps_previous_snapshot(self):
        self.install("v2026-11-25", b"first", b"first")
        self.install("v2026-11-26", b"second", b"second")
        with self.assertRaisesRegex(RuntimeError, "broken build"):
            self.install("v2026-11-27", b"third", b"third", fail=True)
        self.assertEqual(self.text.read_bytes(), b"second")
        self.assertEqual(aai2ru.load_manifest(self.backup)["release_tag"], "v2026-11-26")
        self.assertEqual(self.rollback(), 0)
        self.assertEqual(self.text.read_bytes(), b"first")
        self.assertEqual(self.image.read_bytes(), b"first")

    def test_external_change_aborts_rollback_before_touching_other_files(self):
        self.install("v2026-11-26", b"old", b"old")
        self.install("v2026-11-27", b"new", b"new")
        self.image.write_bytes(b"steam update")
        with self.assertRaisesRegex(ValueError, "art.bundle"):
            self.rollback()
        self.assertEqual(self.text.read_bytes(), b"new")
        self.assertEqual(self.image.read_bytes(), b"steam update")

    def test_finishing_graphics_with_same_installer_extends_rollback(self):
        self.install("v2026-11-26", b"old text", b"old image")
        self.args.no_graphics = True
        self.install("v2026-11-27", b"new text", b"new image")
        self.args.no_graphics = False
        self.install("v2026-11-27", b"new text", b"new image")
        self.assertEqual(self.rollback(), 0)
        self.assertEqual(self.text.read_bytes(), b"old text")
        self.assertEqual(self.image.read_bytes(), b"old image")

    def test_failed_uninstall_keeps_previous_translation(self):
        self.install("v2026-11-26", b"old", b"old")
        self.install("v2026-11-27", b"new", b"new")
        (self.backup / "scripts.bundle").write_bytes(b"damaged backup")
        self.args.uninstall = True
        self.assertEqual(aai2ru.run(self.args), 1)
        self.args.uninstall = False
        self.assertEqual(self.rollback(), 0)
        self.assertEqual(self.text.read_bytes(), b"old")

    def test_uninstall_keeps_priority_over_build_only(self):
        self.install("v2026-11-26", b"old", b"old")
        self.args.uninstall = True
        self.args.build_only = str(self.root / "unused")
        self.assertEqual(aai2ru.run(self.args), 0)
        self.assertEqual(self.text.read_bytes(), b"original text")
        self.assertFalse(Path(self.args.build_only).exists())


if __name__ == "__main__":
    unittest.main()
