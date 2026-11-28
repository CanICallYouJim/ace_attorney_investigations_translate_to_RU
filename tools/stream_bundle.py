"""Read and rebuild modern UnityFS bundles with bounded I/O buffers."""
from __future__ import annotations

from bisect import bisect_right
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from itertools import islice
import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

import lz4.block
import UnityPy
from UnityPy.files.BundleFile import BundleFile, DirectoryInfoFS
from UnityPy.files.SerializedFile import SerializedFile
from UnityPy.helpers.ImportHelper import parse_file
from UnityPy.streams import EndianBinaryReader, EndianBinaryWriter


MIB = 1024**2
BLOCK_SIZE = 128 * 1024
BLOCKS_AT_END = 0x80
PADDING_AT_START = 0x200
DIR_COMBINED = 0x40
LZ4 = 2


class UnsupportedBundle(Exception):
    """The bundle needs UnityPy's general-purpose reader."""


class BlockSource:
    """Compressed block offsets and a small cache of recently read blocks."""

    def __init__(self, reader, blocks, physical_end):
        self.reader = reader
        self.blocks = []
        self.starts = []
        self.length = 0
        self.cache = OrderedDict()
        physical = reader.Position
        for size, packed, codec in blocks:
            if not size or not packed or (codec == 0 and size != packed):
                raise ValueError("Повреждён размер блока UnityFS.")
            if codec not in (0, 2, 3) or (codec and size > 8 * MIB):
                raise UnsupportedBundle()
            self.starts.append(self.length)
            self.blocks.append((physical, size, packed, codec))
            self.length += size
            physical += packed
        if physical != physical_end:
            raise ValueError("Размер блоков не совпадает с размером UnityFS.")

    def read(self, offset, size):
        end = offset + size
        pieces = []
        index = bisect_right(self.starts, offset) - 1
        while offset < end:
            physical, raw_size, packed, codec = self.blocks[index]
            inner = offset - self.starts[index]
            take = min(raw_size - inner, end - offset)
            if codec == 0:
                self.reader.Position = physical + inner
                part = self.reader.read_bytes(take)
                if len(part) != take:
                    raise EOFError("Неполный несжатый блок UnityFS.")
            else:
                data = self.cache.get(index)
                if data is None:
                    self.reader.Position = physical
                    data = lz4.block.decompress(self.reader.read_bytes(packed), uncompressed_size=raw_size)
                    if len(data) != raw_size:
                        raise ValueError("Неверная длина распакованного блока UnityFS.")
                    self.cache[index] = data
                    if len(self.cache) > 8:
                        self.cache.popitem(last=False)
                else:
                    self.cache.move_to_end(index)
                part = data[inner:inner + take]
            pieces.append(part)
            offset += take
            index += 1
        return b"".join(pieces)


class NodeStream:
    """File-like view into a single node, with its own seek position."""

    def __init__(self, source, offset, length):
        self.source = source
        self.offset = offset
        self.length = length
        self.position = 0

    def seek(self, offset, whence=0):
        position = (0, self.position, self.length)[whence] + offset
        if position < 0:
            raise ValueError("Отрицательное смещение в узле UnityFS.")
        self.position = position
        return position

    def tell(self):
        return self.position

    def read(self, size=-1):
        available = max(0, self.length - self.position)
        size = available if size is None or size < 0 else min(available, size)
        data = self.source.read(self.offset + self.position, size)
        self.position += len(data)
        return data


class StreamedBundle(BundleFile):
    def read_fs(self, reader):
        if self.signature != "UnityFS" or self.version not in (7, 8) or self.parse_version() < (2022, 1, 1):
            raise UnsupportedBundle()
        file_size = reader.read_long()
        packed_size = reader.read_u_int()
        raw_size = reader.read_u_int()
        flags = reader.read_u_int()
        reader.align_stream(16)
        codec = flags & 0x3F
        known_flags = DIR_COMBINED | BLOCKS_AT_END | PADDING_AT_START | 0x3F
        if not flags & DIR_COMBINED or flags & ~known_flags or codec not in (0, 2, 3):
            raise UnsupportedBundle()
        header_end = reader.Position
        index_at_end = flags & BLOCKS_AT_END
        index_offset = file_size - packed_size if index_at_end else header_end
        if file_size != reader.Length or not header_end <= index_offset <= file_size - packed_size:
            raise ValueError("Неверное смещение таблицы UnityFS.")
        reader.Position = index_offset
        packed = reader.read_bytes(packed_size)
        data = lz4.block.decompress(packed, uncompressed_size=raw_size) if codec else packed
        if len(data) != raw_size:
            raise ValueError("Неверная длина таблицы UnityFS.")
        index = EndianBinaryReader(data)
        index.Position = 16
        blocks = [(index.read_u_int(), index.read_u_int(), index.read_u_short())
                  for _ in range(index.read_int())]
        nodes = [DirectoryInfoFS(index.read_long(), index.read_long(), index.read_u_int(),
                                 index.read_string_to_null()) for _ in range(index.read_int())]
        reader.Position = header_end if index_at_end else header_end + packed_size
        if flags & PADDING_AT_START:
            reader.align_stream(16)
        self.source = BlockSource(reader, blocks, index_offset if index_at_end else file_size)
        return nodes, self.source

    def read_files(self, source, nodes):
        for node in nodes:
            if not 0 <= node.offset <= node.offset + node.size <= source.length:
                raise ValueError("Узел UnityFS выходит за границы бандла.")
            reader = EndianBinaryReader(NodeStream(source, node.offset, node.size))
            # Resource nodes contain raw bytes and can start with any signature.
            file = reader if node.path.endswith((".resS", ".resource")) else parse_file(reader, self, node.path)
            if not isinstance(file, (EndianBinaryReader, SerializedFile)):
                raise UnsupportedBundle()
            file.flags = node.flags
            self.environment.register_cab(node.path, file)
            self.files[node.path] = file


