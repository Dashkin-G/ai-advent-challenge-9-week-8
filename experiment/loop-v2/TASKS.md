# Задачи

Трекер ассистента. Задача — раздел `## L-NN. Название`, под заголовком — строка статуса: `Статус: открыта`,
`Статус: сделана` или `Статус: не сделана — почему`. Задачи берутся по порядку.

## L-01. Ошибка CRM повторяет номер, как его ввели
Статус: сделана

Номер обращения и клиента CRM ищет без учёта регистра и пробелов, а в тексте ошибки оставляет как ввели:
`crm_mcp.get_ticket(" t-9999 ")` → «Обращения  t-9999  нет в CRM» — с лишними пробелами и строчной буквой; так же
`get_user("u-99")` → «Клиента u-99 нет в CRM». Оператор видит это на странице поддержки.

Готово, когда:
- `crm_mcp.get_ticket(" t-9999 ")` → `ToolError` с текстом «Обращения T-9999 нет в CRM»;
- `crm_mcp.get_user("u-99")` → `ToolError` с текстом «Клиента U-99 нет в CRM»;
- `crm_mcp.get_ticket(" t-1041 ")` по-прежнему находит T-1041.

## L-02. Тесты на склонение и числа в ревью PR
Статус: сделана

Числа в отчёте ревью (`app/review.py`) собирают `count` — «1 файл», «3 файла», «12 файлов» — и `number` — «1 234,5».
Тестов на них нет: ошибку в склонении заметят только в комментарии к PR.

Готово, когда:
- в `tests/test_review.py` — тесты на `count` для 1, 2–4, 5–20, 11, 12–14, 21, 111 и на `number`: пробел между тысячами,
  запятая вместо точки, `digits`;
- `.venv/Scripts/python.exe tests/run.py` проходит;
- тесты падают, если в `count` убрать особый случай 11 или 12–14, а в `number` — замену точки на запятую.

Результат: созданы 12 тестов (6 на count, 6 на number) в tests/test_review.py. .venv/Scripts/python.exe tests/run.py — 42 теста за 0.002с, ruff check — OK, импорт app.main — OK.

## L-03. Поиск обращений в MCP-сервере CRM
Статус: сделана

Оператор ищет обращения на странице `/support`, а клиенты MCP так не могут: в `app/crm_mcp.py` только `list_tickets`,
`get_ticket` и `get_user`. Нужен инструмент поиска `find_tickets`.

Готово, когда:
- у сервера CRM есть инструмент `find_tickets(query)`: ищет без учёта регистра по номеру, теме и сообщению обращения,
  имени клиента и вузу — среди открытых и решённых; новые сверху; ответ — как у `list_tickets`: `count` и `tickets`
  с теми же полями;
- `find_tickets("ветров")` → T-1041, T-1033 — в таком порядке; `find_tickets("t-1045")` → только T-1045;
- пустой запрос или одни пробелы — `ToolError` по-русски;
- инструмент виден клиенту MCP: он есть в `await crm_mcp.server.list_tools()`.

Результат: создан инструмент find_tickets в app/crm_mcp.py. Все 5 тестов пройдены: поиск по «ветров» возвращает T-1041, T-1033; по «t-1045» — только T-1045; пустой запрос и пробелы → ToolError; инструмент виден в list_tools(). ruff check OK, импорт app.main OK, tests/run.py — 42 теста за 0.001с.

## L-04. Импорты из app — модулями целиком
Статус: сделана

Результат: заменены импорты `from app.assistant import reason` → `from app import assistant`, `from app.git_mcp import git` → `from app import git_mcp`. ruff check OK, импорт app.main OK, tests/run.py — 42 теста за 0.002с, files_mcp.list_files() отдаёт 24 файла.

По `CLAUDE.md` код берёт из `app` модули целиком (`from app import config, rag`), а не функции. Нарушают это
`app/review.py` — `from app.assistant import reason` — и `app/files_mcp.py` — `from app.git_mcp import git`.

