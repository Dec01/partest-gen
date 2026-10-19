---
title: Журнал операций над документацией
status: current
verified: 2026-09-06
sources: []
audience: maintainer
ships_in_wheel: false
---

# Журнал

Хронология: что и когда сделано с документацией и почему. Новые записи — сверху вниз,
по дате. Каждая заметная правка доков оставляет здесь строку (инвариант 5 в `WIKI.md`).

## 2026-09-06 · создание репозитория · выделение генератора из `partest`

Генератор перестал быть подпакетом `partest` и стал самостоятельным дистрибутивом
`partest-gen`. Причина и последствия — [[decisions/separate-package]].

**Код.** `partest/project_gen/**` → `partest_gen/**`. Перенос сделан через
`git subtree split`, поэтому история каталога (4 коммита, включая базовый снимок дерева до
реорганизации доков) осталась при файлах, а не превратилась в один «initial commit».
Единственная правка в коде — имена импортов и добавленные `__version__` / `--version`.

**Тесты.** Переехали шесть файлов; имена приведены к репозиторию, где слова
`project_gen` больше нет:

| Было в `partest` | Стало здесь |
|---|---|
| `tests/test_project_gen_g1.py` | `tests/test_g1_skeleton.py` |
| `tests/test_project_gen_g2.py` | `tests/test_g2_resources.py` |
| `tests/test_project_gen_g3.py` | `tests/test_g3_payloads.py` |
| `tests/test_project_gen_g4.py` | `tests/test_g4_p1_stubs.py` |
| `tests/test_project_gen_g5.py` | `tests/test_g5_ui_layout.py` |
| `tests/test_project_gen_golden.py` | `tests/test_golden_suite.py` |
| `tests/test_l1_tools.py::test_partest_gen_init_package_exports` | `tests/test_cli.py` |

`tests/fixtures/sample_openapi.yaml` скопирован, а не перемещён: в `partest` он нужен и
дальше — его читает `test_l1_tools.py`.

**Документация.** Схема повторена целиком, а не сокращена: тот же frontmatter, тот же
линтер, та же генерация страниц в колесо. Что откуда:

| Источник в `partest` | Здесь |
|---|---|
| `docs/wiki/components/project-gen.md` | [[components/generator]] + [[components/ui-layer]] + [[concepts/generated-contract]] |
| `.claude/skills/partest-scaffold/SKILL.md` | тот же скилл, перенесён целиком |
| `.claude/skills/partest-scaffold/references/post-gen-playbook.md` | [[howto/after-generation]] + осталась справочником скилла |
| `docs/wiki/howto/contribute.md` (часть про генератор) | [[howto/contribute]] |
| `docs/wiki/howto/release.md` | [[howto/release]] (переписан под этот пакет) |
| `tools/*.py` | те же инструменты, перецелены на `partest_gen/docs` |

Новые страницы: [[status]], [[index]], этот журнал, [[howto/scaffold]], [[howto/resync]],
пять ADR в `decisions/`.

**Что осталось в `partest` и сюда не поехало.** Методология (`partest.methodology`),
`TypesTestCases`, `partest.tools.generate_init`. Причина — [[decisions/methodology-upstream]].
`generate_init` — утилита общего назначения с собственным публичным входом
(`python -m partest.tools.generate_init`); переезд сломал бы его без выигрыша.

**Разрешённое противоречие.** Страница `components/project-gen.md` в `partest` утверждала,
что CLI ставится вместе с харнессом (`pip install -e .`). После выделения это неверно.
В `partest` страница заменена на короткий указатель, здесь — на [[howto/scaffold]] с
собственной командой установки.

## 2026-10-16 · сверка с выпущенным колесом · расхождения документации с кодом

Примеры воспроизведены на последнем колесе с PyPI. Код поправлен (`Unreleased` в
`CHANGELOG.md`), страницы — вслед за ним.

- [[status]]: текущая версия опубликована 2026-09-23, а не «готовится»; пол `partest` — как в `setup.py`.
- [[decisions/banner-overwrite]]: раздел уточнений — форма баннера, плейсхолдеры скелета,
  брошенные файлы и почему `--prune` не по умолчанию.
- [[howto/resync]]: раздел об удалённых операциях. [[howto/scaffold]]: `--force` для нового
  каталога не нужен, `pythonpath = .`; чек-лист больше не «отмечать».
