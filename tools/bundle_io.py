"""Чтение и запись TextAsset'ов внутри Unity-бандла.

Отдельный модуль, потому что тут два неочевидных места:

  * UnityPy отдаёт TextAsset.m_Script как str, декодированный из UTF-8 с surrogateescape.
    Наши данные — произвольные байты, поэтому кодировать обратно нужно ровно тем же
    способом, иначе часть байт потеряется.
  * env.file.save() по умолчанию пишет бандл без сжатия и раздувает его втрое.
    Игра такой проглотит, но Steam увидит лишний мегабайт разницы, поэтому упаковываем в LZ4.
"""
from __future__ import annotations

import io
from pathlib import Path

import UnityPy


def _to_bytes(script) -> bytes:
    return script.encode("utf-8", "surrogateescape") if isinstance(script, str) else bytes(script)


def read_text_assets(path: Path | io.BytesIO) -> dict[str, bytes]:
    """Полный путь ассета -> сырые байты. Путь сохраняем целиком: он нужен при записи."""
    env = UnityPy.load(path if isinstance(path, io.BytesIO) else str(path))
    return {p: _to_bytes(obj.read().m_Script) for p, obj in env.container.items()}


def write_text_assets(src: Path, replacements: dict[str, bytes], dst: Path) -> tuple[int, int]:
    """Переписать указанные ассеты в бандле и сохранить копию в dst.

    Ключи replacements — те же полные пути, что отдаёт read_text_assets.
    Возвращает (сколько заменено, размер получившегося бандла).
    """
    env = UnityPy.load(str(src))
    done = 0
    for path, obj in env.container.items():
        if path not in replacements:
            continue
        data = obj.read()
        data.m_Script = replacements[path].decode("utf-8", "surrogateescape")
        data.save()
        done += 1

    missing = set(replacements) - set(env.container)
    if missing:
        raise KeyError(f"в бандле нет таких ассетов: {sorted(missing)[:5]}")

    blob = env.file.save(packer="lz4")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(blob)
    return done, len(blob)
