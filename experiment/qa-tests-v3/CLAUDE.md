# Ассистент разработчика — правила проекта

Учебный проект AI Advent Challenge (неделя 8; код перенесён из недели 7). Ассистент отвечает на вопросы о
соседнем проекте `../ml-student-dropout`, ревьюит его pull request, отвечает клиентам поддержки и правит
файлы проекта по задаче. Модели локальные — Ollama: `qwen3.5:4b` (ответы) и `bge-m3` (векторы).

## Стек

- Python 3.12, FastAPI + uvicorn, `httpx2` (HTTP-клиент), `numpy` (векторы), MCP SDK 2.x (`mcp`).
- Pydantic — только тела запросов в `main.py`. Своих классов почти нет: модули с функциями.
- Фронт — по одному `static/*.html` на страницу: чистый HTML + CSS + JS в одном файле, без сборки и фреймворков.
- Зависимости — `requirements.txt` без версий. Новую зависимость добавлять только если без неё никак.
- Тесты — `unittest` из стандартной библиотеки в `tests/`; smoke-сценарии UI — `tests/smoke.md`, их проходит агент `qa`
  через Playwright MCP (`.mcp.json`).

## Структура

```
app/config.py     все настройки: os.getenv("ИМЯ", дефолт), пути от ROOT, адреса MCP
app/llm.py        Ollama: status, load, embed, chat (поток событий); LLMError — ошибка по-человечески
app/rag.py        фрагменты документации и кода, Index с кэшем векторов в data/, search
app/*_mcp.py      MCP-серверы (git, crm, files): MCPServer + @server.tool(), ошибка — ToolError
app/assistant.py  /help: MCP → RAG → промпт → ответ; общие помощники call, reason, dumps
app/support.py    поддержка, app/files.py — работа с файлами, app/review.py — ревью PR (CLI)
app/main.py       FastAPI: страницы, /api/*, MCP-серверы смонтированы на /mcp/<имя>/
static/*.html     страницы: index (/help), support, files
support/          данные поддержки: faq.md, crm.json
data/             кэш векторов (в .gitignore)
tests/            тесты unittest, run.py — их прогон без Ollama и data/; smoke.md — сценарии UI, serve.py — приложение для них
```

Слои: `main.py` знает про HTTP и только вызывает функции модулей. Модули фич не импортируют FastAPI.
Модели вызывает только `llm.py`. Настройки читает только `config.py`.

## Соглашения

- **Язык**: докстринги, комментарии, тексты ошибок, промпты, README — по-русски. Имена в коде — английские.
- **Имена**: модули — одно слово (`support.py`, `files_mcp.py`); функции — глагол или существительное без
  префиксов `get_`/`do_` (`answer`, `queue`, `context_text`, `ensure_index`); приватные — с `_`;
  константы модуля — `UPPER_CASE` с комментарием «зачем» (`MAX = 900  # знаков во фрагменте…`).
- **Докстринг** у каждой функции — одна строка: что возвращает или делает; «почему» — вторым предложением.
  Модуль начинается с докстринга: что он делает, стрелками по шагам.
- **Комментарий** объясняет причину, а не пересказывает код.
- **Потоки шагов** — async-генератор событий `{"type": ...}`; `main.py` отдаёт их как NDJSON через
  `assistant.dumps`. Ошибку шага не бросаем, а отдаём событием `{"type": "error", "step": ..., "message": ...}`.
- **Время** — `time.perf_counter()`, секунды `round(..., 2)`, миллисекунды `round(... * 1000)`.
- **Ошибки для человека**: что случилось и что сделать («Ollama не запущен — откройте его из меню «Пуск»»).
  `LLMError` из `llm.py`, `ToolError` в MCP-серверах, `HTTPException(400, detail="…")` в `main.py`.
- **Эндпоинт без потока** отвечает dict. Неверный вход — 400; Ollama не запущен, нет модели или документации
  (`llm.LLMError`, `FileNotFoundError`) — `HTTPException(status_code=503, detail=str(exc))`.
- **Ошибки валидации — тоже по-русски.** На `?top=abc` FastAPI сам отвечает 422 по-английски. В `main.py` —
  один обработчик `RequestValidationError` → 400 с русским текстом: какой параметр и каким он должен быть.
  Нет обработчика — добавь его, а не обходи типы (`top: str`) в каждом эндпоинте.
- **Сначала найди готовое.** Нужна функция, похожая на существующую, — расширь существующую или назови новую
  по отличию. Две функции с одним смыслом рядом (`search` и `find`) — нельзя.
- **Строки** — f-строки, двойные кавычки; файлы — `encoding="utf-8"`; JSON — `ensure_ascii=False`.
- Длина строки — до 130 знаков. Системные промпты — одна строка на правило.

## Примеры хорошего кода

Настройка — в `config.py`, с дефолтом и комментарием:

```python
TOP = int(os.getenv("TOP", "3"))  # фрагментов документации в промпт
```

Эндпоинт — тонкий: проверка входа, вызов модуля, поток событий:

