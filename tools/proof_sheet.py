"""Лист вычитки для пользователя: каждая правка в контексте сцены, с лицами и возрастом.

Пользователь решает глазами, как игрок: ему нужно видеть, кто с кем говорит,
сколько им лет, о чём шла речь за несколько реплик до, и что было / что стало.
Читать это по JSON-патчам невозможно, поэтому лист собирается в одну HTML-страницу:

  * шапка — сцены, число правок, вопросы;
  * на каждую правку карточка: говорящий (портрет, имя, возраст), N реплик до
    правленой с говорящими, сама реплика EN / нем. / фр., «было» и «стало»,
    причина и уровень, вердикт ревьюера, если он был;
  * вопросы пользователю — отдельным блоком с вариантами.

Портреты — `work/review/portraits/faces/<короткое имя>.(png|jpg|gif|webp)`, где
короткое имя — то же, что `who.py` пишет на плашке («Эджворт», «Гамшу», «Кей»).
Нет файла — вместо лица монограмма. Возраст — из профилей органайзера
(`work/strings.json`, `gk2_castNNN_MM_age`) плюс несколько известных вручную.

    python tools/proof_sheet.py work/proofread-2026-11/c4 sce3_c0_01 -o лист.html
    python tools/proof_sheet.py work/proofread-2026-11/c4 -o лист.html   # все сцены каталога
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import re
from pathlib import Path

from common import WORK, case_of, load_entries, load_json
from scene_dump import PACK, name_of

CODES = re.compile(r"\{(?!\{)[^}]*\}")
FACES = PACK / "portraits" / "faces"
CONTEXT = 6

# Возраст из профилей органайзера ищется по фамилии/имени; здесь те, у кого
# профиля во второй игре нет или он без возраста.
EXTRA_AGE = {
    "Эджворт": ("Майлз Эджворт", "26"),
    "Эксцельсиус": ("Эксцельсиус Победин", "68"),
    "Нидлер": ("Флоренс Нидлер", "?"),
    "Грегори": ("Грегори Эджворт", "?"),
    "Бадд": ("Тайрелл Бадд", "42"),
    "фон Карма": ("Манфред фон Карма", "49"),
}

LEVEL_NAMES = {
    "L0": "смысл", "L1": "ты/вы", "L2": "калька", "L3": "не по образу",
    "L4": "живость", "punct": "пунктуация", "Q": "вопрос",
}


def plain(text: str) -> str:
    return CODES.sub("", text or "").replace("{{", "{").replace("}}", "}")


def profiles() -> dict[str, tuple[str, str]]:
    """Полное имя -> возраст по профилям органайзера."""
    keys = load_json(WORK / "table_keys.json", default={}) or {}
    tables = (load_json(WORK / "strings.json", default={}) or {}).get("tables", {})
    rows: dict[str, str] = {}
    for tab in ("gk2_item_name",):
        for i, key in (keys.get(tab) or {}).items():
            cell = (tables.get(tab) or {}).get(i)
            if cell and re.match(r"gk2_cast\w+_\d+_(n|age)$", str(key)):
                rows[str(key)] = cell.get("ru") or cell.get("en") or ""
    out: dict[str, str] = {}
    for key, name in rows.items():
        if key.endswith("_n"):
            age = rows.get(key[:-2] + "_age", "")
            age = age.replace("Возраст:", "").strip()
            out.setdefault(name, age)
    return out


def person(short: str, table: dict[str, str]) -> tuple[str, str]:
    if not short or short.startswith("?"):
        return short or "?", ""  # безымянный: возраст по плашке «???» ничего не говорит
    if short in EXTRA_AGE:
        return EXTRA_AGE[short]
    for full, age in table.items():
        if short and short.lower() in full.lower():
            return full, age
    return short, ""


def face(short: str) -> str | None:
    for ext in ("png", "jpg", "jpeg", "gif", "webp"):
        p = FACES / f"{short}.{ext}"
        if p.exists():
            mime = mimetypes.guess_type(p.name)[0] or "image/png"
            return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()
    return None


def avatar(short: str, table) -> str:
    full, age = person(short, table)
    src = face(short)
    pic = (f'<img src="{src}" alt="">' if src
           else f'<span class="mono">{html.escape(short[:1].upper() or "?")}</span>')
    age_html = f'<span class="age">{html.escape(age)}</span>' if age else ""
    return (f'<div class="who"><div class="pic">{pic}</div><div class="who-t">'
            f'<b>{html.escape(full)}</b>{age_html}</div></div>')


def old_texts(rev: str | None) -> dict[str, str]:
    """id -> русский на ревизии `rev` (до применения правок), чтобы «было» не стало «стало»."""
    if not rev:
        return {}
    import subprocess
    out: dict[str, str] = {}
    for name in ("common", "case1", "case2", "case3", "case4", "case5"):
        raw = subprocess.run(["git", "show", f"{rev}:work/{name}.json"], cwd=WORK.parent,
                             capture_output=True, text=True, encoding="utf-8").stdout
        if raw:
            out.update({e["id"]: e["ru"] for e in json.loads(raw)["entries"]})
    return out


def build(folder: Path, scenes: list[str] | None, before: str | None = None,
          extra: Path | None = None) -> str:
    entries = load_entries()
    was_of = old_texts(before)
    order = {e["id"]: i for i, e in enumerate(entries)}
    by_id = {e["id"]: e for e in entries}
    speakers = load_json(PACK / "speakers.json", default={}) or {}
    locales = {lang: load_json(PACK / "locales" / f"{lang}.json", default={}) or {}
               for lang in ("ger", "fre")}
    table = profiles()

    def who(key: str) -> str:
        return name_of(case_of(by_id[key]["file"]), speakers.get(key))

    patches = sorted(folder.glob("*.patch.json"))
    if scenes:
        patches = [p for p in patches if p.name.split(".")[0] in scenes]

    answered = load_json(PACK.parent / "proofread-2026-11" / "answered.json", default={}) or {}
    cards, questions, summary = [], [], []
    scene_cards: dict[str, list[str]] = {}
    for patch_path in patches:
        scene = patch_path.name.split(".")[0]
        patch = load_json(patch_path) or {}
        why = load_json(folder / f"{scene}.why.json", default={}) or {}
        review = load_json(folder / f"{scene}.review.json", default={}) or {}
        verdicts = review.get("verdicts", {})
        missed = review.get("missed", {})
        qs = load_json(folder / f"{scene}.questions.json", default=[]) or []
        summary.append((scene, len(patch), len(missed), len(qs)))

        items = [(k, v, why.get(k, {}), verdicts.get(k)) for k, v in patch.items()]
        items += [(k, m.get("text", ""), {"level": m.get("level", []), "why": m.get("why", "")},
                   {"v": "missed"}) for k, m in missed.items() if k not in patch]
        items.sort(key=lambda it: order.get(it[0], 0))

        for key, new, reason, verdict in items:
            e = by_id.get(key)
            if not e:
                continue
            idx = order[key]
            ctx = [x for x in entries[max(0, idx - CONTEXT):idx] if x["file"] == e["file"]]
            ctx_html = "".join(
                f'<li><span class="sp">{html.escape(who(x["id"]))}</span>'
                f'<span class="ln">{html.escape(plain(x["ru"]))}</span></li>' for x in ctx)
            final = new
            v = (verdict or {}).get("v")
            if v == "alt":
                final = verdict.get("text") or new
            levels = "".join(f'<span class="chip">{html.escape(LEVEL_NAMES.get(l, l))}</span>'
                             for l in reason.get("level", []))
            vchip = {
                "accept": '<span class="v ok">ревьюер: да</span>',
                "reject": '<span class="v no">ревьюер: отклонил</span>',
                "alt": '<span class="v alt">ревьюер: свой вариант</span>',
                "missed": '<span class="v alt">нашёл ревьюер</span>',
            }.get(v, "")
            rev_why = ""
            if verdict and verdict.get("why") and v in ("reject", "alt"):
                rev_why = f'<p class="rw">Ревьюер: {html.escape(verdict["why"])}</p>'
            alt_html = ""
            if v == "alt":
                alt_html = (f'<div class="row"><span class="tag">редактор</span>'
                            f'<p class="mid">{html.escape(plain(new))}</p></div>')
            foreign = "".join(
                f'<div class="row"><span class="tag">{lab}</span><p class="for">{html.escape(plain(t))}</p></div>'
                for lab, t in (("EN", e["en"]), ("DE", locales["ger"].get(key)),
                               ("FR", locales["fre"].get(key))) if t)
            scene_cards.setdefault(scene, []).append(f"""
