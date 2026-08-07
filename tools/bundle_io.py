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


def write_string_tables(src: Path, values: dict[str, dict[int, str]], dst: Path) -> tuple[int, int, int]:
    """Переписать значения строковых таблиц в бандле и сохранить копию в dst.

    Таблицы — это MonoBehaviour с typetree, а не TextAsset, поэтому и путь другой:
    read_typetree / save_typetree. Ключи values — имя таблицы без языкового суффикса
    (`gk2_common_nametag`), внутри — {m_Id: новое значение}.

    Имя самой таблицы (`..._de`) не трогаем: игра ищет её по нему. Меняется только
    содержимое строк. Записи, которых в таблице-приёмнике нет, добавляются.

    Возвращает (таблиц изменено, строк переписано, размер бандла).
    """
    env = UnityPy.load(str(src))
    tables = rows = 0
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tree = obj.read_typetree()
        name = tree.get("m_Name", "")
        wanted = values.get(name.rsplit("_", 1)[0])
        if not wanted:
            continue

        table = tree["m_TableData"]
        seen = set()
        for row in table:
            if row["m_Id"] in wanted:
                new = wanted[row["m_Id"]]
                if row["m_Localized"] != new:
                    row["m_Localized"] = new
                    rows += 1
                seen.add(row["m_Id"])
        for key, new in wanted.items():
            if key not in seen:
                table.append({"m_Id": key, "m_Localized": new, "m_Metadata": {"m_Items": []}})
                rows += 1

        obj.save_typetree(tree)
        tables += 1

    missing = set(values) - {
        obj.read_typetree().get("m_Name", "").rsplit("_", 1)[0]
        for obj in UnityPy.load(str(src)).objects if obj.type.name == "MonoBehaviour"}
    if missing:
        raise KeyError(f"в бандле нет таких таблиц: {sorted(missing)[:5]}")

    blob = env.file.save(packer="lz4")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(blob)
    return tables, rows, len(blob)


def asset_paths(path: Path) -> dict[str, str]:
    """Имя файла в нижнем регистре -> полный путь ассета, как он записан в бандле.

    Нужно потому, что регистр в именах не всегда нижний (`sce1_LateDebug.bytes`),
    а при записи путь должен совпадать с бандлом в точности.
    """
    env = UnityPy.load(str(path))
    return {p.split("/")[-1].lower(): p for p in env.container}


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