```python
@app.post("/api/support/answer")
async def support_answer(body: Question):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Напишите вопрос клиента")

    async def stream():
        async for event in support.answer(body.ticket_id, question):
            yield assistant.dumps(event)

    return StreamingResponse(stream(), media_type="application/x-ndjson")
```

Ошибка внешнего сервиса — переведена на человеческий язык:

```python
    try:
        async with _client(600) as client:
            response = await client.post("/api/embed", json={"model": config.EMBED_MODEL, "input": texts})
    except httpx2.ConnectError:
        raise LLMError(NOT_RUNNING)
    if response.status_code == 404:
        raise _missing(config.EMBED_MODEL)
```

Инструмент MCP — аргументы с описанием через `Annotated`, результат — dict:

```python
@server.tool()
def list_files(
    path: Annotated[str, Field(description="Папка внутри проекта, например src/ml; пусто — весь проект")] = "",
) -> dict[str, Any]:
    """Файлы проекта — отслеживаемые git и новые, без игнорируемых (.venv, data, models)."""
    found = git("ls-files", "--cached", "--others", "--exclude-standard", "--", path or ".").splitlines()
    return {"path": path or ".", "count": len(found), "files": found}
```

Шаги с временем и ошибкой по шагу:

```python
    step = "sources"
    try:
        started = time.perf_counter()
        hits = await rag.search(question)
        yield {"type": "sources", "hits": hits, "seconds": round(time.perf_counter() - started, 2)}
    except llm.LLMError as exc:
        yield {"type": "error", "step": step, "message": str(exc)}
```

## Запрещено

- `print` для отладки — только `logging` (`logger = logging.getLogger(__name__)`), и только в `main.py`/CLI.
- Голый `except:` и проглатывание ошибки молча (`except Exception: pass`). Ловим — показываем словами.
- Настройки, адреса и ключи прямо в коде модулей: всё — через `config.py` и переменные окружения.
- Логика в `main.py` и FastAPI в модулях фич. `requests` и синхронный HTTP в async-коде — только `httpx2`.
- Новые слои и абстракции «на вырост»: классы-сервисы, репозитории, DI, базовые классы ради одного наследника.
- Английские тексты для пользователя и сообщения ошибок вида `"Error: invalid input"`.

## Шаблон модуля

```python
"""Что делает модуль: шаг → шаг → результат."""
import time

from app import config, llm, rag

LIMIT = 10  # почему именно столько


async def run(question):
    """Шаги событиями: first → second → done; ошибка — error с шагом."""
    step = "first"
    try:
        started = time.perf_counter()
        ...
        yield {"type": "first", "seconds": round(time.perf_counter() - started, 2)}
    except llm.LLMError as exc:
        yield {"type": "error", "step": step, "message": str(exc)}
```

Импорты: стандартная библиотека → сторонние → `from app import ...` (модули целиком, не функции).

## README

Каждый день — раздел `## День N. Название` с подразделами: что сделано, «Как работает» (схема в блоке
кода), «Запуск», «Как проверить задание», «Результат (дата, железо)» с таблицей замеров, «Находки»,
«Как устроено (новое)» и строка API. Пишем коротко и цифрами.

## Проверка

Каждая команда — отдельным вызовом инструмента Bash, пути — относительные и через `/`. Права выданы на
команду целиком: цепочка через `;` или `&&` и абсолютный путь требуют подтверждения, а без человека
(`claude -p`) просто не выполнятся.

```
.venv/Scripts/ruff.exe check app
.venv/Scripts/python.exe -c "import app.main"
.venv/Scripts/python.exe tests/run.py
```

Новый или изменённый эндпоинт — вызвать его без Ollama: `TestClient` без `with` (lifespan с MCP и прогревом
модели не стартует), векторы — заглушка, кэш векторов — во временной папке, чтобы заглушка не попала в
настоящий `data/`. Проверить удачный ответ и каждую ошибку на русском:

```
.venv/Scripts/python.exe -c "
import os, tempfile
os.environ['DATA_DIR'] = tempfile.mkdtemp()
from fastapi.testclient import TestClient
from app import llm, main

async def fake_embed(texts):
    return [[float(len(t) % 7 + 1), 1.0] + [0.0] * 1022 for t in texts]

llm.embed = fake_embed
client = TestClient(main.app)
for params in ({'question': 'как запустить'}, {'question': ''}, {'question': 'x', 'limit': 'abc'}):  # удачный, пустой, не тот тип
    r = client.get('/api/<путь>', params=params)
    print(r.status_code, r.json())
"
```

Документацию ассистент берёт из `PROJECT_DIR` (по умолчанию `../ml-student-dropout`). Полный прогон —
`.venv/Scripts/python.exe -m app.main` → http://127.0.0.1:8001, нужен Ollama.

## Субагенты и скиллы

- Скилл `new-endpoint` — порядок работы над новым эндпоинтом.
- Агент `style-reviewer` — после нового модуля или правок больше чем в трёх файлах. Он заново читает правила и
  весь diff, поэтому мелкую правку проверяй сам командами из «Проверки».
- Агент `qa` — после PR и после новой фичи: тесты кода и smoke-сценарии через Playwright MCP, единый отчёт со скриншотами
  в `reports/`.