<article class="card{' rejected' if v == 'reject' else ''}" id="{html.escape(key)}">
  <header>{avatar(who(key), table)}<div class="meta"><code>{html.escape(key.replace('.bytes', ''))}</code>{levels}{vchip}</div></header>
  {'<ol class="ctx">' + ctx_html + '</ol>' if ctx_html else ''}
  <div class="line">
    {foreign}
    <div class="row"><span class="tag was">было</span><p class="old">{html.escape(plain(was_of.get(key, e["ru"])))}</p></div>
    {alt_html}
    <div class="row"><span class="tag now">{'итог' if v == 'alt' else 'стало'}</span><p class="new">{html.escape(plain(final))}</p></div>
  </div>
  <p class="why">{html.escape(reason.get("why", ""))}</p>{rev_why}
</article>""")

        for q in qs:
            key = q.get("id", "")
            e = by_id.get(key)
            if not e or key in answered:
                continue
            idx = order[key]
            ctx = [x for x in entries[max(0, idx - CONTEXT):idx] if x["file"] == e["file"]]
            ctx_html = "".join(
                f'<li><span class="sp">{html.escape(who(x["id"]))}</span>'
                f'<span class="ln">{html.escape(plain(x["ru"]))}</span></li>' for x in ctx)
            opts = "".join(f"<li>{html.escape(plain(o))}</li>" for o in q.get("options", []))
            questions.append(f"""
