"""Выгрузить из игры то, без чего сплошная вычитка вслепую: говорящих и семь языков.

Говорящий (код E101) и тексты других локализаций живут только в бандлах игры,
а бандлов нет там, где вычитку ведут агенты, — в облачном контейнере. Поэтому
здесь, на машине с игрой, всё нужное вынимается один раз в `work/review/`:

    work/review/speakers.json      id сегмента -> слот говорящего ("0000", "0002", ...)
    work/review/locales/<lang>.json id сегмента -> текст реплики на этом языке
    work/review/meta.json          когда выгружено, сколько, где разошлась разбивка

Сами файлы игры в репозиторий не попадают — только извлечённый текст реплик.
Идентификаторы те же, что в `work/case{N}.json` (арифметика extract.py), говорящий
определяется как в who.py: если в сегменте нет E101, говорит тот же, что раньше
в этом блоке. Тексты других языков берутся через polyglot.resolve — тот же код,
что у `polyglot.py`, поэтому и расхождения разбивки те же: такие места помечены
в meta.json и в тексте, сверять их глазами.

    make review-pack
    python tools/export_review_pack.py
    python tools/export_review_pack.py --langs eng,fre,ger    # не все языки
    python tools/export_review_pack.py --no-push              # только выгрузить, не пушить

**Куда уходит.** Пакет нужен в облаке, а `dev` для него неподходящее место: 8 файлов
по нескольку мегабайт и смена при каждой выгрузке. Поэтому после выгрузки скрипт сам
коммитит `work/review/` в отдельную ветку `review-pack` и пушит её в `origin`.
Коммит собирается через временный индекс (`GIT_INDEX_FILE`) — рабочее дерево,
текущая ветка и индекс пользователя не трогаются, даже если в дереве идёт чужая
работа (CLAUDE.md, «Рабочее дерево может быть общим»). В `dev` пакет не попадает:
`work/review/` в `.gitignore`. Новый коммит ставится поверх прежнего `review-pack`,
без force-push. Забрать в облаке:

    git fetch origin review-pack
    git archive FETCH_HEAD work/review | tar -x
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import os
import subprocess
import tempfile

from common import PROJECT, SCRIPT_LANGS, WORK, case_of, in_case_scope, load_entries, save_json
import polyglot as P
import segments as S
import tps as T
from who import speaker_of

OUT = WORK / "review"
BRANCH = "review-pack"


def git(*args: str, env: dict | None = None, check: bool = True) -> str:
    done = subprocess.run(["git", *args], cwd=PROJECT, env=env, capture_output=True,
                          text=True, encoding="utf-8")
    if check and done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout.strip()


def push_pack(summary: str) -> int:
    """Закоммитить work/review/ в ветку review-pack и запушить, не трогая дерево."""
    files = sorted(p for p in OUT.rglob("*") if p.is_file())
    if not files:
        print("! пакет пуст — пушить нечего")
        return 1

    # Прежний review-pack — родитель нового коммита; нет ветки — коммит без родителя.
    fetched = subprocess.run(["git", "fetch", "origin", BRANCH], cwd=PROJECT,
                             capture_output=True, text=True, encoding="utf-8")
    parent = git("rev-parse", "FETCH_HEAD") if fetched.returncode == 0 else None

    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, "index"))
        for path in files:
            blob = git("hash-object", "-w", str(path))
            rel = path.relative_to(PROJECT).as_posix()
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},{rel}", env=env)
        tree = git("write-tree", env=env)

    if parent and git("rev-parse", f"{parent}^{{tree}}") == tree:
        print(f"{BRANCH}: пакет не изменился, пушить нечего")
        return 0
    cmd = ["commit-tree", tree, "-m", f"Пакет вычитки: {summary}"]
    if parent:
        cmd += ["-p", parent]
    commit = git(*cmd)

    for attempt in range(4):
        done = subprocess.run(["git", "push", "origin", f"{commit}:refs/heads/{BRANCH}"],
                              cwd=PROJECT, capture_output=True, text=True, encoding="utf-8")
        if done.returncode == 0:
            print(f"запушено в origin/{BRANCH}: {commit[:10]}")
            return 0
        print(f"! push не прошёл (попытка {attempt + 1}): {done.stderr.strip()}")
    print(f"коммит {commit[:10]} собран, но не запушен; повторить: "
          f"git push origin {commit}:refs/heads/{BRANCH}")
    return 1


def walk_english(eng: dict[str, bytes]):
    """(id, файл, метка-спецификация, индекс, говорящий) — в порядке игры."""
    for name in sorted(eng):
        if not in_case_scope(name):
            continue
        seen: collections.Counter = collections.Counter()
        for block in T.parse(eng[name]).blocks:
            current = None
            for idx, seg in enumerate(S.split(block.text)):
                who = speaker_of(seg)
                if who is not None:
                    current = who
                if not seg.has_text():
                    continue
                label = f"{block.label_id:08X}"
                seen[(label, idx)] += 1
                nth = seen[(label, idx)]
                spec = label if nth == 1 else f"{label}#{nth}"
                yield f"{name}|{spec}|{idx}", name, spec, idx, current


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--langs", default=",".join(SCRIPT_LANGS),
                    help="какие локализации выгрузить, через запятую")
    ap.add_argument("--no-push", action="store_true",
                    help=f"не коммитить и не пушить в ветку {BRANCH}")
    args = ap.parse_args()
    langs = [x for x in args.langs.split(",") if x]

    print("читаю бандлы всех языков (минута-две)...")
    scripts = P.load_all()
    eng = scripts["eng"]

    known = {e["id"] for e in load_entries()}
    rows = list(walk_english(eng))
    ids = {r[0] for r in rows}
    lost = sorted(known - ids)
    if lost:
        print(f"! {len(lost)} id из work/case*.json не нашлись в английских скриптах, "
              f"например {lost[:3]} — нумерация разошлась, выгрузке верить нельзя")
        return 1

    speakers = {key: who for key, _n, _s, _i, who in rows if key in known}
    save_json(OUT / "speakers.json", speakers)
    print(f"говорящие: {len(speakers)} реплик, без E101 — "
          f"{sum(1 for v in speakers.values() if v is None)}")

    mismatch: dict[str, list[str]] = {}
    for lang in langs:
        files = scripts.get(lang, {})
        out: dict[str, str | None] = {}
        bad = []
        cache: dict[tuple[str, str, int], list | None] = {}
        for key, name, spec, idx, _who in rows:
            if key not in known:
                continue
            raw = files.get(name)
            if raw is None:
                out[key] = None
                continue
            ck = (name, spec, idx)
            if ck not in cache:
                cache[ck] = P.resolve(raw, spec, idx)
            segs = cache[ck]
            if segs is None:
                out[key] = None
            elif idx < len(segs) and segs[idx] is not None:
                out[key] = segs[idx]
            else:
                # Разбивка блока разошлась: кладём блок целиком с пометкой,
                # редактор увидит, что это не одна реплика, а весь блок.
                out[key] = "[БЛОК] " + " ‖ ".join(t for t in segs if t)
                bad.append(key)
        save_json(OUT / "locales" / f"{lang}.json", out)
        mismatch[lang] = bad
        print(f"{lang}: {sum(1 for v in out.values() if v)} реплик, разбивка разошлась — {len(bad)}")

    by_case = collections.Counter(case_of(k.split("|")[0]) for k in speakers)
    save_json(OUT / "meta.json", {
        "exported": dt.datetime.now().isoformat(timespec="seconds"),
        "segments": len(speakers),
        "by_case": {str(k): v for k, v in sorted(by_case.items(), key=lambda kv: str(kv[0]))},
        "langs": langs,
        "split_mismatch": {lang: len(v) for lang, v in mismatch.items()},
        "split_mismatch_sample": {lang: v[:20] for lang, v in mismatch.items()},
    })
    print(f"готово: {OUT}")
    if args.no_push:
        return 0
    stamp = dt.date.today().isoformat()
    return push_pack(f"{len(speakers)} реплик, {len(langs)} языков, {stamp}")


if __name__ == "__main__":
    raise SystemExit(main())
