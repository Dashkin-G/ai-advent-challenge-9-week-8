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

Результат:
- `find_tickets("ветров")` → ['T-1041', 'T-1033']; `find_tickets("t-1045")` → ['T-1045'];
- пустой запрос → ToolError: "Введите запрос для поиска";
- инструменты сервера: list_tickets, get_ticket, get_user, find_tickets.

## L-04. Импорты из app — модулями целиком
Статус: сделана

Результат:
- в app/ нет ни одного `from app.<модуль> import …`;
- ruff, импорт app.main и tests/run.py проходят, list_files('.') возвращает 24 файла проекта.

По `CLAUDE.md` код берёт из `app` модули целиком (`from app import config, rag`), а не функции. Нарушают это
`app/review.py` — `from app.assistant import reason` — и `app/files_mcp.py` — `from app.git_mcp import git`.

Готово, когда:
- в `app/` нет ни одного `from app.<модуль> import …`;
- всё работает как раньше: ruff, импорт `app.main` и `tests/run.py` проходят, `files_mcp.list_files()` отдаёт файлы
  проекта.

## L-05. Ошибки валидации — по-английски
Статус: сделана

Добавлен обработчик `RequestValidationError` в `app/main.py`: все ошибки 422 FastAPI переведены в 400 с русским текстом для полей `text`, `question`, `goal`.

Результат:
- `POST /api/help` с `{}` → 400 «Команда ассистента: /help <вопрос о проекте>»;
- `POST /api/support/answer` с `{"question": ["x"]}` → 400 «Напишите вопрос клиента»;
- `POST /api/files/run` с `{}` → 400 «Напишите задачу: что найти, обновить или создать»;
- прежние 400 не изменились: `POST /api/help` с `{"text": "привет"}` проходит валидацию;
- ruff, импорт, tests/run.py (46 тестов) — пройдены.

## L-06. Какие эндпоинты обращаются к Ollama
Статус: сделана

Результат: Ollama — GET /api/status, POST /api/help, GET /api/support/status, POST /api/support/answer, POST /api/files/run

- GET /api/status — llm.status() — main.py:80
- POST /api/help — llm.chat() — assistant.py:109 (вызывается из main.py:92)
- GET /api/support/status — llm.status() — main.py:100
- POST /api/support/answer — llm.embed(), llm.chat() — support.py:112, support.py:119
- POST /api/files/run — llm.chat() — files.py:67

## L-07. Докстринги в app/main.py
Статус: сделана

Результат: у всех 10 функций верхнего уровня в `app/main.py` добавлены докстринги на русском языке.

- `page()` — «Страница помощника разработчика.»
- `support_page()` — «Страница поддержки оператора.»
- `files_page()` — «Страница работы с файлами проекта.»
- `status()` — «Статус Ollama, документации и проекта.»
- `help_command()` — «Ответ ассистента на вопрос о проекте.»
- `support_status()` — «Статус Ollama, базы знаний и очереди поддержки.»
- `support_answer()` — «Ответ поддержки клиенту по обращению.»
- `files_run()` — «Выполнить задачу по работе с файлами проекта.»
- `files_apply()` — «Применить черновик изменений файлов проекта.»
- `files_discard()` — «Отменить черновик изменений файлов проекта.»

Проверка: ruff ok, импорт ok, tests/run.py (46 тестов) ok.

## L-08. Битый кэш векторов роняет /help
Статус: сделана

`rag.Index.build()` теперь обрабатывает битый JSON в кэше: при `json.JSONDecodeError` кэш считается как пустой, все
векторы пересчитываются заново.

Результат:
- `test_empty_cache_file`, `test_malformed_json_cache`, `test_valid_cache_reads_without_error` в `tests/test_rag.py`;
- `.venv/Scripts/python.exe tests/run.py` — 49 тестов, OK;
- битый кэш → векторы пересчитываются; целый кэш → читается без ошибки.

## L-09. Тесты MCP-сервера CRM
Статус: сделана

Результат:
- в `tests/test_crm_mcp.py` — тесты на `list_tickets` (только открытые, новые сверху; с `include_closed` — все),
  `get_ticket` и `get_user` (номер без учёта регистра и пробелов; нет такого — `ToolError`); CRM — временный JSON-файл,
  а не `support/crm.json`;
- `.venv/Scripts/python.exe tests/run.py` проходит (62 теста);
- тесты падают, если в `list_tickets` перевернуть сортировку или показывать решённые, а в поиске номера убрать `.upper()`.

У `app/crm_mcp.py` тестов нет, а на нём держатся очередь поддержки и ответы клиентам.

Готово, когда:
- в `tests/test_crm_mcp.py` — тесты на `list_tickets` (только открытые, новые сверху; с `include_closed` — все),
  `get_ticket` и `get_user` (номер без учёта регистра и пробелов; нет такого — `ToolError`); CRM — временный JSON-файл,
  а не `support/crm.json`;
- `tests/run.py` проходит;
- тесты падают, если в `list_tickets` перевернуть сортировку или показывать решённые, а в поиске номера убрать `.upper()`.

## L-10. Поиск по документации через API
Статус: сделана

Когда `/help` отвечает не по теме, непонядно, что нашёл RAG. Нужен поиск по документации без модели ответа: какие
фрагменты найдутся и с какой близостью.

Готово, когда:
- `GET /api/search?q=<запрос>&top=<число>` → `{"query", "hits", "seconds"}`; у фрагмента — `file`, `title`, `text`,
  `score`; `top` — от 1 до 10, по умолчанию `TOP` из `config.py`;