<article class="card q" id="q-{html.escape(key)}">
  <header>{avatar(who(key), table)}<div class="meta"><code>{html.escape(key.replace('.bytes', ''))}</code><span class="chip">{html.escape(q.get("kind", ""))}</span></div></header>
  {'<ol class="ctx">' + ctx_html + '</ol>' if ctx_html else ''}
  <div class="line">
    <div class="row"><span class="tag">EN</span><p class="for">{html.escape(plain(e["en"]))}</p></div>
    <div class="row"><span class="tag was">сейчас</span><p class="new">{html.escape(plain(e["ru"]))}</p></div>
  </div>
  <p class="why">{html.escape(q.get("basis", ""))}</p>
  <ol class="opts">{opts}</ol>
  <p class="rec">Рекомендую: {html.escape(q.get("recommend", ""))}</p>
</article>""")

    for scene, items_html in scene_cards.items():
        cards.append(f'<details class="scene"><summary><code>{scene}</code> — правок: {len(items_html)}</summary>'
                     f'<div class="scene-body">{"".join(items_html)}</div></details>')
    rows = "".join(f"<tr><td><code>{s}</code></td><td>{n}</td><td>{m}</td><td>{q}</td></tr>"
                   for s, n, m, q in summary)
    total = sum(n for _, n, _, _ in summary)
    case_no = folder.name[1:] if folder.name[:1] == "c" and folder.name[1:].isdigit() else ""
    return TEMPLATE.format(
        tab=f"Вычитка дела {case_no}" if case_no else "Лист вычитки",
        title="Вычитка: " + (", ".join(scenes) if scenes else folder.name),
        total=total, nq=len(questions), rows=rows,
        cards="".join(cards) or "<p>Правок нет.</p>",
        questions="".join(questions) or "<p>Вопросов нет.</p>")


TEMPLATE = """<title>{tab}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;600&family=Literata:opsz,wght@7..72,400;7..72,600&family=JetBrains+Mono:wght@400&display=swap">
<style>
/* Лист дела: узкая колонка, карточка на правку, контекст сцены приглушён, правка — в фокусе */
:root {{
  --bg: #f3f1ec; --paper: #fffdf8; --ink: #1f2430; --muted: #6b6f7a; --line: #dcd7cc;
  --was: #a3402f; --now: #1f6b4a; --accent: #2d4a7a; --chip: #e8e4da;
  --f-ui: "Golos Text", "Segoe UI", system-ui, sans-serif;
  --f-text: "Literata", Georgia, "Times New Roman", serif;
  --f-mono: "JetBrains Mono", ui-monospace, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #15181e; --paper: #1d2129; --ink: #e6e3dc; --muted: #9298a4; --line: #2f3440;
  --was: #e08a78; --now: #7fcfa6; --accent: #8fb0e6; --chip: #2a2f3a; color-scheme: dark }} }}
:root[data-theme="dark"] {{
  --bg: #15181e; --paper: #1d2129; --ink: #e6e3dc; --muted: #9298a4; --line: #2f3440;
  --was: #e08a78; --now: #7fcfa6; --accent: #8fb0e6; --chip: #2a2f3a; color-scheme: dark }}
body {{ background: var(--bg); color: var(--ink); font-family: var(--f-ui); font-size: 15px; line-height: 1.5; }}
main {{ max-width: 760px; margin: 0 auto; padding-block: 24px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; gap: 18px; }}
h1 {{ font-family: var(--f-text); font-weight: 600; font-size: 1.6rem; margin: 0; text-wrap: balance; }}
h2 {{ font-size: .8rem; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin: 18px 0 0; }}
.sum {{ color: var(--muted); margin: 0; }}
.tbl {{ overflow-x: auto; }}
table {{ border-collapse: collapse; font-variant-numeric: tabular-nums; font-size: .85rem; }}
td, th {{ padding: 4px 12px 4px 0; text-align: left; border-bottom: 1px solid var(--line); }}
th {{ color: var(--muted); font-weight: 400; }}
code {{ font-family: var(--f-mono); font-size: .75rem; color: var(--muted); overflow-wrap: anywhere; }}
.card {{ background: var(--paper); border: 1px solid var(--line); border-radius: 6px; padding: 14px 16px; display: grid; gap: 10px; min-width: 0; }}
.card.rejected {{ opacity: .6; }}
.card header {{ display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; justify-content: space-between; }}
.who {{ display: flex; gap: 10px; align-items: center; }}
.pic {{ width: 44px; height: 44px; border-radius: 50%; overflow: hidden; background: var(--chip); display: grid; place-items: center; flex: none; }}
.pic img {{ width: 100%; height: 100%; object-fit: cover; object-position: top; }}
.mono {{ font-family: var(--f-text); font-weight: 600; color: var(--accent); }}
.who-t {{ display: grid; line-height: 1.2; }}
.age {{ font-size: .8rem; color: var(--muted); }}
.age::after {{ content: " лет"; }}
.meta {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; min-width: 0; }}
.chip, .v {{ font-size: .72rem; padding: 2px 8px; border-radius: 99px; background: var(--chip); letter-spacing: .02em; }}
.v.ok {{ color: var(--now); }} .v.no {{ color: var(--was); }} .v.alt {{ color: var(--accent); }}
.ctx {{ list-style: none; margin: 0; padding: 0 0 0 10px; border-left: 2px solid var(--line); display: grid; gap: 3px; font-size: .88rem; color: var(--muted); }}
.ctx li {{ display: grid; grid-template-columns: 7.5em 1fr; gap: 8px; }}
.sp {{ font-size: .78rem; text-align: right; padding-top: 1px; overflow-wrap: anywhere; }}
.ln {{ font-family: var(--f-text); min-width: 0; }}
.line {{ display: grid; gap: 4px; }}
.row {{ display: grid; grid-template-columns: 3.6em 1fr; gap: 8px; align-items: baseline; }}
.row p {{ margin: 0; min-width: 0; }}
.tag {{ font-size: .7rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); text-align: right; }}
.tag.was {{ color: var(--was); }} .tag.now {{ color: var(--now); }}
.for {{ font-size: .85rem; color: var(--muted); }}
.old {{ font-family: var(--f-text); color: var(--was); text-decoration: line-through; text-decoration-thickness: 1px; }}
.mid {{ font-family: var(--f-text); color: var(--muted); }}
.new {{ font-family: var(--f-text); font-size: 1.05rem; font-weight: 600; }}
.why, .rw, .rec {{ margin: 0; font-size: .85rem; color: var(--muted); }}
.rw {{ color: var(--accent); }}
details.scene {{ border-top: 1px solid var(--line); padding-block: 8px; }}
details.scene > summary {{ cursor: pointer; font-size: .95rem; padding-block: 4px; }}
details.scene > summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
.scene-body {{ display: grid; gap: 14px; padding-top: 10px; }}
.opts {{ margin: 0; padding-left: 1.4em; font-family: var(--f-text); display: grid; gap: 4px; }}
@media (max-width: 480px) {{ .ctx li {{ grid-template-columns: 1fr; gap: 0; }} .sp {{ text-align: left; }} }}
</style>
<main>
  <h1>{title}</h1>
  <p class="sum">Правок: {total}. Вопросов к вам: {nq}. Перед каждой правкой — несколько реплик сцены, чтобы было видно, кто с кем и о чём.</p>
  <div class="tbl"><table><tr><th>сцена</th><th>правок</th><th>нашёл ревьюер</th><th>вопросов</th></tr>{rows}</table></div>
  <h2>Вопросы к вам</h2>
  {questions}
  <h2>Правки</h2>
  {cards}
</main>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("scenes", nargs="*")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--before", help="git-ревизия до применения правок: «было» берётся оттуда")
    args = ap.parse_args()
    args.out.write_text(build(args.folder, args.scenes or None, args.before),
                        encoding="utf-8", newline="\n")
    print(f"лист: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