@contextmanager
def open_bundle(path):
    env = UnityPy.Environment(path=str(path.parent))
    with path.open("rb") as stream:
        reader = EndianBinaryReader(stream)
        try:
            if reader.read_bytes(8) != b"UnityFS\0":
                raise UnsupportedBundle()
            reader.Position = 0
            bundle = StreamedBundle(reader, env, path.name)
        except UnsupportedBundle:
            stream.seek(0)
            # Keep use of the current reader for legacy and encrypted bundles.
            env = UnityPy.Environment(path=str(path.parent))
            bundle = env.load_file(stream, name=path.name)
        env.files[path.name] = env.file = bundle
        try:
            yield env
        finally:
            if isinstance(bundle, StreamedBundle):
                bundle.source.cache.clear()


def read_parts(reader, offset, size):
    reader.Position = offset
    while size:
        part = reader.read_bytes(min(size, BLOCK_SIZE))
        if not part:
            raise EOFError("Неполные данные узла UnityFS.")
        size -= len(part)
        yield part


def serialized_parts(asset):
    header = asset.header
    if header.version != 22:
        yield asset.save()
        return
    meta = EndianBinaryWriter(endian=header.endian)
    meta.write_string_to_null(asset.unity_version)
    meta.write_int(asset._m_target_platform)
    meta.write_boolean(asset._enable_type_tree)
    meta.write_int(len(asset.types))
    for typ in asset.types:
        typ.write(asset, meta, False)

    objects = sorted(asset.objects.values(), key=lambda obj: obj.path_id)
    meta.write_int(len(objects))
    data_size = 0
    for obj in objects:
        size = len(obj.data) if obj.data is not None else obj.byte_size
        meta.align_stream(4)
        meta.write_long(obj.path_id)
        meta.write_long(data_size)
        meta.write_u_int(size)
        meta.write_int(obj.type_id)
        data_size += (size + 7) & ~7

    meta.write_int(len(asset.script_types))
    for identifier in asset.script_types:
        identifier.write(header, meta)
    meta.write_int(len(asset.externals))
    for external in asset.externals:
        external.write(header, meta)
    meta.write_int(len(asset.ref_types))
    for typ in asset.ref_types:
        typ.write(asset, meta, True)
    meta.write_string_to_null(asset.userInformation)
    metadata = meta.bytes

    writer = EndianBinaryWriter()
    data_offset = (48 + len(metadata) + 15) & ~15
    writer.write_u_int(0)
    writer.write_u_int(0)
    writer.write_u_int(header.version)
    writer.write_u_int(0)
    writer.write_boolean(header.endian == ">")
    writer.write_bytes(header.reserved)
    writer.write_u_int(len(metadata))
    writer.write_long(data_offset + data_size)
    writer.write_long(data_offset)
    writer.write_long(asset.unknown)
    writer.write_bytes(metadata)
    writer.align_stream(16)
    yield writer.bytes
    for obj in objects:
        if obj.data is None:
            yield from read_parts(obj.reader, obj.byte_start, obj.byte_size)
            size = obj.byte_size
        else:
            yield obj.data
            size = len(obj.data)
        yield b"\0" * (-size % 8)


def node_parts(file):
    if isinstance(file, SerializedFile):
        if file.is_changed:
            yield from serialized_parts(file)
            return
        file = file.reader
    if isinstance(file, EndianBinaryWriter):
        length = file.Length
        file.stream.seek(0)
        file = EndianBinaryReader(file.stream, endian=file.endian)
        yield from read_parts(file, 0, length)
    else:
        yield from read_parts(file, 0, file.Length)


