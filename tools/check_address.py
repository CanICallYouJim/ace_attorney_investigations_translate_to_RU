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
    python tools/check_address.py --tables               # кнопки тем и врезки

`--tables` — про второе хранилище. Кнопку темы переводят отдельным проходом,
до диалогов (правило №6), и собеседника в ней нет вовсе: «What are you hiding» —
и всё. Так в списке тем Ларри оказалось «Что вы скрываете» при «Что ты скрываешь?»
в реплике под ней, а в списке тем к потерявшей память Кей — «Что вы помните».
Обе нашёл игрок 31 августа 2026.

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
from common import (BACKUP, HOST, WORK, case_of, in_case_scope, load_entries,
                    load_json, read_scripts_all)
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
# Кнопка темы — не реплика: местоимения в ней может не быть вовсе («Что вы
# скрываете»), а форма всё равно видна по окончанию глагола. В репликах этот
# признак не нужен и только шумит — там местоимение почти всегда есть.
RU_VERB_VY = re.compile(r"\b[а-яё]{2,}(?:ете|ёте|ите)\b", re.I)
RU_VERB_TY = re.compile(r"\b[а-яё]{2,}(?:ешь|ёшь|ишь)\b", re.I)
# Второе лицо прячется и в прошедшем времени, и это худший из тайников: «Что-нибудь
# заметили?» — вежливое «вы», а «Тело отодвинули?» — безличное «они», и морфология
# их не различает. Поэтому признак берётся только в вопросе: в кнопке темы вопрос
# почти всегда обращён к собеседнику. Так нашлось `gk2_topic00_00a` (игрок,
# 1 сентября 2026) — форму там выбрали только мы, у остальных семи её нет вовсе.
RU_PAST_PL = re.compile(r"\b[а-яё]{3,}ли\b", re.I)
# Английский тоже бывает виден: где стоит `you`, форму выбирали не мы одни.
EN_YOU = re.compile(r"\byou(?:r|rs|rself)?\b", re.I)

# Таблицы, где у строки есть собеседник: кнопки тем, варианты ответа, ярлыки
# логики. Врезки (`gk2_txtcut`), описания улик и интерфейс сюда не входят —
# там речь о третьих лицах или обращение к самому игроку.
ADDRESSED_TABLES = ("gk2_select_short", "gk2_select_long",
                    "gk2_logic_button", "gk2_logic_name")

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
    "Ланг": ("ты", "свысока и намеренно: зовёт «господин прокурор» и тут же «тыкает» — на этом контрасте держится его пренебрежение; решение пользователя 2 сентября 2026"),
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


def french_tables() -> dict[str, dict[str, str]]:
    """Французские строковые таблицы: имя таблицы -> {m_Id: строка}.

    Немецкий столбец лежит в work/strings.json, а французский приходится читать
    из бандла — но читать обязательно. Немецкий молчит там, где французский
    говорит (`Ihr Alibi` в начале строки неотличимо от «её алиби», а `Votre
    alibi` однозначно), и оба молчат там, где ушли от формы нарочно.
    """
    import UnityPy

    from common import bundle

    out: dict[str, dict[str, str]] = {}
    for key in ("strings_fre", "strings_fre_main"):
        env = UnityPy.load(str(bundle(key)))
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            tree = obj.read_typetree()
            if "m_TableData" not in tree:
                continue
            name = tree["m_Name"].rsplit("_", 1)[0]
            out.setdefault(name, {}).update(
                {str(row["m_Id"]): row["m_Localized"] for row in tree["m_TableData"]})
    return out