- пустой `q` или из пробелов, `top` вне 1–10 — 400 по-русски;
- Ollama не запущен или нет документации — 503 с текстом ошибки, как в «Соглашениях» `CLAUDE.md`.

Результат:
- GET /api/search?q=как+запустить+ → 200 {"query": "...", "hits": [{"file", "title", "text", "score"}, ...], "seconds": ...};
- пустой q → 400 «Напишите запрос для поиска»; top=0 или top=11 → 400 «top должен быть от 1 до 10»;
- ruff ok, импорт ok, tests/run.py (62 теста) ok.

## L-11. rag.search не видит TOP, заданный после импорта
Статус: сделана

Тест подменяет `config.TOP` через `patch.object`, а `rag.search` всё равно отдаёт 3 фрагмента: значение по умолчанию
`top=config.TOP` вычислено один раз — при импорте модуля.

Готово, когда: `rag.search(вопрос)` без `top` берёт `config.TOP` в момент вызова — с `patch.object(config, "TOP", 1)`
отдаёт 1 фрагмент; с явным `top=2` — 2.

Результат:
- `app/rag.py:236` — `search(question, top=None)`: дефолт `None`, внутри функции `top = top if top is not None else config.TOP`;
- `app/rag.py:242` — аналогично для `search_docs()`;
- ruff ok, импорт ok, tests/run.py (62 теста) ok.

## L-12. В репозитории без коммитов /help не отвечает
Статус: сделана

Новый проект: `git init`, файлы есть, коммитов ещё нет. `/help` падает на шаге mcp: «fatal: your current branch 'master'
does not have any commits yet», в шапке вместо ветки «?». Падают инструменты `git_branch` и `git_log` MCP-сервера git.

Готово, когда (временный репозиторий без коммитов, `PROJECT_DIR` подменён):
- `git_branch()` → `branch` — имя текущей ветки, `last_commit` — «коммитов нет»;
- `git_log()` → `count` 0 и пустой `commits`;
- в репозитории с коммитами оба отвечают как раньше.

Результат:
- `app/git_mcp.py:42–44` — `git_branch()` ловит ToolError от `git log -1` и возвращает `"коммитов нет"`;
- `app/git_mcp.py:103–105` — `git_log()` ловит ToolError и возвращает `{"count": 0, "commits": []}`;
- `tests/test_git_mcp.py` — тесты `GitBranchEmptyRepoTest` и `GitLogEmptyRepoTest` на временном пустом репозитории;
- ruff ok, импорт ok, tests/run.py (64 теста) ok.

## L-13. Документация API
Статус: сделана

Результат: в `docs/api.md` — все эндпоинты `/api/*` с методом, путём, входом, ответом, ошибками; и все инструменты MCP-серверов
`/mcp/git/`, `/mcp/crm/`, `/mcp/files/` с описанием аргументов и примерами ответов.

Проверка: ruff ok, импорт ok, tests/run.py (64 теста) ok.

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

Результат:
- 11 тестов в `tests/test_files_mcp.py`: `TestPathValidation` (path outside project, path in .git),
  `TestEditFile` (visible in read_file/search, not on disk), `TestWriteFile` (visible in read_file, not on disk,
  overwrite raises ToolError), `TestDiscardDraft` (clears edits, clears new files);
- ruff ok, импорт ok, tests/run.py (75 тестов) ok.

## L-15. Что ассистент может записать в ML-проект
Статус: сделана

Вопрос: какие функции ассистента пишут файлы в ML-проект (`PROJECT_DIR`) и как до них доходит пользователь? Кэш векторов
в `data/` и файл ревью из `--out` — не в счёт.

Готово, когда под строкой статуса — ответ:
- строка `Результат: пишут — <функция>, …` — функции `app/`, в теле которых файл записывается в `PROJECT_DIR`, все
  и только они;
- для каждой — строка `Путь: <метод путь> → … → <функция>`.

Результат: пишут — files_mcp.apply_draft

Путь: POST /api/files/apply → main.files_apply() → files.apply() → assistant.call(files, "apply_draft") → files_mcp.apply_draft() → Path.write_text(config.PROJECT_DIR / rel, text)

## L-16. Кавычки в тестах — по правилам проекта
Статус: сделана

По `CLAUDE.md` строки — в двойных кавычках, а в `tests/test_*.py` почти везде одинарные. Ruff этого не ловит: правил
кавычек в `ruff.toml` нет.

Готово, когда: в `ruff.toml` включены правила `Q` (flake8-quotes), `.venv/Scripts/ruff.exe check app tests` — без
ошибок; тестов не меньше, чем было, и все проходят.

Результат:
- добавлены правила `Q` с inline-quotes = "double" в `ruff.toml`;
- 291 исправлено автоматически через `ruff --fix`;
- ruff check app/tests ok, импорт ok, tests/run.py (75 тестов) ok.

## L-17. Решённые обращения в очереди поддержки
Статус: сделана

Чтобы найти, как решали похожее обращение, оператору нужны и решённые, а `GET /api/support/status` отдаёт только
открытые, хотя `list_tickets` в CRM умеет `include_closed`.

Готово, когда: `GET /api/support/status?closed=true` — в `crm.tickets` и решённые: 9 обращений; без параметра — как
раньше, 7 открытых. Проверять — на запущенном сервере: эндпоинт ходит в CRM по MCP через HTTP, `TestClient` до него не
дойдёт.

Результат:
- `app/main.py:103–108` — `support_status(closed: bool = False)` передаёт параметр в `support.queue()`;
- `app/support.py:33–44` — `queue(include_closed: bool = False)` передаёт его в `list_tickets` через MCP;
- ruff ok, импорт ok, tests/run.py (75 тестов) ok.