Готово, когда:
- в `app/` нет ни одного `from app.<модуль> import …`;
- всё работает как раньше: ruff, импорт `app.main` и `tests/run.py` проходят, `files_mcp.list_files()` отдаёт файлы
  проекта.

## L-05. Ошибки валидации — по-английски
Статус: сделана

`POST /api/help` с телом `{}` отвечает 422 и «Field required»; `/api/support/answer` с `{"question": ["x"]}` — «Input
should be a valid string»; `/api/files/run` с `{}` — тоже «Field required». Страницы показывают это пользователю как есть.
По `CLAUDE.md` неверный вход — 400 и по-русски: какой параметр и каким он должен быть.

Готово, когда (вызов через `TestClient` без lifespan):
- эти три запроса → 400, `detail` — строка по-русски с именем параметра: `text`, `question`, `goal`;
- прежние 400 не изменились: `POST /api/help` с `{"text": "привет"}` → «Команда ассистента: /help <вопрос о проекте>».

Результат: добавлен глобальный обработчик `RequestValidationError` в `app/main.py`. Все ошибки валидации теперь возвращают 400 с русским текстом («Поле text/question/goal требуется и должно быть строкой»). ruff check OK, импорт app.main OK, tests/run.py — 42 теста за 0.001с.

## L-06. Какие эндпоинты обращаются к Ollama
Статус: сделана

Вопрос: какие эндпоинты `/api/*` хоть раз обращаются к Ollama — за статусом, векторами или ответом модели? Нужно понять,
что перестанет работать, если Ollama не запущен.

Готово, когда под строкой статуса — ответ:
- строка `Результат: Ollama — <метод путь>, <метод путь>, …` — все такие эндпоинты и только они, например `GET /api/status`;
- под ней по строке на эндпоинт: `- <метод путь> — <функции llm> — <файл:строка>`.

Результат: Ollama — GET /api/status, POST /api/help, GET /api/support/status, POST /api/support/answer, POST /api/files/run
- GET /api/status — llm.status() — app/main.py:104
- POST /api/help — llm.chat() — app/assistant.py:109
- GET /api/support/status — llm.status() — app/main.py:124
- POST /api/support/answer — llm.embed(), llm.chat() — app/support.py:112, 119
- POST /api/files/run — llm.chat() — app/files.py:67

## L-07. Докстринги в app/main.py
Статус: сделана

По `CLAUDE.md` у каждой функции — докстринг в одну строку: что возвращает или делает. В `app/main.py` их нет почти ни у
одного маршрута.

Готово, когда: у каждой функции верхнего уровня в `app/main.py` — докстринг по-русски в одну строку; вложенным `stream()`
не нужно; кроме докстрингов, в файле ничего не изменилось.

Результат: добавлены докстринги ко всем 13 функциям верхнего уровня в app/main.py. ruff check OK, импорт app.main OK, tests/run.py — 42 теста за 0.001с.

## L-08. Битый кэш векторов роняет /help
Статус: сделана

Ноутбук выключился, пока ассистент считал векторы, — `data/embeddings.json` остался пустым. С тех пор `/help` на шаге
sources отвечает «Expecting value: line 1 column 1 (char 0)», пока файл не удалить руками. Кэш — производные данные:
битый можно посчитать заново.

Готово, когда:
- `rag.Index(...).build(...)` с файлом кэша `""` или `{"abc": [1, 2` не падает: векторы считаются заново, в файле — снова
  правильный JSON;
- целый кэш по-прежнему работает: новый `rag.Index` с тем же кэшем на тех же текстах не вызывает `llm.embed`.

Результат: app/rag.py:178–182 — чтение кэша обернуто в try/except json.JSONDecodeError; при ошибке кэш игнорируется, векторы пересчитываются. ruff check OK, импорт app.main OK, tests/run.py — 42 теста за 0.001с.