def tables() -> int:
    """То же самое по строковым таблицам: кнопки тем, врезки, подписи.

    Здесь ошибка живёт вольготнее, чем в репликах. Кнопку темы переводят
    отдельным проходом, до диалогов (правило №6), а в самой кнопке нет ни
    говорящего, ни собеседника: «What are you hiding» — и всё. Так и вышло,
    что в списке тем Ларри стояло «Что вы скрываете», а в реплике под ней —
    «Что ты скрываешь?». Нашёл игрок.

    Два списка, и второй важнее первого:

    * **расхождение** — у немцев или французов форма есть, и она не наша;
    * **форму выбрали только мы** — ни в английском, ни у немцев, ни у французов
      формы нет вовсе, а по-русски она есть. Это не мелочь: строка таблицы
      **одна на всю игру**, а собеседник у неё в каждой сцене свой. Кнопка
      «Notice anything?» показывается и Кей, и Гамшу, и Бадду — а Эджворт с Кей
      на «ты», с Гамшу в деле 1 на «вы», Грегори с Баддом на «вы». Все семь
      локализаций ушли от формы (яп. 気づいたこと, фр. `Quelque chose à signaler ?`,
      нем. `Etwas bemerkt?`), и мы обязаны уйти тоже. Найдено игроком
      1 сентября 2026: стояло «Что-нибудь заметили?», стало «Что удалось
      заметить?».
    """
    data = load_json(WORK / "strings.json")
    if not data:
        print("нет work/strings.json — сначала tools/extract_strings.py")
        return 1
    fre = french_tables()

    hits = seen = only_ours = 0
    for table, rows in sorted(data["tables"].items()):
        for key, entry in rows.items():
            ru = (entry.get("ru") or "").replace("\n", " ")
            de = (entry.get("de") or "").replace("\n", " ")
            en = (entry.get("en") or "").replace("\n", " ")
            fr = (fre.get(table, {}).get(key) or "").replace("\n", " ")
            if not ru:
                continue
            formal = (bool(DE_SIE_ALWAYS.search(de)) or bool(DE_SIE_MID.search(de))
                      or bool(FR_VOUS.search(fr)) or bool(FR_VOUS_VERB.search(fr)))
            familiar = bool(DE_DU.search(de)) or bool(FR_TU.search(fr))
            ru_vy = bool(RU_VY.search(ru)) or bool(RU_VERB_VY.search(ru))
            ru_ty = bool(RU_TY.search(RU_TY_INTERJ.sub(" ", ru))) or bool(RU_VERB_TY.search(ru))

            if not (formal or familiar):
                # Ни у кого формы нет. Если она есть у нас — разбирать: строка
                # одна, а собеседников у неё несколько.
                if (table in ADDRESSED_TABLES and not EN_YOU.search(en)
                        and (ru_vy or ru_ty
                             or (ru.rstrip().endswith("?") and RU_PAST_PL.search(ru)))):
                    only_ours += 1
                    print(f"{table} {key} — форму выбрали только мы")
                    print(f"   EN: {en}")
                    print(f"   DE: {de}")
                    print(f"   FR: {fr}")
                    print(f"   RU: {ru}")
                continue

            seen += 1
            if familiar and not formal and ru_vy and not ru_ty:
                why = "у них «ты», у нас «вы»"
            elif formal and not familiar and ru_ty and not ru_vy:
                why = "у них «вы», у нас «ты»"
            else:
                continue
            hits += 1
            print(f"{table} {key} — {why}")
            print(f"   EN: {en}")
            print(f"   DE: {de}")
            print(f"   FR: {fr}")
            print(f"   RU: {ru}")

    print()
    print(f"записей с чужим признаком: {seen}, расхождений: {hits}, "
          f"«форму выбрали только мы»: {only_ours}")
    print("Признак вероятностный: письмо по-немецки вежливо и между друзьями,")
    print("а интерфейс обращается к игроку, а не к персонажу. Решать глазами.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", type=int, help="номер дела")
    ap.add_argument("--tables", action="store_true",
                    help="не реплики, а строковые таблицы: кнопки тем, врезки")
    ap.add_argument("--who", help="только этот говорящий, как в who.py")
    ap.add_argument("--imperative", action="store_true",
                    help="только повеления (там местоимений нет)")
    args = ap.parse_args()

    if args.tables:
        return tables()
    if args.case is None:
        ap.error("нужен --case или --tables")

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
