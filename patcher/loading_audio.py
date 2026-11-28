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
    """Queue short PCM blocks so gain changes leave the track position intact."""

    def __init__(self, wav: bytes):
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
            self.pcm = source.readframes(frames)
        if not self.pcm:
            raise ValueError("Звуковая дорожка пуста.")
        self.offset = 0
        block_size = max(1, rate // 40) * channels * width
        self.format = Format(1, channels, rate, rate * channels * 2,
                             channels * 2, 16, 0)
        self.dll = ctypes.WinDLL("winmm")
        self.handle = ctypes.c_void_p()
        self.blocks = []
        code = self.dll.waveOutOpen(ctypes.byref(self.handle), wintypes.UINT(-1),
                                    ctypes.byref(self.format), None, None, 0)
        self._check(code)
        try:
            for _ in range(3):
                buffer = ctypes.create_string_buffer(block_size)
                header = Header(ctypes.addressof(buffer), block_size, 0, 0, 0, 0, None, 0)
                self._check(self.dll.waveOutPrepareHeader(self.handle,
                            ctypes.byref(header), ctypes.sizeof(header)))
                self.blocks.append((buffer, header))
        except Exception:
            self.close()
            raise

    @staticmethod
    def _check(code: int) -> None:
        if code:
            raise RuntimeError(f"Аудиоустройство недоступно (WinMM {code}).")

    def _next_block(self, size: int, volume: float) -> bytes:
        end = self.offset + size
        block = self.pcm[self.offset:end]
        remaining = size - len(block)
        if remaining:
            loops, tail = divmod(remaining, len(self.pcm))
            block += self.pcm * loops + self.pcm[:tail]
        self.offset = end % len(self.pcm)
        if volume == 0:
            return bytes(size)
        if volume == 1:
            return block
        samples = array.array("h", block)
        return array.array("h", (round(sample * volume) for sample in samples)).tobytes()

    def pump(self, volume: float) -> None:
        for buffer, header in self.blocks:
            if header.flags & 0x10:  # WHDR_INQUEUE
                continue
            pcm = self._next_block(header.length, volume)
            ctypes.memmove(buffer, pcm, header.length)
            self._check(self.dll.waveOutWrite(self.handle, ctypes.byref(header), ctypes.sizeof(header)))

    def close(self) -> None:
        if not self.handle:
            return
        self.dll.waveOutReset(self.handle)
        for _, header in self.blocks:
            self.dll.waveOutUnprepareHeader(self.handle, ctypes.byref(header), ctypes.sizeof(header))
        self.dll.waveOutClose(self.handle)
        self.handle = ctypes.c_void_p()


class LoadingAudio:
    """Asynchronous looping background music with a quiet failure path.

    Call ``start(game_root)`` once a game is found, ``set_volume(float)`` from
    the slider, and ``stop()`` on completion or window close. ``available``
    becomes true after playback opens; ``error`` explains unavailable audio.
    A missing audio device or codec must never prevent installation.
    """

    def __init__(self, volume: float = 0.35):
        self.volume = max(0.0, min(1.0, volume))
        self.available = False
        self.error: str | None = None
        self._lock = threading.RLock()
        self._cancel: threading.Event | None = None
        self._thread: threading.Thread | None = None

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
        try:
            from stream_bundle import open_bundle

            bundles = game_root / "GK12_Data/StreamingAssets/aa/StandaloneWindows64"
            candidates = sorted(bundles.glob("gk2_bgm_trial_assets_all_*.bundle"))
            if not candidates:
                candidates = sorted(bundles.glob("gk2_bgm_assets_all_*.bundle"))
            if not candidates:
                raise FileNotFoundError("Музыкальный бандл игры не найден.")
            with open_bundle(candidates[0]) as env:
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
            player = _WavePlayer(wav)
            del wav
            try:
                with self._lock:
                    if cancel.is_set():
                        return
                    player.pump(self.volume)
                    self.available = True
                while not cancel.wait(.01):
                    player.pump(self.volume)
            finally:
                player.close()
                with self._lock:
                    if self._cancel is cancel:
                        self.available = False
        except Exception as exc:
            with self._lock:
                if not cancel.is_set():
                    self.error = traceback.format_exc()

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))

    def stop(self) -> None:
        """Stop sound immediately; decoding and cleanup finish asynchronously."""
        with self._lock:
            if self._cancel:
                self._cancel.set()
            self.available = False

    def wait_closed(self, timeout: float = 5.0) -> None:
        """Optional shutdown hook for callers outside the UI thread."""
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout)
