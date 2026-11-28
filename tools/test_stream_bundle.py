"""Compatibility and failure tests for the installer's chunked UnityFS I/O."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import UnityPy
from UnityPy.streams import EndianBinaryReader, EndianBinaryWriter

import stream_bundle as sb


def serialized_fixture() -> bytes:
    """A v22 serialized file with one big object and one small object."""
    meta = EndianBinaryWriter(endian="<")
    meta.write_string_to_null("2022.3.17f1")
    meta.write_int(19)
    meta.write_boolean(False)
    meta.write_int(1)
    meta.write_int(49)  # TextAsset
    meta.write_boolean(False)
    meta.write_short(-1)
    meta.write_bytes(bytes(16))
    meta.write_int(2)
    first = bytes(range(256)) * 1025
    second = b"original"
    for path_id, offset, size in ((1, 0, len(first)), (2, len(first), len(second))):
        meta.align_stream(4)
        meta.write_long(path_id)
        meta.write_long(offset)
        meta.write_u_int(size)
        meta.write_int(0)
    meta.write_bytes(bytes(13))  # no script types, externals, ref types or user info
    writer = EndianBinaryWriter()
    data_offset = (48 + meta.Length + 15) & ~15
    writer.write_bytes(bytes(8))
    writer.write_u_int(22)
    writer.write_bytes(bytes(8))
    writer.write_u_int(meta.Length)
    writer.write_long(data_offset + len(first) + len(second))
    writer.write_long(data_offset)
    writer.write_long(0)
    writer.write_bytes(meta.bytes)
    writer.align_stream(16)
    writer.write_bytes(first)
    writer.write_bytes(second)
    return writer.bytes


class StreamBundleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.source = self.folder / "source.bundle"
        bundle = sb.StreamedBundle.__new__(sb.StreamedBundle)
        bundle.signature, bundle.version = "UnityFS", 8
        bundle.version_player, bundle.version_engine = "5.x.x", "2022.3.17f1"
        asset = EndianBinaryReader(serialized_fixture())
        asset.flags = 4
        self.resource = bytes(range(255)) * 1300
        raw = EndianBinaryReader(self.resource)
        raw.flags = 0
        bundle.files = {"CAB-example": asset, "CAB-example.resS": raw}
        sb.write_streamed(bundle, self.source, 1)

    def test_workers_produce_same_bundle_and_stock_unitypy_reads_it(self):
        low, high = self.folder / "low.bundle", self.folder / "high.bundle"
        with sb.open_bundle(self.source) as env:
            self.assertIsInstance(env.file, sb.StreamedBundle)
            asset = env.file.files["CAB-example"]
            asset.objects[2].set_raw_data(b"translated, length changed")
            expected = asset.save()
            sb.write_streamed(env.file, low, 1)
            sb.write_streamed(env.file, high, 4)
        self.assertEqual(low.read_bytes(), high.read_bytes())
        with low.open("rb") as stream:
            rebuilt = UnityPy.load(stream).file
            self.assertEqual(rebuilt.files["CAB-example"].reader.bytes, expected)
            self.assertEqual(rebuilt.files["CAB-example.resS"].bytes, self.resource)

    def test_failed_attempt_keeps_existing_output_and_source(self):
        result = self.folder / "result.bundle"
        result.write_bytes(b"previous")
        original = self.source.read_bytes()

        def fail(bundle, path, workers):
            path.write_bytes(b"incomplete")
            raise MemoryError()

        with (sb.open_bundle(self.source) as env,
              patch.object(sb, "compression_workers", return_value=2),
              patch.object(sb, "write_streamed", side_effect=fail) as write):
            with self.assertRaises(MemoryError):
                sb.save_bundle(env.file, result, source=self.source)
        self.assertEqual([call.args[2] for call in write.call_args_list], [2, 1])
        self.assertEqual(result.read_bytes(), b"previous")
        self.assertEqual(self.source.read_bytes(), original)
        self.assertCountEqual(self.folder.iterdir(), [self.source, result])

    def test_memory_pressure_restarts_the_bundle_with_one_worker(self):
        result = self.folder / "result.bundle"
        write_streamed = sb.write_streamed

        def fail_parallel(bundle, path, workers):
            if workers > 1:
                path.write_bytes(b"incomplete")
                raise MemoryError()
            write_streamed(bundle, path, workers)

        with (sb.open_bundle(self.source) as env,
              patch.object(sb, "compression_workers", return_value=4),
              patch.object(sb, "write_streamed", side_effect=fail_parallel) as write):
            sb.save_bundle(env.file, result, source=self.source)
        self.assertEqual([call.args[2] for call in write.call_args_list], [4, 1])
        self.assertEqual(result.read_bytes(), self.source.read_bytes())
        self.assertCountEqual(self.folder.iterdir(), [self.source, result])

    def test_output_must_not_alias_input(self):
        alias = self.folder / "hardlink.bundle"
        alias.hardlink_to(self.source)
        original = self.source.read_bytes()
        with sb.open_bundle(self.source) as env:
            for output in (self.source, alias):
                with self.assertRaises(ValueError):
                    sb.save_bundle(env.file, output, source=self.source)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(alias.read_bytes(), original)

    def test_worker_limit_uses_available_memory(self):
        with (patch.object(sb.os, "process_cpu_count", return_value=12, create=True),
              patch.object(sb, "available_memory", side_effect=[300 * sb.MIB, 3 * 1024 * sb.MIB])):
            self.assertEqual(sb.compression_workers(), 1)
            self.assertEqual(sb.compression_workers(), 8)

    def test_large_pixel_hash_preserves_row_order_and_alpha(self):
        from picture_layer import pixels_sha

        image = Image.linear_gradient("L").resize((1600, 900)).convert("RGBA")
        image.putalpha(Image.effect_noise(image.size, 64).convert("L"))
        self.assertEqual(pixels_sha(image), hashlib.sha256(image.tobytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
