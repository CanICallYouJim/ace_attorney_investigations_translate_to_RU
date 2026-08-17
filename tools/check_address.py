"""«Ты» или «вы» — сверить с немцами и французами.

По-английски обращение не видно: `you` одно на всех, `Compare the chest...` —
и не поймёшь, наставник это юнцу или свидетелю. Русский выбрать обязан, и выбор
этот держится на возрасте, чине и близости говорящих — то есть на том, чего
в самой реплике нет. Ошибка получается тихая: текст правильный, длина в норме,
`check_len.py` зелёный, и только игрок видит, что сорокалетний адвокат «выкает»
своему восемнадцатилетнему стажёру.

Немцы и французы решали ровно ту же задачу и записали ответ прямо в текст:
`du`/`Sie`, `tu`/`vous`. Это тот же приём, что правило №3 (непонятное место —
сперва в другие локализации), просто применённый к грамматике, а не к словам.

Два признака, оба нужны — по отдельности каждый слеп:

* **местоимения**: нем. `du/dich/dir/dein`, фр. `tu/toi/ton/te` против `Sie/Ihnen`,
  `vous/votre`;
* **повелительное наклонение**: там местоимений нет вовсе. Немецкое вежливое
  повеление **всегда** содержит `Sie` (`Vergleichen Sie…`), фамильярное — нет
  (`Vergleiche…`); французское `Comparez` против `Compare`. Так и нашлась
  единственная ошибка дела 3: `Compare the treasure chest…` → «Сравните…»,
  при немецком `Vergleiche` и французском `Compare`.

Проверка **не валится**: признак вероятностный, и обращений к третьему лицу,
к залу и к самому себе в игре много. Это список на разбор глазами, как
`reread.py --latin`, а не сторож. Разбирать так: сперва посмотреть, **к кому**
обращена реплика (`who.py` покажет соседей по сцене), потом решать.

    python tools/check_address.py --case 3               # всё дело
    python tools/check_address.py --case 3 --who Грегори # один говорящий
    python tools/check_address.py --case 3 --imperative  # только повеления

Кто с кем на «ты» — записано в [`docs/voices.md`](../docs/voices.md), возрасты
персонажей — в [`docs/glossary.md`](../docs/glossary.md).
"""
from __future__ import annotations

import argparse
import collections
import re

import polyglot as P
import segments as S
import tps as T
from common import BACKUP, HOST, case_of, in_case_scope, load_entries, load_json, read_scripts_all
from who import NAMES, speaker_of

DE_DU = re.compile(r"\b(?:du|dich|dir|dein|deine[mnrs]?|deiner)\b", re.I)
# `Ihnen` вежливо всегда. А `Sie` и `Ihr` вежливы, только когда прописная буква
# в них не объясняется началом предложения: в начале `Sie` это «они»/«она»,
# а `Ihr` — «её»/«их». Без этой оговорки проверка давала 143 ложных места
# на одно дело и была бы бесполезна.
DE_SIE_ALWAYS = re.compile(r"\bIhnen\b")
DE_SIE_MID = re.compile(r"(?<![.!?…:;»\"(\[]\s)(?<!^)(?<!^\s)\b(?:Sie|Ihre[mnrs]?|Ihr)\b")
FR_TU = re.compile(r"\b(?:tu|toi|ton|ta|tes|te)\b", re.I)
FR_VOUS = re.compile(r"\b(?:vous|votre|vos)\b", re.I)
# Французское «вы» видно и без местоимения — по окончанию глагола: `Comparez`,
# `Regardez`, `Écoutez`. Для повелений это единственный признак, какой есть.
FR_VOUS_VERB = re.compile(r"\b\w{3,}(?:ez|iez)\b", re.I)

RU_VY = re.compile(r"\b(?:вы|вас|вам|вами|ваш(?:а|е|и|его|ей|ем|ему|у|им|их)?)\b", re.I)
RU_TY = re.compile(r"\b(?:ты|тебя|тебе|тобой|тво(?:й|я|ё|и|его|ей|ем|ему|ю|им|их))\b", re.I)
# «Ух ты!», «ишь ты», «вот ты как» — междометия, обращения в них нет.
RU_TY_INTERJ = re.compile(r"\b(?:ух|ишь|вон|вот|ну|ой|ай)\s+ты\b", re.I)

# Форма, решённая за персонажем целиком. Проверка её не показывает, но и
# не прячет: число снятых мест печатается в конце. Без этого список нечитаем —
# у Густо 52 реплики Эджворту на «ты» при немецком `Sie`, и все 52 намеренные.
# Заводить строку сюда можно **только** вместе со строкой в docs/decisions.md.
DECIDED: dict[str, tuple[str, str]] = {
    "Густо": ("ты", "говорит обрубками и без церемоний, «вы» ему не по складу"),
    "Сдобина": ("ты", "приторная фамильярность — её маска, всех зовёт уменьшительными"),
    "Защитин": ("ты", "панибратство — его главная метка (кроме флешбэка, там он стажёр)"),
    "Молотова": ("вы", "высокий штиль ровен ко всем, решение пользователя 9 августа 2026"),
    "Лястраж": ("вы", "приторная любезность: «милочка», «дорогуша»"),
}
# Повелительное на «вы»: «сравните», «взгляните», «простите».
RU_IMP = re.compile(r"\b[А-Яа-яЁё]{3,}(?:йте|ьте|ите)\b")
# Изъявительные формы, которые попадают под тот же хвост -ите. Список короткий
# нарочно: цель — снять шум, а не построить морфологию.
NOT_IMP = {"хотите", "говорите", "думаете", "видите", "знаете", "считаете", "делаете",
           "смотрите", "помните", "молчите", "шутите", "любите", "сидите", "держите",
           "носите", "просите", "ходите", "лежите", "летите", "стоите", "верите",
           "спешите", "грустите",
           # Междометия-формулы: их говорят и тем, с кем на «ты», — форма
           # обращения по ним не читается вовсе.
           "простите", "извините", "постойте", "стойте", "погодите", "позвольте",
           "позволите", "помилуйте", "здравствуйте", "смилуйтесь"}


