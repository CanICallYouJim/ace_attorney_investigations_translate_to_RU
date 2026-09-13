# Рутина проекта одной командой. Список целей: make
#
# Запускать из Git Bash. Make на Windows по умолчанию исполняет команды через
# cmd, а тот не понимает ни прямых слэшей в пути к программе, ни UTF-8 — поэтому
# ниже он подменяется на bash из состава Git, найденный по короткому пути
# (в длинном есть пробел, а make на пробелы в SHELL спотыкается).
#
# Если bash не нашёлся, всё продолжает работать через cmd: каждый рецепт здесь —
# один вызов программы, без шелловских конструкций. Всё, что сложнее, живёт
# в tools/mk.py и tools/publish_branch.py именно поэтому.

ifeq ($(OS),Windows_NT)
  BASH := $(firstword $(wildcard C:/PROGRA~1/Git/usr/bin/bash.exe \
                                 C:/PROGRA~2/Git/usr/bin/bash.exe \
                                 C:/PROGRA~1/Git/bin/bash.exe))
  ifneq ($(BASH),)
    SHELL := $(BASH)
    .SHELLFLAGS := -c
    PY := .venv/Scripts/python.exe
  else
    PY := .venv\Scripts\python.exe
  endif
else
  PY := .venv/bin/python
endif

# Без этого кириллица в выводе падает на cp1251 при перенаправлении в файл.
export PYTHONIOENCODING := utf-8

.DEFAULT_GOAL := help
.PHONY: help check check-full selftest build install graphics graphics-ru layers restore \
        status patch patch-check uninstall release publish extract clean

help:                ## показать этот список
	@$(PY) tools/mk.py

##@ Проверки

check:               ## быстрые проверки: длины, коды, таблицы, кальки
	$(PY) tools/check_all.py

check-full:          ## полный набор: плюс тесты формата и разбор всех бандлов игры
	$(PY) tools/check_all.py --full

selftest:            ## сверить патчер с конвейером репозитория (нужна игра с переводом)
	$(PY) patcher/selftest.py

##@ Перевод в игру

build: check         ## собрать бандлы в work/build, игру не трогать
	$(PY) tools/build.py
	$(PY) tools/build_strings.py

install: check       ## собрать и поставить в игру текст и русские картинки — игра закрыта
	$(PY) tools/build.py --install
	$(PY) tools/build_strings.py --install
	$(PY) tools/inject_localized.py --install
	$(PY) tools/check_all.py --build

graphics:            ## подменить немецкую графику, ролики и выкрики английскими
	$(PY) tools/swap_localized.py --build --install

graphics-ru:         ## только русские картинки (их ставит и install) — игра закрыта
	$(PY) tools/inject_localized.py --install

layers:              ## снять слой русских надписей для патчера и листы для показа
	$(PY) tools/layer_localized.py

restore:             ## вернуть игру к оригиналам
	$(PY) tools/restore.py

status:              ## что сейчас стоит в игре и сколько переведено
	$(PY) tools/restore.py --check
	$(PY) patcher/aai2ru.py --check --no-pause

##@ Патчер и релиз

patch-check:         ## показать, что сделает патчер, ничего не меняя
	$(PY) patcher/aai2ru.py --check --no-pause

patch: layers        ## накатить патчером на свою игру — тем же путём, что у игрока
	$(PY) patcher/aai2ru.py --no-pause

uninstall:           ## откатить патчер: вернуть оригиналы из _backup_ru
	$(PY) patcher/aai2ru.py --uninstall --no-pause

release: check layers ## собрать дерево витрины и AAI2-RU.exe в dist/release
	$(PY) tools/publish_release.py --exe

publish:             ## перенести собранное в ветку main и отправить на GitHub
	$(PY) tools/publish_branch.py --push

##@ Данные и уборка

extract:             ## перечитать реплики и таблицы из игры в work/
	$(PY) tools/extract.py
	$(PY) tools/extract_strings.py

clean:               ## убрать собранное: work/build, dist/release, кеши
	@$(PY) tools/mk.py clean
