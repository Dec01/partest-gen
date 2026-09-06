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