def strip(text: str) -> str:
    return re.sub(r"\{[^}]*\}", "", text or "").replace("\n", " ").strip()


def lang_index(lang: str) -> dict[str, str]:
    """адрес -> реплика на этом языке.

    Слот-носитель читается из `backup/`: в живой игре он уже занят нашим
    переводом, и сверять русское «вы» с русским же «вы» бессмысленно.
    """
    if lang == HOST:
        files: dict[str, bytes] = {}
        manifest = load_json(BACKUP / "manifest.json", default={}) or {}
        for key in (f"script_{lang}", f"script_{lang}_trial"):
            entry = manifest.get(key)
            if entry and (BACKUP / entry["file"]).exists():
                files.update(P.read_bundle_scripts(BACKUP / entry["file"]))
        if not files:
            raise SystemExit(f"нет оригинала {lang} в backup/ — сверять не с чем")
    else:
        files = read_scripts_all(lang)

    out: dict[str, str] = {}
    for name, raw in files.items():
        seen: dict[tuple[str, int], int] = {}
        for block in T.parse(raw).blocks:
            for idx, seg in enumerate(S.split(block.text)):
                if not seg.has_text():
                    continue
                label = f"{block.label_id:08X}"
                nth = seen[(label, idx)] = seen.get((label, idx), 0) + 1
                key = f"{name}|{label}|{idx}" if nth == 1 else f"{name}|{label}#{nth}|{idx}"
                _h, core, _t = seg.core()
                out[key] = T.to_markup(core)
    return out


def speakers_index(case: int) -> dict[str, str]:
    """адрес -> имя говорящего, как его подписывает who.py."""
    eng = read_scripts_all("eng")
    out: dict[str, str] = {}
    for name in sorted(eng):
        if not in_case_scope(name) or case_of(name) != case:
            continue
        seen: dict[tuple[str, int], int] = {}
        for block in T.parse(eng[name]).blocks:
            current = None
            for idx, seg in enumerate(S.split(block.text)):
                who = speaker_of(seg)
                if who is not None:
                    current = who
                if not seg.has_text():
                    continue
                label = f"{block.label_id:08X}"
                nth = seen[(label, idx)] = seen.get((label, idx), 0) + 1
                key = f"{name}|{label}|{idx}" if nth == 1 else f"{name}|{label}#{nth}|{idx}"
                out[key] = NAMES.get(case, {}).get(current, current or "—")
    return out


def polite_imperative(ru: str) -> bool:
    return any(w.lower() not in NOT_IMP for w in RU_IMP.findall(ru))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", type=int, required=True, help="номер дела")
    ap.add_argument("--who", help="только этот говорящий, как в who.py")
    ap.add_argument("--imperative", action="store_true",
                    help="только повеления (там местоимений нет)")
    args = ap.parse_args()

    ger, fre = lang_index("ger"), lang_index("fre")
    who = speakers_index(args.case)

    hits = 0
    suppressed: collections.Counter[str] = collections.Counter()
    for entry in load_entries(args.case):
        ru = strip(entry.get("ru"))
        if not ru:
            continue
        name = who.get(entry["id"], "—")
        if args.who and name != args.who:
            continue
        de, fr = strip(ger.get(entry["id"], "")), strip(fre.get(entry["id"], ""))
        if not de and not fr:
            continue

        formal = (bool(DE_SIE_ALWAYS.search(de)) or bool(DE_SIE_MID.search(de))
                  or bool(FR_VOUS.search(fr)))
        familiar = bool(DE_DU.search(de)) or bool(FR_TU.search(fr))
        ru_vy = bool(RU_VY.search(ru))
        ru_ty = bool(RU_TY.search(RU_TY_INTERJ.sub(" ", ru)))

        why = None
        if familiar and not formal and ru_vy and not ru_ty:
            why = "у них «ты», у нас «вы»"
        elif formal and not familiar and ru_ty and not ru_vy:
            why = "у них «вы», у нас «ты»"
        elif (not formal and not familiar and polite_imperative(ru) and not ru_ty
                and fr and not FR_VOUS_VERB.search(fr)):
            # Повеление: вежливое немецкое обязано нести `Sie`, а французское —
            # окончание `-ez`. Нет ни того, ни другого, а по-русски «-йте» —
            # значит, форму мы выбрали сами, и её стоит перепроверить.
            why = "повеление на «вы», а у них фамильярное"
        if args.imperative and why and not why.startswith("повеление"):
            continue
        if not why:
            continue

        settled = DECIDED.get(name)
        if settled and ((settled[0] == "ты" and ru_ty) or (settled[0] == "вы" and ru_vy)):
            suppressed[name] += 1
            continue

        hits += 1
        print(f"[{name}] {entry['id']} — {why}")
        print(f"   EN: {strip(entry['en'])}")
        if de:
            print(f"   DE: {de}")
        if fr:
            print(f"   FR: {fr}")
        print(f"   RU: {ru}")

    print(f"\nмест на разбор: {hits}")
    print("Признак вероятностный: обращения к залу, к третьему лицу и к самому")
    print("себе сюда попадают тоже. Смотреть, к кому реплика, — и только потом решать.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
