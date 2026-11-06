"""Optional installer music, read from the player's installed game.

No game audio is shipped with the installer. Decoding happens off the GUI thread
and stays in memory. Attenuation changes only PCM samples, never the Windows
mixer or the game's audio settings.
"""
from __future__ import annotations

import array
import ctypes
import io
import sys
import threading
import traceback
import wave
from pathlib import Path


class _WavePlayer:
    """Own waveOut handle; attenuation is baked into PCM, not mixer settings."""

    def __init__(self, wav: bytes, volume: float):
        from ctypes import wintypes

        class Format(ctypes.Structure):
            _fields_ = [("tag", wintypes.WORD), ("channels", wintypes.WORD),
                        ("rate", wintypes.DWORD), ("bytes_per_sec", wintypes.DWORD),
                        ("block", wintypes.WORD), ("bits", wintypes.WORD),
                        ("extra", wintypes.WORD)]

        class Header(ctypes.Structure):
            _fields_ = [("data", ctypes.c_void_p), ("length", wintypes.DWORD),
                        ("recorded", wintypes.DWORD), ("user", ctypes.c_size_t),
                        ("flags", wintypes.DWORD), ("loops", wintypes.DWORD),
                        ("next", ctypes.c_void_p), ("reserved", ctypes.c_size_t)]

        with wave.open(io.BytesIO(wav), "rb") as source:
            channels, width, rate, frames, _, _ = source.getparams()
            if width != 2:
                raise ValueError("Музыка должна быть в формате PCM16.")
            samples = array.array("h", source.readframes(frames))
        for index in range(len(samples)):
            samples[index] = round(samples[index] * volume)
        self.buffer = ctypes.create_string_buffer(samples.tobytes())
        self.header = Header(ctypes.addressof(self.buffer), len(samples) * 2,
                             0, 0, 4 | 8, 0xFFFFFFFF, None, 0)
        self.format = Format(1, channels, rate, rate * channels * 2,
                             channels * 2, 16, 0)
        self.dll = ctypes.WinDLL("winmm")
        self.handle = ctypes.c_void_p()
        self.prepared = False
        code = self.dll.waveOutOpen(ctypes.byref(self.handle), wintypes.UINT(-1),
                                    ctypes.byref(self.format), None, None, 0)
        self._check(code)
        try:
            self._check(self.dll.waveOutPrepareHeader(self.handle,
                        ctypes.byref(self.header), ctypes.sizeof(self.header)))
            self.prepared = True
        except Exception:
            self.close()
            raise

    @staticmethod
    def _check(code: int) -> None:
        if code:
            raise RuntimeError(f"Аудиоустройство недоступно (WinMM {code}).")

    def play(self, muted: bool) -> None:
        if muted:
            self.set_muted(True)
        self._check(self.dll.waveOutWrite(self.handle, ctypes.byref(self.header),
                                        ctypes.sizeof(self.header)))

    def set_muted(self, muted: bool) -> None:
        action = self.dll.waveOutPause if muted else self.dll.waveOutRestart
        self._check(action(self.handle))

    def close(self) -> None:
        if not self.handle:
            return
        self.dll.waveOutReset(self.handle)
        if self.prepared:
            self.dll.waveOutUnprepareHeader(self.handle, ctypes.byref(self.header),
                                           ctypes.sizeof(self.header))
        self.dll.waveOutClose(self.handle)
        self.handle = ctypes.c_void_p()


class LoadingAudio:
    """Asynchronous looping background music with a quiet failure path.

    Call ``start(game_root)`` once a game is found, ``set_muted(bool)`` from
    the sound button, and ``stop()`` on completion or window close. ``available``
    becomes true after playback opens; ``error`` explains unavailable audio.
    A missing audio device or codec must never prevent installation.
    """

    def __init__(self, volume: float = 0.35):
        self.volume = max(0.0, min(1.0, volume))
        self.muted = False
        self.available = False
        self.error: str | None = None
        self._lock = threading.RLock()
        self._cancel: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._player: _WavePlayer | None = None

    def start(self, game_root: str | Path) -> None:
        """Start loading immediately; never block the Tk event loop."""
        self.stop()
        self.error = None
        if sys.platform != "win32":
            self.error = "Музыка доступна только в Windows."
            return
        cancel = threading.Event()
        self._cancel = cancel
        self._thread = threading.Thread(
            target=self._play, args=(Path(game_root), cancel),
            name="installer-music", daemon=True)
        self._thread.start()

    def _play(self, game_root: Path, cancel: threading.Event) -> None:
        player = None
        try:
            import UnityPy

            bundles = game_root / "GK12_Data/StreamingAssets/aa/StandaloneWindows64"
            candidates = sorted(bundles.glob("gk2_bgm_trial_assets_all_*.bundle"))
            if not candidates:
                candidates = sorted(bundles.glob("gk2_bgm_assets_all_*.bundle"))
            if not candidates:
                raise FileNotFoundError("Музыкальный бандл игры не найден.")
            env = UnityPy.load(str(candidates[0]))
            if cancel.is_set():
                return
            clip = next((obj for obj in env.objects
                         if obj.type.name == "AudioClip"
                         and obj.peek_name() == "BGM_04"), None)
            if clip is None:
                raise LookupError("Фоновая композиция игры не найдена.")
            samples = clip.read().samples
            wav = next((data for name, data in samples.items()
                        if name.lower().endswith(".wav")), None)
            if not wav or wav[:4] != b"RIFF":
                raise ValueError("Не удалось декодировать музыку игры.")
            # Release the bundle before installation starts its heavier work.
            del samples, clip, env
            if cancel.is_set():
                return
            try:
                player = _WavePlayer(wav, self.volume)
                del wav
                with self._lock:
                    if cancel.is_set():
                        return
                    self._player = player
                    player.play(self.muted)
                    self.available = True
                cancel.wait()
            finally:
                with self._lock:
                    if player:
                        player.close()
                    if self._player is player:
                        self._player = None
                        self.available = False
        except Exception as exc:
            with self._lock:
                if not cancel.is_set():
                    self.error = traceback.format_exc()

    def set_muted(self, muted: bool) -> None:
        with self._lock:
            self.muted = bool(muted)
            try:
                if self._player:
                    self._player.set_muted(self.muted)
            except Exception as exc:
                self.error = traceback.format_exc()
                self.stop()

    def stop(self) -> None:
        """Stop sound immediately; decoding and cleanup finish asynchronously."""
        with self._lock:
            if self._cancel:
                self._cancel.set()
            if self._player:
                self._player.close()
            self.available = False

    def wait_closed(self, timeout: float = 5.0) -> None:
        """Optional shutdown hook for callers outside the UI thread."""
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout)
