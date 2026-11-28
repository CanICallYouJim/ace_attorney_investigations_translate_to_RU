"""Installer progress and entry-point routing; no real game files are accessed."""
from __future__ import annotations

import array
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "patcher"))
import aai2ru
import locate
import steps


class ProgressTests(unittest.TestCase):
    def execute(self, *, callback=True, fail=False, no_graphics=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = root / "data"
            data.mkdir()
            (data / "strings.json").write_text("{}", encoding="utf-8")
            stage = root / "stage"
            stage.mkdir()
            staged = stage / "file"
            staged.write_bytes(b"test")
            change = steps.Change("test", root / "original", staged, "test")
            args = SimpleNamespace(
                game_path=str(root), data=str(data), uninstall=False, bundle=None,
                build_only=str(stage), no_graphics=no_graphics, full=False,
                gk1_graphics=False, backup_graphics=False,
            )
            events = []
            if callback:
                args.progress = events.append
            common = ModuleType("common")
            common.sha256 = lambda path: "test-sha"

            def graphics(stage, gk1, only, record, progress=None):
                if progress:
                    progress(dict(kind="progress", id="graphics", current=0,
                                  total=1, detail="test"))
                yield change
                if progress:
                    progress(dict(kind="progress", id="graphics", current=1,
                                  total=1, detail="test"))

            with (
                patch.object(locate, "find_game", return_value=root),
                patch.object(aai2ru, "setup_env"),
                patch.object(aai2ru, "load_manifest", return_value={}),
                patch.object(aai2ru, "say"),
                patch.object(aai2ru, "install_change") as install,
                patch.object(aai2ru, "save_manifest") as save,
                patch.object(steps, "scripts", return_value=[change],
                             side_effect=RuntimeError("failed") if fail else None),
                patch.object(steps, "strings", return_value=[change]),
                patch.object(steps, "gk1_scripts", return_value=[]),
                patch.object(steps, "fonts", return_value=[]),
                patch.object(steps, "graphics", side_effect=graphics),
                patch.dict(sys.modules, {"common": common}),
            ):
                if fail:
                    with self.assertRaisesRegex(RuntimeError, "failed"):
                        aai2ru.run(args)
                else:
                    self.assertEqual(aai2ru.run(args), 0)
                install.assert_not_called()
                save.assert_not_called()
            return events

    def test_complete_event_order_and_counts(self):
        events = self.execute()
        self.assertEqual(events[0]["kind"], "game")
        phases = [e["id"] for e in events if e["kind"] == "phase"]
        self.assertEqual(phases, ["scripts", "strings", "gk1", "fonts", "graphics"])
        self.assertEqual([e["id"] for e in events if e["kind"] == "phase_done"], phases)
        for phase in ("scripts", "strings", "graphics"):
            values = [e["current"] for e in events
                      if e["kind"] == "progress" and e["id"] == phase]
            self.assertEqual(values, [0, 1])
        self.assertTrue(all(0 <= e["current"] <= e["total"] for e in events
                            if e["kind"] == "progress"))

    def test_failure_never_completes_phase(self):
        events = self.execute(fail=True)
        self.assertFalse(any(e["kind"] == "phase_done" for e in events))

    def test_console_without_callback(self):
        self.assertEqual(self.execute(callback=False), [])

    def test_disabled_graphics(self):
        self.assertFalse(any(e.get("id") == "graphics"
                             for e in self.execute(no_graphics=True)))


class EntryPointTests(unittest.TestCase):
    def test_preview_routes_to_gui_without_installing(self):
        ui = ModuleType("loading_ui")
        ui.launch = Mock(return_value=0)
        with (patch.dict(sys.modules, {"loading_ui": ui}),
              patch.object(aai2ru, "setup_console"),
              patch.object(aai2ru, "run") as run):
            self.assertEqual(aai2ru.main(["--preview"]), 0)
            ui.launch.assert_called_once()
            self.assertTrue(ui.launch.call_args.args[0].preview)
            run.assert_not_called()


    def test_explicit_console_routes_to_run(self):
        ui = ModuleType("loading_ui")
        ui.launch = Mock()
        with (patch.dict(sys.modules, {"loading_ui": ui}),
              patch.object(aai2ru, "setup_console"),
              patch.object(aai2ru, "say"),
              patch.object(aai2ru, "run", return_value=0) as run):
            self.assertEqual(aai2ru.main(["--console", "--no-pause"]), 0)
            run.assert_called_once()
            ui.launch.assert_not_called()

    def test_preview_rejects_build_only(self):
        with (patch.object(aai2ru, "setup_console"),
              patch.object(aai2ru, "say"),
              patch.object(aai2ru, "run") as run):
            self.assertEqual(aai2ru.main(["--preview", "--build-only", "unused"]), 1)
            run.assert_not_called()


class LauncherEventTests(unittest.TestCase):
    def test_failed_ui_event_does_not_stop_later_progress(self):
        from loading_ui import Installer

        events = queue.Queue()
        broken = {"kind": "progress", "id": "graphics", "current": 20}
        done = {"kind": "finished", "code": 0}
        events.put(broken)
        events.put(done)
        handler = Mock(side_effect=[RuntimeError("render failed"), False])
        root = Mock()
        launcher = SimpleNamespace(events=events, handle=handler, root=root, poll=Mock())

        Installer.poll(launcher)

        self.assertEqual([call.args[0] for call in handler.call_args_list], [broken, done])
        root.report_callback_exception.assert_called_once()
        root.after.assert_called_once_with(60, launcher.poll)

    def test_memory_error_reports_failure_and_traceback(self):
        from loading_ui import Installer

        events = queue.Queue()
        launcher = SimpleNamespace(events=events, args=SimpleNamespace(preview=False),
                                   game="dummy", rollback=False, runner=Mock(side_effect=MemoryError))
        Installer.work(launcher)

        self.assertIn("MemoryError", events.get_nowait()["text"])
        self.assertEqual(events.get_nowait(), {"kind": "finished", "code": 1, "failure": "memory"})


class LauncherAudioTests(unittest.TestCase):
    def test_gain_changes_keep_playback_position_and_wrap(self):
        from loading_audio import _WavePlayer

        player = _WavePlayer.__new__(_WavePlayer)
        player.pcm = array.array("h", [1000, -2000, 3000, -4000]).tobytes()
        player.offset = 0
        self.assertEqual(list(array.array("h", player._next_block(4, .35))), [350, -700])
        self.assertEqual(player._next_block(2, 0), b"\x00\x00")
        self.assertEqual(list(array.array("h", player._next_block(4, 1))), [-4000, 1000])


if __name__ == "__main__":
    unittest.main()
