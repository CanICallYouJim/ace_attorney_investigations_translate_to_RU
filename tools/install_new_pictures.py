"""Быстрая установка картинок: в игру уходят только новые и изменённые, остальное не трогается.

Пара к `inject_localized.py --install` (`make graphics-ru`). Тот на каждый запуск
собирает **из `backup/`** все бандлы, где есть хоть одна русская картинка, и заново
упаковывает в BC7 все русские картинки — около семидесяти, это минуты. Этот берёт
**живой** бандл, в котором прежние русские картинки уже стоят, и перепаковывает
только изменившиеся; бандлы без изменений не пишутся вовсе. Просьба пользователя
от 2 октября 2026: «новые фотки ставить только, не переписывая все — очень долго».
Старый путь остаётся запасным: что-то пошло не так — `make graphics-ru` собирает
всё начисто из оригиналов и лечит любое наслоение.

    .venv\\Scripts\\python.exe tools\\install_new_pictures.py              # поставить изменённые
    .venv\\Scripts\\python.exe tools\\install_new_pictures.py --dry        # только показать, что поставит
    .venv\\Scripts\\python.exe tools\\install_new_pictures.py cut00_01e    # поставить названные, даже без изменений

Как узнаёт изменённые. После записи в `work/build_assets/installed_pictures.json`
ложатся хэш каждой поставленной PNG и хэш живого бандла. Картинка считается
стоящей, если хэш PNG прежний **и** бандл с тех пор никто не переписывал. Иначе
(новая картинка, правленая PNG, бандл переписан `make graphics-ru` или
`restore.py`) — живая текстура раскодируется и сравнивается с PNG по пикселям:
BC7 теряет немного, поэтому «другая» — это больше `MOVED` пикселей, отличных
больше чем на `TOL` уровней.

Где живой бандл ещё оригинальный (после `restore.py`, или его ни разу не писали) —
в нём нет подмены немецких адресов на английские, и одну картинку туда не вставить:
такой бандл собирается целиком из `backup/` тем же кодом, что у `inject_localized.py`
(`patch`), со всеми русскими картинками этого бандла.

Механика сверяется после записи, как у полной установки: русские пиксели —
в **немецком** объекте (раскодировано из записанного бандла и сравнено с PNG),
английская текстура той же картинки равна оригиналу из `backup/` до бита.
Плашки ситуации и заставка «Возражение» сюда не ходят — у них своя таблица
и свой атлас: изменились — `make graphics-ru`.

Слой патчера (`make layers`) отдельно: этот инструмент ставит картинки только
в свою игру.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import UnityPy
from PIL import Image

from common import BACKUP, BUNDLES, WORK, game_is_running, load_json, save_json, sha256
from inject_localized import patch
from layer_localized import index, original, stored_flipped
from picture_layer import FLIP, german_object, sprites_by_key, write_bundle
from swap_localized import BUILD, MANIFEST, plan_env, register_backup

STATE = BUILD / "installed_pictures.json"
TOL = 48          # уровней: дальше этого BC7 пиксель не уводит, правка — уводит
MOVED = 40        # пикселей: столько «других» — уже правка, а не шум упаковки


def pngs() -> dict[str, Path]:
    """Русские картинки на текстуру: work/graphics_ru/<дело>/*.png, без плашек и заставки."""
    found: dict[str, Path] = {}
    for png in sorted((WORK / "graphics_ru").rglob("*.png")):
        if png.parent.name == "ui":
            continue
        if png.stem in found:
            sys.exit(f"одна картинка лежит дважды: {found[png.stem]} и {png}")
        found[png.stem] = png
    return found


def as_stored(png: Path, tex, flipped: bool) -> Image.Image:
    """PNG в том виде, как её хранит бандл: размер текстуры и сторона."""
    img = Image.open(png).convert("RGBA")
    if img.size != (tex.m_Width, tex.m_Height):
        img = img.resize((tex.m_Width, tex.m_Height), Image.LANCZOS)
    return img.transpose(FLIP) if flipped else img


def differs(a: Image.Image, b: Image.Image) -> int:
    """Сколько пикселей отличаются больше чем на TOL уровней (по худшему каналу)."""
    if a.size != b.size:
        return a.size[0] * a.size[1]
    d = np.abs(np.asarray(a.convert("RGBA"), dtype=np.int16) - np.asarray(b.convert("RGBA"), dtype=np.int16))
    return int((d.max(axis=2) > TOL).sum())


def entries_of(env) -> dict:
    ab = next(o for o in env.objects if o.type.name == "AssetBundle")
    return {k: v for k, v in ab.read_typetree()["m_Container"]}


def is_built(bundle_name: str) -> bool:
    """Живой бандл уже собран нашей установкой (есть бэкап и живой от него отличается)."""
    saved = BACKUP / bundle_name
    manifest = load_json(MANIFEST, default={}) or {}
    key = f"asset_{bundle_name.split('_assets_all_')[0]}"
    return saved.exists() and key in manifest and sha256(BUNDLES / bundle_name) != manifest[key]["sha256"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="поставить эти картинки, даже если они не менялись")
    ap.add_argument("--dry", action="store_true", help="ничего не писать: показать, что изменилось")
    ap.add_argument("--raw", action="store_true", help="класть несжатым (RGBA32), как у inject_localized.py")
    args = ap.parse_args()

    files = pngs()
    unknown = [n for n in args.names if n not in files]
    if unknown:
        sys.exit(f"нет таких PNG в work/graphics_ru: {', '.join(unknown)}")
    idx = index()
    state = load_json(STATE, default={}) or {}
    state.setdefault("pictures", {})
    state.setdefault("bundles", {})

    by_bundle: dict[str, list[tuple[str, str]]] = defaultdict(list)    # бандл -> [(имя, адрес)]
    for name in files:
        for bundle_name, key, _ in idx.get(name, []):
            if (BUNDLES / bundle_name).exists():
                by_bundle[bundle_name].append((name, key))

    png_sha = {name: sha256(path) for name, path in files.items()}
    live_sha = {b: sha256(BUNDLES / b) for b in by_bundle}

    todo: dict[str, list[tuple[str, str]]] = defaultdict(list)
    whole: list[str] = []
    checked = 0
    for bundle_name, items in sorted(by_bundle.items()):
        if not is_built(bundle_name):
            whole.append(bundle_name)
            continue
        trusted = state["bundles"].get(bundle_name) == live_sha[bundle_name]
        live = orig = None
        for name, key in items:
            if name in args.names:
                todo[bundle_name].append((name, key))
                continue
            if trusted and state["pictures"].get(name) == png_sha[name]:
                continue
            # Не уверены — раскодировать живую текстуру и сравнить с PNG
            if live is None:
                live = UnityPy.load(str(BUNDLES / bundle_name))
                orig = UnityPy.load(str(original(bundle_name)))
                entries = entries_of(live)
                pairs = dict(plan_env(live))
            tex = german_object(live, entries, key, pairs.get(key)).read()
            img = as_stored(files[name], tex, stored_flipped(orig, key, Image.open(files[name]).convert("RGBA")))
            checked += 1
            if differs(img, tex.image) > MOVED:
                todo[bundle_name].append((name, key))
            else:
                state["pictures"][name] = png_sha[name]
        if bundle_name not in todo:
            state["bundles"][bundle_name] = live_sha[bundle_name]    # всё в нём сверено и стоит

    if checked:
        print(f"сверено с живыми текстурами: {checked}")
    for bundle_name in whole:
        names = sorted({n for n, _ in by_bundle[bundle_name]})
        print(f"  {bundle_name.split('_assets_all_')[0]:44} бандл оригинальный — соберу целиком "
              f"из backup/, картинок: {len(names)}")
    for bundle_name, items in sorted(todo.items()):
        print(f"  {bundle_name.split('_assets_all_')[0]:44} поставить: "
              + ", ".join(sorted({n for n, _ in items})))
    if not todo and not whole:
        print("все русские картинки уже стоят — ставить нечего")
        save_json(STATE, state)
        return 0
    if args.dry:
        return 0
    if game_is_running():
        sys.exit("GK12.exe запущен — закрой игру, файлы бандлов заблокированы.")

    BUILD.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    for bundle_name in sorted(set(todo) | set(whole)):
        if bundle_name in whole:
            blob, notes, _ = patch(bundle_name, [(k, files[n]) for n, k in by_bundle[bundle_name]], args.raw)
            written = by_bundle[bundle_name]
        else:
            env = UnityPy.load(str(BUNDLES / bundle_name))
            orig = UnityPy.load(str(original(bundle_name)))
            sprites = sprites_by_key(env)
            entries = entries_of(env)
            pairs = dict(plan_env(env))
            pictures = {}
            notes = []
            for name, key in todo[bundle_name]:
                if key in sprites:
                    problems.append(f"{name}: это спрайт-плашка — ставить через make graphics-ru")
                    continue
                tex = german_object(env, entries, key, pairs.get(key)).read()
                face = Image.open(files[name]).convert("RGBA")
                flipped = stored_flipped(orig, key, face)
                if flipped:
                    notes.append(f"{name}: бандл хранит её вверх ногами — перевернул")
                pictures[key] = as_stored(files[name], tex, flipped)
            # Пары — только для своих адресов: по ним `german_object` найдёт немецкий
            # объект, даже если адрес картинки ещё уведён на английский. Остальные
            # адреса живого бандла уже подменены прежней установкой — их не трогать.
            blob, more = write_bundle(env, [(k, pairs[k]) for k in pictures if k in pairs], pictures, args.raw)
            notes += more
            written = [(n, k) for n, k in todo[bundle_name] if k in pictures]
        out = BUILD / bundle_name
        out.write_bytes(blob)

        # Сверка механики по записанному, до копирования в игру
        env = UnityPy.load(str(out))
        orig = UnityPy.load(str(original(bundle_name)))
        entries = entries_of(env)
        pairs = dict(plan_env(env))
        bad = []
        for name, key in written:
            obj = german_object(env, entries, key, pairs.get(key))
            if entries[key]["asset"]["m_PathID"] != obj.path_id:
                bad.append(f"{name}: адрес _ger ведёт не на немецкий объект")
            face = Image.open(files[name]).convert("RGBA")
            tex = obj.read()
            want = as_stored(files[name], tex, stored_flipped(orig, key, face))
            if differs(want, tex.image) > MOVED:
                bad.append(f"{name}: в немецкой текстуре не та картинка")
            eng = pairs.get(key)
            if eng and eng in orig.container:
                if np.asarray(env.container[eng].read().image).tobytes() != \
                        np.asarray(orig.container[eng].read().image).tobytes():
                    bad.append(f"{name}: английская текстура изменилась против backup/")
        short = bundle_name.split('_assets_all_')[0]
        print(f"  {short:44} записано картинок: {len(written)}; {len(blob)/1024/1024:.1f} МБ")
        for note in notes:
            print(f"      {note}")
        if bad:
            problems += [f"{short}: {b}" for b in bad]
            print("      НЕ установлен — сверка не прошла")
            continue
        register_backup(bundle_name, BUNDLES / bundle_name)
        shutil.copy2(out, BUNDLES / bundle_name)
        print("      установлен, сверка: немецкая текстура = PNG, английская = backup/")
        state["bundles"][bundle_name] = sha256(BUNDLES / bundle_name)
        for name, _ in by_bundle[bundle_name]:
            state["pictures"][name] = png_sha[name]

    save_json(STATE, state)
    for p in problems:
        print(f"  БЕДА: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