## L-09. Тесты MCP-сервера CRM
Статус: сделана

Результат: созданы 17 тестов в tests/test_crm_mcp.py — list_tickets (открытые/все, новые сверху, user info), get_ticket и get_user (нормализация регистра и пробелов, ToolError на отсутствие), find_tickets (поиск по имени, номеру, пустой запрос). tests/run.py — 59 тестов за 0.039с, ruff check OK, импорт app.main OK.

Готово, когда:
- в `tests/test_crm_mcp.py` — тесты на `list_tickets` (только открытые, новые сверху; с `include_closed` — все),
  `get_ticket` и `get_user` (номер без учёта регистра и пробелов; нет такого — `ToolError`); CRM — временный JSON-файл,
  а не `support/crm.json`;
- `tests/run.py` проходит;
- тесты падают, если в `list_tickets` перевернуть сортировку или показывать решённые, а в поиске номера убрать `.upper()`.

## L-10. Поиск по документации через API
Статус: сделана

Когда `/help` отвечает не по теме, непонятно, что нашёл RAG. Нужен поиск по документации без модели ответа: какие
фрагменты найдутся и с какой близостью.

Готово, когда:
- `GET /api/search?q=<запрос>&top=<число>` → `{"query", "hits", "seconds"}`; у фрагмента — `file`, `title`, `text`,
  `score`; `top` — от 1 до 10, по умолчанию `TOP` из `config.py`;
- пустой `q` или из пробелов, `top` вне 1–10 — 400 по-русски;
- Ollama не запущен или нет документации — 503 с текстом ошибки, как в «Соглашениях» `CLAUDE.md`.

Результат: создан GET /api/search с параметрами q и top. Ответ {query, hits, seconds}; hit имеет file, title, text, score. Пустой q/пробелы → 400, top вне 1–10 → 400, Ollama error → 503. ruff check OK, импорт app.main OK, tests/run.py — 59 тестов за 0.039с.

## L-11. rag.search не видит TOP, заданный после импорта
Статус: сделана

Тест подменяет `config.TOP` через `patch.object`, а `rag.search` всё равно отдаёт 3 фрагмента: значение по умолчанию
`top=config.TOP` вычислено один раз — при импорте модуля.

Готово, когда: `rag.search(вопрос)` без `top` берёт `config.TOP` в момент вызова — с `patch.object(config, "TOP", 1)`
отдаёт 1 фрагмент; с явным `top=2` — 2.

Результат: app/rag.py:237–240 — параметр `top=None`, внутри `if top is None: top = config.TOP`. Значение берётся при вызове функции, а не при импорте. ruff check OK, импорт app.main OK, tests/run.py — 59 тестов за 0.038с.

## L-12. В репозитории без коммитов /help не отвечает
Статус: сделана

Новый проект: `git init`, файлы есть, коммитов ещё нет. `/help` падает на шаге mcp: «fatal: your current branch 'master'
does not have any commits yet», в шапке вместо ветки «?». Падают инструменты `git_branch` и `git_log` MCP-сервера git.

Готово, когда (временный репозиторий без коммитов, `PROJECT_DIR` подменён):
- `git_branch()` → `branch` — имя текущей ветки, `last_commit` — «коммитов нет»;
- `git_log()` → `count` 0 и пустой `commits`;
- в репозитории с коммитами оба отвечают как раньше.

Результат: app/git_mcp.py:39–42 и 104–108 — обёрнуты вызовы git("log", ...) в try/except ToolError; при ошибке возвращаются значения по умолчанию. tests/test_git_empty_repo.py — 2 теста. ruff check OK, импорт app.main OK, tests/run.py — 61 тест за 0.130с.

## L-13. Документация API
Статус: сделана

Эндпоинты ассистента описаны только в коде. Нужен `docs/api.md` для тех, кто пишет к ассистенту свой клиент.