def bundle_blocks(bundle, nodes):
    buffer = bytearray()
    offset = 0
    for name, file in bundle.files.items():
        length = 0
        for part in node_parts(file):
            length += len(part)
            view = memoryview(part)
            while view:
                take = min(len(view), BLOCK_SIZE - len(buffer))
                buffer.extend(view[:take])
                view = view[take:]
                if len(buffer) == BLOCK_SIZE:
                    yield bytes(buffer)
                    buffer.clear()
        nodes.append(DirectoryInfoFS(offset, length, file.flags, name))
        offset += length
    if buffer:
        yield bytes(buffer)


def available_memory():
    if sys.platform != "win32":
        return 0
    import ctypes as c

    class MemoryStatus(c.Structure):
        _fields_ = [
            ("length", c.c_uint32), ("load", c.c_uint32),
            ("total_phys", c.c_uint64), ("avail_phys", c.c_uint64),
            ("total_page_file", c.c_uint64), ("avail_page_file", c.c_uint64),
            ("total_virtual", c.c_uint64), ("avail_virtual", c.c_uint64),
            ("avail_extended_virtual", c.c_uint64),
        ]

    status = MemoryStatus()
    status.length = c.sizeof(status)
    if c.windll.kernel32.GlobalMemoryStatusEx(c.byref(status)):
        return min(status.avail_phys, status.avail_page_file)
    return 0


def compression_workers():
    # Keep a reserve for UnityPy's object metadata, texture edits and the OS.
    available = available_memory()
    cpu = getattr(os, "process_cpu_count", os.cpu_count)() or 1
    return min(cpu, 8, max(1, (available - 512 * MIB) // (256 * MIB)))


def pack_block(block):
    data = lz4.block.compress(block, mode="high_compression", compression=3, store_size=False)
    return (len(block), data, LZ4) if len(data) < len(block) else (len(block), block, 0)


def write_streamed(bundle, path, workers):
    nodes = []
    blocks = []
    with path.open("wb") as output:
        header = EndianBinaryWriter(output)
        header.write_string_to_null(bundle.signature)
        header.write_u_int(bundle.version)
        header.write_string_to_null(bundle.version_player)
        header.write_string_to_null(bundle.version_engine)
        header_offset = header.Position
        header.write_bytes(b"\0" * 20)
        header.align_stream(16)

        source = bundle_blocks(bundle, nodes)
        pool = ThreadPoolExecutor(max_workers=workers) if workers > 1 else nullcontext()
        with pool as executor:
            while batch := list(islice(source, workers * 16)):
                packed_blocks = executor.map(pack_block, batch) if executor else map(pack_block, batch)
                for raw_size, packed, codec in packed_blocks:
                    output.write(packed)
                    blocks.append((raw_size, len(packed), codec))

        index = EndianBinaryWriter(b"\0" * 16)
        index.write_int(len(blocks))
        for raw_size, packed_size, codec in blocks:
            index.write_u_int(raw_size)
            index.write_u_int(packed_size)
            index.write_u_short(codec)
        index.write_int(len(nodes))
        for node in nodes:
            index.write_long(node.offset)
            index.write_long(node.size)
            index.write_u_int(node.flags)
            index.write_string_to_null(node.path)
        data = index.bytes
        packed = lz4.block.compress(data, store_size=False)
        output.write(packed)
        file_size = output.tell()
        header.Position = header_offset
        header.write_long(file_size)
        header.write_u_int(len(packed))
        header.write_u_int(len(data))
        header.write_u_int(DIR_COMBINED | BLOCKS_AT_END | LZ4)


def save_bundle(bundle, path, *, source):
    if path.resolve() == source.resolve() or (path.exists() and path.samefile(source)):
        raise ValueError("Папка для сборки должна отличаться от папки исходных файлов игры.")
    with NamedTemporaryFile(dir=path.parent, prefix=".aai2-bundle-", suffix=".tmp", delete=False) as file:
        temporary = Path(file.name)
    try:
        if not isinstance(bundle, StreamedBundle):
            temporary.write_bytes(bundle.save(packer="lz4"))
        else:
            workers = compression_workers()
            try:
                write_streamed(bundle, temporary, workers)
            except (MemoryError, RuntimeError) as exc:
                # Leave the exception scope before retrying so the old
                # workers, buffers and traceback can be released.
                if workers == 1 or (isinstance(exc, RuntimeError) and str(exc) != "can't start new thread"):
                    raise
                workers = 0
            if not workers:
                write_streamed(bundle, temporary, 1)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
