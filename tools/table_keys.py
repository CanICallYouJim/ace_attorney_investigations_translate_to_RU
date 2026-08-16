"""Какой записи строковой таблицы какое дело — по ключам, а не по догадке.

У каждой таблицы Unity Localization есть парный ассет `SharedTableData`, и в нём
на каждый `m_Id` записан **человеческий ключ**: `gk2_itm01_00c_00`, `gk2_topic04_030`,
`gk2_cast205_01`. Номер в ключе — это номер дела (нумерация с нуля: `01` = дело 2),
то есть принадлежность записи делу лежит прямо в игре и её не надо угадывать.

Зачем это отдельный скрипт. 10 августа 2026 дела опознавали по кластерам соседних
`m_Id` («разрыв больше 10 000 — новый кластер»), и метод дал ложное «дело 2 закрыто»:
кластер `gk2_select_short 1568924782592..632` держит темы **всей игры** вперемешку.
Ключи такой ошибки не допускают — но и не решают всего:

* `gk2_itmNN_`, `gk2_logicNN_`, `gk2_selectNN_`, `gk2_topicNN_`, `gk2_txtcutNN_`
  — дело записано в ключе, ответ точный;
* `gk2_castNNN_MM` — профиль персонажа. Номер `NNN` это персонаж, а `MM` —
  версия профиля (по ходу игры он переписывается). Дела в ключе нет,
  и версии приходится разбирать по тексту;
* **набор дела не равен тому, что игрок в этом деле увидит.** Интерфейс «Малого
  вора» (`gk2_topic04_02f..031`) лежит в наборе дела 5, а показывается и в деле 2 —
  копия строки в игре одна. Ключ говорит, где строка объявлена, а не где всплывёт.

    python tools/table_keys.py            # сводка: таблица x дело, переведено/всего
    python tools/table_keys.py --case 2   # что относится к делу 2 и что не переведено
    python tools/table_keys.py --todo     # только непереведённое, по делам
    python tools/table_keys.py --dump     # work/table_keys.json: таблица -> {m_Id: ключ}

Скрипт **только читает** игру.
"""
from __future__ import annotations

import argparse
import collections
import re

from common import BUNDLES, WORK, load_json, save_json

OUT = WORK / "table_keys.json"

# Бандлы с общими данными таблиц. Их два, как и самих таблиц: основной ("_trial_",
# вопреки названию) и галерейный.
SHARED_PREFIXES = ("localization-assets-shared_trial_assets_all_",
                   "localization-assets-shared_assets_all_")

# gk2_itm01_00c_00 -> дело 2; gk2_topic04_030 -> дело 5.
CASE_IN_KEY = re.compile(r"^gk2_(itm|logic|select|topic|txtcut|keyword)([0-9]{2})_")
CAST_KEY = re.compile(r"^gk2_(cast[0-9A-Fa-f]+)_")


def read_shared() -> dict[str, dict[int, str]]:
    """Имя таблицы -> {m_Id: ключ}. Оба бандла разом."""
    import UnityPy

    out: dict[str, dict[int, str]] = {}
    for prefix in SHARED_PREFIXES:
        matches = sorted(BUNDLES.glob(prefix + "*.bundle"))
        if not matches:
            raise FileNotFoundError(f"нет бандла с префиксом {prefix!r} в {BUNDLES}")
        env = UnityPy.load(str(matches[0]))
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                tree = obj.read_typetree()
            except Exception:
                continue
            if "m_Entries" not in tree:
                continue
            name = tree.get("m_TableCollectionName") or tree["m_Name"].replace(" Shared Data", "")
            out.setdefault(name, {}).update(
                {row["m_Id"]: row["m_Key"] for row in tree["m_Entries"]})
    return out


def case_of_key(key: str) -> str:
    """Дело записи по её ключу; 'профиль' и 'интерфейс' — там дела в ключе нет."""
    m = CASE_IN_KEY.match(key)
    if m:
        return f"дело {int(m.group(2)) + 1}"
    if CAST_KEY.match(key):
        return "профиль"
    if key.startswith("gk1_"):
        return "GK1"
    return "интерфейс"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", type=int, help="показать записи одного дела")
    ap.add_argument("--todo", action="store_true", help="только непереведённые записи")
    ap.add_argument("--dump", action="store_true", help=f"записать {OUT}")
    args = ap.parse_args()

    keys = read_shared()
    if args.dump:
        save_json(OUT, {t: {str(i): k for i, k in rows.items()} for t, rows in keys.items()})
        print(f"{OUT}: таблиц {len(keys)}, записей {sum(len(v) for v in keys.values())}")

    strings = load_json(WORK / "strings.json")
    if not strings:
        print("нет work/strings.json — сначала tools/extract_strings.py")
        return 1
    tables = strings["tables"]

    if args.case is not None:
        want = f"дело {args.case}"
        shown = 0
        for table in sorted(tables):
            rows = [(keys.get(table, {}).get(int(k), "?"), k, v) for k, v in tables[table].items()]
            rows = [r for r in rows if case_of_key(r[0]) == want]
            if not rows:
                continue
            done = sum(1 for _, _, v in rows if v.get("ru"))
            print(f"\n=== {table}: {done} из {len(rows)}")
            for key, mid, v in sorted(rows):
                if args.todo and v.get("ru"):
                    continue
                mark = "  " if v.get("ru") else "->"
                en = (v.get("en") or "").replace("\n", " ")[:56]
                print(f" {mark} {key:22s} {en:56s} {(v.get('ru') or '')[:30]}")
                shown += 1
        print(f"\nпоказано записей: {shown}")
        print("Помнить: набор дела и то, что игрок в деле увидит, — не одно и то же,")
        print("см. интерфейс «Малого вора» в наборе дела 5.")
        return 0

    per: dict[str, dict[str, list[int]]] = collections.defaultdict(
        lambda: collections.defaultdict(lambda: [0, 0]))
    for table, rows in tables.items():
        km = keys.get(table, {})
        for mid, v in rows.items():
            cell = per[table][case_of_key(km.get(int(mid), "?"))]
            cell[0] += 1
            cell[1] += 1 if v.get("ru") else 0
    for table in sorted(per):
        parts = " ".join(f"{grp}={ru}/{n}" for grp, (n, ru) in sorted(per[table].items()))
        print(f"{table:22s} {parts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