- [[components/generator]], [[concepts/generated-contract]], [[components/ui-layer]],
  [[howto/contribute]]: `--prune`, кто пишет файлы, что UI-прогон из корня читает спеку
  (дефект на стороне `partest`).

**Разрешённое противоречие.** `CHANGELOG.md` держал последний выпуск под `Unreleased`,
первый — как «unreleased», а запись последнего говорила, что пол `partest` не двигался. По
PyPI все три выпуска выложены 2026-09-23, а `setup.py` выпуска пол поднял; исправлено по PyPI
и коммиту `release:`.

## 2026-10-17 · по итогам ревью · поправки к ADR и новая страница

- Создана [[proposals]]: спорное по итогам ревью (глубина, `pythonpath`, публичные
  имена, мажор против отдельного признака чек-листа) — не реализовано, ждёт человека.
- [[decisions/banner-overwrite]]: раздел уточнений заменён поправками
  (приняты 2026-10-18); `sources` дополнены `resources.py`, `cli.py`.
- [[concepts/generated-contract]], [[howto/resync]], [[components/generator]],
  [[components/ui-layer]]: признак Python-баннера — прежняя полная строка, чек-лист — свой
  признак, заготовки скелета, ограничения `--prune`, зависимость списка брошенных от
  методики `partest`.

## 2026-10-17 · второй раунд ревью

- [[components/generator]]: раздел «Python API» — `emit_resources`, `find_orphans`,
  `remove_orphans` с сигнатурами; пути deprecated-операций; `--entities` и отказы.
- [[howto/resync]]: отказы `--prune` (пустая и чужая спецификация), `--entities` без
  совпадений, отчёт о неудалённом и об обойдённых ссылках.
- [[decisions/banner-overwrite]]: в поправках — признак чек-листа отдельным абзацем, BOM у
  заготовок, риск неотличимых однострочных заготовок, запрет записи через ссылки.
- [[proposals]]: пункт (e) и раздел второго раунда (A–E); (c) переписан под приватизацию.

## 2026-10-18 · третий раунд ревью

- [[components/generator]]: экранирование текста спецификации, запрет записи через ссылки для
  всего, что пишет генератор; `remove_orphans(..., skipped=)`; `sources` дополнены.
- [[howto/resync]]: переименование тегов в два шага, «skipped on recheck», подсказка про
  теги вне `--entities` с изменёнными путями.
- [[decisions/banner-overwrite]]: в поправках — прямо, что правило заготовок по букве ADR
  мажор и минор держится на решении человека.
- [[proposals]]: (e) — о версии; к (A) — С-1, к (B) — С-2.
- [[howto/contribute]]: строка про `_fsguard.py`.

## 2026-10-18 · финальная проверка security

- [[components/generator]]: ключевые слова Python в тегах и путях, имена свойств, которые
  нельзя сделать полями как есть, невидимые символы, отказ до записи для несохраняемых
  спецификаций.

## 2026-10-18 · release

`Unreleased` свёрнут в выпуск (номер — в CHANGELOG); поправки [[decisions/banner-overwrite]] приняты; `status.md` обновлён.

## 2026-10-18 · патч-кандидат после ревью предыдущего выпуска

- [[components/ui-layer]]: браузер проверяет сертификаты по `PARTEST_TLS_VERIFY` (таблица
  значений, CA-бандл и хранилище браузера); абзац о том, когда `partest` читает спецификацию.
- [[components/generator]]: пример `init-package-exports` — на пакет, написанный руками, и
  предупреждение против генерируемых каталогов; что остаётся у устаревших операций.
- [[status]]: патч-кандидат, `partest.ui.ignore_https_errors` среди того, что берётся.
- [[proposals]]: пять записей после ревью патч-кандидата — ошибки сертификата в браузере,
  UI-переключатель TLS, код выхода для сетевых сбоев, `PARTEST_TLS_VERIFY` у `--url`, отказ
  `init-package-exports` в дереве генератора.

## 2026-10-19 · ревью патч-кандидата, четвёртый заход

- [[proposals]]: (6) BOM против объявленного charset, (7) сырые исключения сети у
  `load_openapi`, (8) единая очистка URL в `partest`.
- [[components/generator]]: правило скрытия URL с учётными данными и ещё одним `@`;
  `SpecReadError.downloaded` и `stage`; ошибки декодирования скачанного ответа.
