"""Плашка нейросети через Codex: отдать вырезку и задание, забрать рисунок.

Курс 23 сентября 2026 (правило №13, скилл `/graphics`, шаг 3): нейросеть
редактирует **всю вырезку вместе с фоном**, вклеивает `paste_art.py` ключом
`плашка`. До 8 октября 2026 вырезку пользователь носил в ChatGPT руками;
теперь её отдаёт этот скрипт — `codex exec` со встроенным генератором
картинок (`image_generation`, вход ChatGPT, тот же, что у пользователя).

Как это устроено, проверено 8 октября 2026 на вывеске `cut01_009`:

* `codex exec -i <вырезка>` с заданием на stdin; Codex зовёт генератор сам.
  Песочница у него только на чтение — скопировать файл он не может,
  и не нужно: рисунок ложится в `~/.codex/generated_images/<сессия>/`,
  номер сессии печатается в шапке вывода (`session id: …`).
* Размер рисунка свой (1670×720 → 1909×824), кадр тот же. Приводит к размеру
  и совмещает `paste_art.py`, здесь ничего не трогается.

    python tools/codex_image.py <картинка.png> <задание.txt> <куда.png> [--box x0 y0 x1 y1]

`--box` — вырезка из картинки (та же рамка идёт в задание вклейки ключом
`вырезка`); без него — картинка целиком. Прозрачное кладётся на серый 128,
мелкая вырезка увеличивается до 1024 по длинной стороне: генератор рисует
крупно, а карточку улики 300×300 видит иначе слишком грубо. Отправленная
вырезка остаётся рядом — `<куда>_вход.png`.

Пишет рисунок в `<куда.png>`, вывод Codex — рядом в `<куда>.log`.
Код 0 — рисунок есть; 1 — Codex отработал, но рисунка не оставил.

Очередь — `work/graphics_ai/codex.json`: `{"_общее": "хвост каждого задания",
"<имя>": {"дело", "box", "задание"}}`. Рисунок ложится в
`work/graphics_ai/<дело>/<имя>_codex_<N>.png`, N — следующий свободный
(повтор не затирает прошлую пробу):

    python tools/codex_image.py --queue work/graphics_ai/codex.json --jobs 3
    python tools/codex_image.py --queue work/graphics_ai/codex.json --only cut01_009

Образец и основа (9 октября 2026, правило №13 «одно изображение в разных кадрах»).
`образец` — список картинок-эталонов, которые прикладываются к заданию вслед
за вырезкой: принятая русская улика, по которой нейросеть ставит ту же вывеску
в другом кадре. Элемент — путь от корня проекта или `{"файл", "box"}`; в CLI —
`--ref <файл> [--ref …]`. `основа` — что редактировать вместо английского
оригинала: наш черновик, когда исправить надо одну букву (цирк `cut01_009`:
«Б» → «Е» вышло только так). Первой всегда идёт вырезка — её и правят.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

HEADER = (
    "Use your built-in image generation tool to EDIT the attached image. "
    "Do not draw anything with code (no Python, PIL, canvas), do not try to "
    "copy or save files — just generate the edited image once and stop.\n\n"
)
GENERATED = Path.home() / ".codex" / "generated_images"


def make_input(src: Path, box, dest: Path) -> Path:
    """Вырезка на сером, увеличенная до 1024 по длинной стороне, если мельче."""
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    grey = Image.new("RGBA", im.size, (128, 128, 128, 255))
    grey.alpha_composite(im)
    crop = grey.convert("RGB").crop(tuple(box) if box else (0, 0, *im.size))
    k = 1024 / max(crop.size)
    if k > 1:
        crop = crop.resize((round(crop.width * k), round(crop.height * k)), Image.LANCZOS)
    out = dest.with_name(dest.stem + "_вход.png")
    crop.save(out)
    return out


REF_NOTE = (
    "The FIRST attached image is the one to edit; output only its edited version. "
    "The other attached images are REFERENCES described in the task below (usually the "
    "approved Russian version of the same object — copy its lettering exactly); "
    "do not output them.\n\n"
)


def make_refs(refs, dest: Path) -> list[Path]:
    """Образцы рядом с рисунком: `<куда>_образец<N>.png` (вырезка `box`, если задана)."""
    from PIL import Image
    out = []
    for n, ref in enumerate(refs or [], 1):
        spec = ref if isinstance(ref, dict) else {"файл": ref}
        im = Image.open(spec["файл"]).convert("RGBA")
        grey = Image.new("RGBA", im.size, (128, 128, 128, 255))
        grey.alpha_composite(im)
        im = grey.convert("RGB")
        if spec.get("box"):
            im = im.crop(tuple(spec["box"]))
        k = 1024 / max(im.size)
        if k > 1:
            im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
        path = dest.with_name(f"{dest.stem}_образец{n}.png")
        im.save(path)
        out.append(path)
    return out


def run(crop: Path, prompt: str, dest: Path, timeout: int = 1200, refs=None) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    log = dest.with_suffix(".log")
    images = ["-i", str(crop.resolve())]
    for r in refs or []:
        images += ["-i", str(Path(r).resolve())]
    proc = subprocess.run(
        ["codex", "exec", "--skip-git-repo-check", "-s", "read-only", *images, "-"],
        input=(HEADER + (REF_NOTE if refs else "") + prompt).encode("utf-8"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=timeout, shell=(sys.platform == "win32"),
    )
    text = proc.stdout.decode("utf-8", "replace")
    log.write_text(text, encoding="utf-8")
    m = re.search(r"session id:\s*([0-9a-f-]{36})", text)
    if not m:
        print(f"  нет номера сессии в выводе Codex (код {proc.returncode}), см. {log}")
        return 1
    folder = GENERATED / m.group(1)
    pics = sorted(folder.glob("*.png"), key=lambda p: p.stat().st_mtime) if folder.exists() else []
    if not pics:
        print(f"  Codex не оставил рисунка (сессия {m.group(1)}), см. {log}")
        return 1
    shutil.copyfile(pics[-1], dest)
    print(f"  {dest} <- {pics[-1].name} (сессия {m.group(1)}, рисунков {len(pics)})")
    return 0


def queue(path: Path, only: list[str] | None, jobs: int) -> int:
    import json
    from concurrent.futures import ThreadPoolExecutor
    q = json.loads(path.read_text(encoding="utf-8"))
    tail = q.get("_общее", "")
    todo = []
    for name, job in q.items():
        if name.startswith("_") or (only and name not in only):
            continue
        folder = path.parent / job["дело"]
        n = 1
        while (folder / f"{name}_codex_{n}.png").exists() or (folder / f"{name}_codex_{n}.log").exists():
            n += 1
        dest = folder / f"{name}_codex_{n}.png"
        src = Path(job["основа"]) if job.get("основа") else \
            Path("work/graphics_en") / job["дело"] / f"{job.get('картинка', name)}.png"
        folder.mkdir(parents=True, exist_ok=True)
        crop = make_input(src, job.get("box"), dest)
        refs = make_refs(job.get("образец"), dest)
        todo.append((crop, job["задание"].rstrip() + "\n\n" + tail, dest, 1200, refs))
    with ThreadPoolExecutor(max(1, jobs)) as ex:
        codes = list(ex.map(lambda t: run(*t), todo))
    print(f"рисунков: {codes.count(0)} из {len(codes)}")
    return 0 if codes and not any(codes) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("picture", type=Path, nargs="?", help="картинка оригинала (work/graphics_en/<дело>/<имя>.png)")
    ap.add_argument("prompt", type=Path, nargs="?", help="задание нейросети, текст UTF-8")
    ap.add_argument("dest", type=Path, nargs="?", help="куда положить рисунок")
    ap.add_argument("--queue", type=Path, help="очередь заданий (work/graphics_ai/codex.json)")
    ap.add_argument("--only", nargs="+", help="только эти имена из очереди")
    ap.add_argument("--jobs", type=int, default=2, help="сколько Codex разом")
    ap.add_argument("--box", type=int, nargs=4, help="вырезка x0 y0 x1 y1")
    ap.add_argument("--timeout", type=int, default=1200)
    ap.add_argument("--ref", type=Path, action="append", help="образец (эталон) — приложить вслед за вырезкой")
    a = ap.parse_args()
    if a.queue:
        return queue(a.queue, a.only, a.jobs)
    crop = make_input(a.picture, a.box, a.dest)
    refs = make_refs([str(r) for r in a.ref or []], a.dest)
    return run(crop, a.prompt.read_text(encoding="utf-8"), a.dest, a.timeout, refs)


if __name__ == "__main__":
    raise SystemExit(main())
