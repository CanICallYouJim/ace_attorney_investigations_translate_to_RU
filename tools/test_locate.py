"""Поиск игры вне Steam: временные диски и папки, без обхода настоящих дисков."""
from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "patcher"))
import locate

NEARBY_CANDIDATES = locate.nearby_candidates


class LocateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, value in (("nearby_candidates", []), ("candidates", []),
                            ("local_drives", [self.root])):
            mock = patch.object(locate, name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def game(self, relative: str) -> Path:
        folder = self.root / relative
        (folder / "GK12_Data").mkdir(parents=True)
        (folder / "GK12.exe").write_bytes(b"")
        return folder.resolve()

    def test_finds_non_steam_game_in_nested_unicode_folder(self):
        game = self.game("Игры с диска/другое имя/one/two/three/four/five/game")
        self.assertEqual(locate.find_game(), game)

    def test_continues_on_second_drive(self):
        first = self.root / "empty drive"
        second = self.root / "second drive"
        first.mkdir()
        game = self.game("second drive/arbitrary/game")
        with patch.object(locate, "local_drives", return_value=[first, second]):
            self.assertEqual(locate.find_game(), game)

    def test_explicit_path_wins_and_invalid_path_does_not_fall_back(self):
        game = self.game("explicit")
        with patch.object(locate, "local_drives") as drives:
            self.assertEqual(locate.find_game(game), game)
            self.assertIsNone(locate.find_game(self.root / "missing"))
            drives.assert_not_called()

    def test_nearby_game_wins_over_steam_without_disk_scan(self):
        nearby, steam = self.game("nearby"), self.game("steam")
        with patch.object(locate, "nearby_candidates", return_value=[nearby]), \
                patch.object(locate, "candidates", return_value=[steam]), \
                patch.object(locate, "local_drives") as drives:
            self.assertEqual(locate.find_game(), nearby)
            drives.assert_not_called()

    def test_steam_game_remains_fast_path(self):
        game = self.game("steam")
        with patch.object(locate, "candidates", return_value=[game]), \
                patch.object(locate, "local_drives") as drives:
            self.assertEqual(locate.find_game(), game)
            drives.assert_not_called()

    def test_marker_alone_or_directory_named_exe_is_not_game(self):
        (self.root / "GK12.exe").write_bytes(b"")
        self.assertIsNone(locate.find_game())
        (self.root / "GK12.exe").unlink()
        (self.root / "GK12.exe").mkdir()
        (self.root / "GK12_Data").mkdir()
        self.assertFalse(locate.is_game_dir(self.root))
        self.assertIsNone(locate.find_game())

    def test_inaccessible_directory_does_not_abort_other_folders(self):
        blocked = self.root / "a-blocked"
        blocked.mkdir()
        game = self.game("z-working/game")
        scandir = locate.os.scandir

        def guarded(path):
            if Path(path) == blocked:
                raise PermissionError("test directory is unreadable")
            return scandir(path)

        with patch.object(locate.os, "scandir", side_effect=guarded) as scan:
            self.assertEqual(locate.find_game(), game)
            self.assertTrue(any(Path(call.args[0]) == blocked for call in scan.call_args_list))

    def test_does_not_descend_into_reparse_directory(self):
        self.game("a-link/game")
        game = self.game("z-real/game")
        with patch.object(locate, "_is_reparse_dir", side_effect=lambda p: p.name == "a-link"):
            self.assertEqual(locate.find_game(), game)

    def test_windows_junction_attribute_is_detected(self):
        info = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        with patch.object(Path, "stat", return_value=info):
            self.assertTrue(locate._is_reparse_dir(self.root))

    def test_frozen_app_checks_actual_exe_folder(self):
        # Remove the test's nearby override to exercise PyInstaller's folder choice.
        with patch.object(locate, "nearby_candidates", NEARBY_CANDIDATES), \
                patch.object(sys, "frozen", True, create=True), \
                patch.object(sys, "executable", str(self.root / "AAI2-RU.exe")):
            self.assertEqual(locate.nearby_candidates()[0], self.root)

    def test_slow_path_reports_which_drive_is_being_searched(self):
        messages = []
        self.assertIsNone(locate.find_game(progress=messages.append))
        self.assertTrue(any(str(self.root) in message for message in messages))
        self.assertIn("--game-path", locate.explain_failure())


if __name__ == "__main__":
    unittest.main()