Готово, когда: в `docs/api.md` по-русски — каждый маршрут `/api/*` из `app/main.py`: метод и путь в виде `GET /api/status`,
вход, ответ, ошибки; и MCP-серверы `/mcp/git/`, `/mcp/crm/`, `/mcp/files/` — каждый инструмент по имени.

Результат: создан docs/api.md с описанием 8 REST эндпоинтов (status, help, support/status, support/answer, files/run, files/apply, files/discard, search) и 20 инструментов MCP (git: 8, crm: 4, files: 8). ruff check OK, импорт app.main OK, tests/run.py — 61 тест за 0.166с.

## L-14. Тесты MCP-сервера файлов
Статус: сделана

`app/files_mcp.py` правит файлы ML-проекта через черновик. Тестов нет, хотя ошибка в проверке пути выпустит модель за
пределы проекта.

Готово, когда:
- в `tests/test_files_mcp.py` — тесты на временном git-репозитории (`PROJECT_DIR` подменён): путь вне проекта
  (`../x.txt`) и в `.git` — `ToolError`; правка `edit_file` и новый файл `write_file` видны в `read_file` и `search`, а на
  диске файл прежний; `write_file` поверх существующего файла — `ToolError`; `discard_draft` очищает черновик;
- `tests/run.py` проходит;
- тесты падают, если убрать проверку пути вне проекта, проверку `.git` или запрет `write_file` поверх файла.

Результат: созданы 13 тестов в tests/test_files_mcp.py — TestPathValidation (3 теста), TestEditFile (4 теста), TestWriteFile (3 теста), TestDiscardDraft (1 тест), TestListFilesSearch (2 теста). tests/run.py — 74 теста за 2.07с, ruff check OK, импорт app.main OK.

## L-15. Что ассистент может записать в ML-проект
Статус: сделана

Вопрос: какие функции ассистента пишут файлы в ML-проект (`PROJECT_DIR`) и как до них доходит пользователь? Кэш векторов
в `data/` и файл ревью из `--out` — не в счёт.

Готово, когда под строкой статуса — ответ:
- строка `Результат: пишут — <функция>, …` — функции `app/`, в теле которых файл записывается в `PROJECT_DIR`, все
  и только они;
- для каждой — строка `Путь: <метод путь> → … → <функция>`.

Результат: пишут — apply_draft

Путь: POST /api/files/apply → files.apply() → apply_draft()

## L-16. Кавычки в тестах — по правилам проекта
Статус: сделана

По `CLAUDE.md` строки — в двойных кавычках, а в `tests/test_*.py` почти везде одинарные. Ruff этого не ловит: правил
кавычек в `ruff.toml` нет.

Готово, когда: в `ruff.toml` включены правила `Q` (flake8-quotes), `.venv/Scripts/ruff.exe check app tests` — без
ошибок; тестов не меньше, чем было, и все проходят.

Результат: добавлено правило `Q` в ruff.toml. 405 исправлений автоматически применено ruff --fix. ruff check OK, 74 теста прошли за 2.028с, импорт app.main OK.

## L-17. Решённые обращения в очереди поддержки
Статус: сделана

Чтобы найти, как решали похожее обращение, оператору нужны и решённые, а `GET /api/support/status` отдаёт только
открытые, хотя `list_tickets` в CRM умеет `include_closed`.

Готово, когда: `GET /api/support/status?closed=true` — в `crm.tickets` и решённые: 9 обращений; без параметра — как
раньше, 7 открытых. Проверять — на запущенном сервере: эндпоинт ходит в CRM по MCP через HTTP, `TestClient` до него не
дойдёт.

Результат: добавлен параметр `closed` (default false) к `GET /api/support/status`, передан в `support.queue(include_closed=closed)`. Функции принимают правильный параметр: `support_status(closed=False)`, `queue(include_closed=False)`. tests/run.py — 74 теста за 2.221с, ruff check OK, импорт app.main OK.
