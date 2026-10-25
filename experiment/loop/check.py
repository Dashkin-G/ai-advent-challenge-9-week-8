"""Независимая проверка задач execution loop по их «Готово, когда» — без Ollama, настоящего data/ и ML-проекта.
Стенд зовёт её в копии проекта после каждой задачи:
  python <проект>/experiment/loop/check.py L-05 --base <коммит до задачи>  → «ok» или что не так; код выхода 1
  python <проект>/experiment/loop/check.py --health                         → тесты, ruff и импорт копии — JSON"""
import argparse
import ast
import asyncio
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from pathlib import Path

WORK = Path.cwd()  # копия проекта, в которой работал агент
TMP = Path(tempfile.mkdtemp(prefix="loop-check-"))
DOCS = TMP / "project"  # документация для поиска — четыре раздела
DOC = ("# Проект\n\n## Запуск\n\nКоманда uvicorn app.main:app\n\n## Модель\n\nСлучайный лес на признаках студента\n\n"
       "## Данные\n\nCSV с оценками и посещаемостью\n\n## API\n\nPOST /predict — прогноз риска\n")
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    PORT = probe.getsockname()[1]  # свободный порт: сервер агента мог остаться на своём
# настройки app читаются при импорте: Ollama — на порту, где никого нет; кэш и ML-проект — временные
os.environ.update(OLLAMA_URL="http://127.0.0.1:9", DATA_DIR=str(TMP / "data"), PROJECT_DIR=str(DOCS), PORT=str(PORT))
sys.path.insert(0, str(WORK))
BASE = "HEAD"  # коммит до задачи — из --base
RUFF = Path(sys.executable).with_name("ruff.exe")  # из .venv проекта: в рабочей папке на коммите своего .venv нет

# эндпоинты, которые ходят в Ollama: llm.status, llm.embed или llm.chat — ответ на L-06
OLLAMA = {"GET /api/status", "POST /api/help", "GET /api/support/status", "POST /api/support/answer", "POST /api/files/run"}
ROUTE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/api/[\w/{}-]*\w)")


def cyr(text):
    return bool(re.search("[а-яё]", str(text), re.I))


def tail(done):
    return " / ".join((done.stdout + done.stderr).strip().splitlines()[-3:])


def detail(response):
    """Текст ошибки из ответа FastAPI: detail строкой или тело как есть."""
    try:
        data = response.json()
    except ValueError:
        return response.text
    return data["detail"] if isinstance(data, dict) and isinstance(data.get("detail"), str) else response.text


async def fake_embed(texts):
    return [[float(len(t) % 7 + 1), 1.0, float(len(t) % 3)] for t in texts]


def repo(files, commit):
    """Временный git-репозиторий с файлами; commit — с одним коммитом «init»."""
    path = Path(tempfile.mkdtemp(prefix="repo-", dir=TMP))
    git = ["git", "-C", str(path), "-c", "user.name=check", "-c", "user.email=check@example.com"]
    subprocess.run([*git, "init", "-q"], check=True)
    for name, text in files.items():
        (path / name).write_text(text, encoding="utf-8")
    if commit:
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "init"], check=True)
    return path


def task(number):
    """Раздел задачи в TASKS.md копии."""
    found = re.search(rf"^## {number}\..*?(?=^## L-|\Z)", (WORK / "TASKS.md").read_text(encoding="utf-8"), re.M | re.S)
    return found.group(0) if found else ""


def answer(number, prefix):
    return [line for line in task(number).splitlines() if line.startswith(prefix)]


def tests(where, pattern=None):
    return subprocess.run([sys.executable, "tests/run.py", *(["-p", pattern] if pattern else [])], cwd=where,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)


def unit(test_file):
    """Файл тестов есть и проходит отдельным прогоном."""
    if not (WORK / "tests" / test_file).exists():
        yield f"нет tests/{test_file}"
    elif (done := tests(WORK, test_file)).returncode:
        yield f"tests/{test_file} не проходит: {tail(done)}"


def mutants(test_file, target, changes):
    """Тесты ловят поломку: в копии проекта target ломается заменой old → new, прогон test_file должен упасть."""
    applied = 0
    for old, new in changes:
        copy = Path(tempfile.mkdtemp(prefix="mutant-", dir=TMP))
        for item in ("app", "tests", "support"):
            shutil.copytree(WORK / item, copy / item, ignore=shutil.ignore_patterns("__pycache__"))
        file = copy / target
        text = file.read_text(encoding="utf-8")
        if old not in text:
            continue  # код переписан — эта поломка неприменима
        applied += 1
        file.write_text(text.replace(old, new), encoding="utf-8")
        if not tests(copy, test_file).returncode:
            yield f"тесты не заметили поломку {target}: {old!r} → {new!r}"
    if not applied:
        yield f"ни одна поломка не применилась к {target} — проверить тесты нечем"


def health():
    """Тесты, ruff и импорт копии: стенд сравнивает до и после задачи — новых падений быть не должно."""
    done = tests(WORK)
    out = done.stdout + done.stderr
    ran = re.search(r"^Ran (\d+) tests?", out, re.M)
    failed = sum(int(n) for n in re.findall(r"(?:failures|errors)=(\d+)", out)) or int(bool(done.returncode))
    lint = subprocess.run([RUFF, "check", "app", "tests", "--output-format", "concise"],
                          cwd=WORK, capture_output=True, text=True, encoding="utf-8", errors="replace")
    errors = len(re.findall(r"^\S.*:\d+:\d+: ", lint.stdout, re.M)) if lint.returncode in (0, 1) else 999  # 2 — сломан конфиг
    imported = subprocess.run([sys.executable, "-c", "import app.main"], cwd=WORK, capture_output=True).returncode == 0
    return {"tests": int(ran.group(1)) if ran else 0, "failed": failed, "ruff": errors, "import": imported}


def l01():
    from mcp.server.mcpserver.exceptions import ToolError

    from app import crm_mcp
    for tool, arg, want in ((crm_mcp.get_ticket, " t-9999 ", "Обращения T-9999 нет в CRM"),
                            (crm_mcp.get_user, "u-99", "Клиента U-99 нет в CRM")):
        try:
            tool(arg)
            yield f"{tool.__name__}({arg!r}) не бросил ToolError"
        except ToolError as exc:
            if str(exc) != want:
                yield f"{tool.__name__}({arg!r}) → «{exc}», ждали «{want}»"
    if crm_mcp.get_ticket(" t-1041 ")["id"] != "T-1041":
        yield "get_ticket(' t-1041 ') не нашёл T-1041"


def l02():
    failures = list(unit("test_review.py"))
    yield from failures
    if not failures:
        yield from mutants("test_review.py", "app/review.py",
                           [("n % 100 != 11", "True"), ("not 12 <= n % 100 <= 14", "True"), ('.replace(".", ",")', "")])


def l03():
    from mcp.server.mcpserver.exceptions import ToolError

    from app import crm_mcp
    find = getattr(crm_mcp, "find_tickets", None)
    if not callable(find):
        yield "нет функции crm_mcp.find_tickets"
        return
    if "find_tickets" not in [tool.name for tool in asyncio.run(crm_mcp.server.list_tools())]:
        yield "find_tickets не зарегистрирован в MCP-сервере CRM"
    found = find("ветров")
    ids = [t["id"] for t in found["tickets"]]
    if ids != ["T-1041", "T-1033"]:
        yield f"find_tickets('ветров') → {ids}, ждали ['T-1041', 'T-1033']"
    if found.get("count") != len(ids):
        yield f"count {found.get('count')}, обращений {len(ids)}"
    sample = crm_mcp.list_tickets()["tickets"][0]
    if ids and (set(found["tickets"][0]) != set(sample) or set(found["tickets"][0].get("user") or {}) != set(sample["user"])):
        yield f"поля обращения {sorted(found['tickets'][0])} — не как у list_tickets {sorted(sample)}"
    ids = [t["id"] for t in find("t-1045")["tickets"]]
    if ids != ["T-1045"]:
        yield f"find_tickets('t-1045') → {ids}, ждали ['T-1045']"
    for query in ("", "   "):
        try:
            find(query)
            yield f"find_tickets({query!r}) не бросил ToolError"
        except ToolError as exc:
            if not cyr(exc):
                yield f"find_tickets({query!r}): ошибка не по-русски — {exc}"


def l04():
    for file in sorted((WORK / "app").glob("*.py")):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app."):
                yield f"app/{file.name}:{node.lineno}: from {node.module} import …"
    from app import config, files_mcp, review  # noqa: F401 — модули импортируются без ошибок
    config.PROJECT_DIR = repo({"README.md": "# Проект\n"}, commit=True)
    if "README.md" not in files_mcp.list_files()["files"]:
        yield "files_mcp.list_files() не видит файлы проекта"


def l05():
    from fastapi.testclient import TestClient

    from app import main
    client = TestClient(main.app, raise_server_exceptions=False)  # без with: lifespan не стартует; 500 — ответом
    for path, body, name in (("/api/help", {}, "text"), ("/api/support/answer", {"question": ["x"]}, "question"),
                             ("/api/files/run", {}, "goal")):
        response = client.post(path, json=body)
        text = detail(response)
        if response.status_code != 400 or not cyr(text) or name not in text or re.search("Field required|Input should", text):
            yield f"POST {path} {json.dumps(body, ensure_ascii=False)} → {response.status_code} {response.text[:150]}"
    response = client.post("/api/help", json={"text": "привет"})
    if response.status_code != 400 or detail(response) != "Команда ассистента: /help <вопрос о проекте>":
        yield f"POST /api/help с text «привет» → {response.status_code} {response.text[:150]}"


def l06():
    lines = answer("L-06", "Результат:")
    if not lines:
        yield "нет строки «Результат: Ollama — …» в начале строки"
        return
    got = {f"{method} {path}" for method, path in ROUTE.findall(lines[0])}
    if got != OLLAMA:
        yield f"эндпоинты: лишние {sorted(got - OLLAMA) or '—'}, не названы {sorted(OLLAMA - got) or '—'}"
    rows = [line for line in task("L-06").splitlines() if re.match(r"- (GET|POST|PUT|PATCH|DELETE) /api/\S+ — ", line)]
    if len(rows) < len(got):
        yield f"строк «- <метод путь> — …» {len(rows)}, эндпоинтов {len(got)}"


def strip(tree):
    """AST без докстрингов модуля, классов и функций."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(node):
            node.body = node.body[1:] or [ast.Pass()]
    return ast.dump(tree)


def l07():
    text = (WORK / "app/main.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node)
            if not doc:
                yield f"{node.name}(): нет докстринга"
            elif "\n" in doc.strip() or not cyr(doc):
                yield f"{node.name}(): докстринг не в одну строку по-русски — {doc[:60]!r}"
    before = subprocess.run(["git", "show", f"{BASE}:app/main.py"], cwd=WORK, capture_output=True, text=True, encoding="utf-8")
    if strip(ast.parse(before.stdout)) != strip(tree):
        yield "кроме докстрингов, в app/main.py изменён код"


def l08():
    from app import config, llm, rag
    calls = []

    async def counting(texts):
        calls.append(len(texts))
        return await fake_embed(texts)

    llm.embed = counting
    texts = {"README.md": DOC}
    cache = config.DATA_DIR / "broken.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    for broken in ("", '{"abc": [1, 2'):
        cache.write_text(broken, encoding="utf-8")
        try:
            asyncio.run(rag.Index("broken").build(texts))
        except Exception as exc:
            yield f"кэш {broken!r}: {type(exc).__name__}: {exc}"
            return
        try:
            json.loads(cache.read_text(encoding="utf-8"))
        except ValueError:
            yield f"кэш {broken!r}: после сборки в файле не JSON"
            return
    calls.clear()
    asyncio.run(rag.Index("broken").build(texts))
    if calls:
        yield "целый кэш не используется: новый Index снова вызвал llm.embed"


def l09():
    failures = list(unit("test_crm_mcp.py"))
    yield from failures
    if failures:
        return
    if "CRM_FILE" not in (WORK / "tests/test_crm_mcp.py").read_text(encoding="utf-8"):
        yield "тесты не подменяют config.CRM_FILE — читают support/crm.json"
    yield from mutants("test_crm_mcp.py", "app/crm_mcp.py",
                       [("reverse=True", "reverse=False"), ('t["status"] not in CLOSED', "True"), (".upper()", "")])


def l10():
    from fastapi.testclient import TestClient

    from app import config, llm, main
    llm.embed = fake_embed
    client = TestClient(main.app, raise_server_exceptions=False)  # необработанная ошибка — ответ 500, а не падение
    response = client.get("/api/search", params={"q": "запуск", "top": 2})
    if response.status_code != 200:
        yield f"GET /api/search?q=запуск&top=2 → {response.status_code} {response.text[:150]}"
        return
    body = response.json()
    if not {"query", "hits", "seconds"} <= set(body):
        yield f"в ответе {sorted(body)}, ждали query, hits, seconds"
    hits = body.get("hits") or []
    if len(hits) != 2 or any(not {"file", "title", "text", "score"} <= set(hit) for hit in hits):
        yield f"top=2 → {len(hits)} фрагментов или у фрагмента нет file, title, text, score"
    hits = client.get("/api/search", params={"q": "запуск"}).json().get("hits") or []
    if len(hits) != config.TOP:
        yield f"без top — {len(hits)} фрагментов, ждали TOP = {config.TOP}"
    for params in ({"q": "   "}, {"q": "запуск", "top": 11}, {"q": "запуск", "top": 0}):
        response = client.get("/api/search", params=params)
        if response.status_code != 400 or not cyr(detail(response)):
            yield f"GET /api/search {params} → {response.status_code} {response.text[:150]}"

    async def down(texts):
        raise llm.LLMError(llm.NOT_RUNNING)

    llm.embed = down
    response = client.get("/api/search", params={"q": "модель"})
    if response.status_code != 503 or llm.NOT_RUNNING not in detail(response):
        yield f"Ollama не запущен → {response.status_code} {response.text[:150]}"
    config.PROJECT_DIR = Path(tempfile.mkdtemp(dir=TMP))
    response = client.get("/api/search", params={"q": "модель"})
    if response.status_code != 503 or "PROJECT_DIR" not in detail(response):
        yield f"нет документации → {response.status_code} {response.text[:150]}"


def l11():
    from unittest.mock import patch

    from app import config, llm, rag
    llm.embed = fake_embed

    async def search():
        with patch.object(config, "TOP", 1):
            one = await rag.search("запуск")
        return one, await rag.search("запуск", top=2)

    one, two = asyncio.run(search())
    if len(one) != 1:
        yield f"с config.TOP = 1 rag.search отдал {len(one)} фрагментов"
    if len(two) != 2:
        yield f"с top=2 rag.search отдал {len(two)} фрагментов"


def l12():
    from app import config, git_mcp
    config.PROJECT_DIR = repo({"a.txt": "x\n"}, commit=False)
    name = subprocess.run(["git", "-C", str(config.PROJECT_DIR), "symbolic-ref", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    for tool, good in ((git_mcp.git_branch, lambda r: r["branch"] == name and "коммитов нет" in r["last_commit"].lower()),
                       (git_mcp.git_log, lambda r: r["count"] == 0 and r["commits"] == [])):
        try:
            result = tool()
            if not good(result):
                yield f"без коммитов {tool.__name__}() → {result}"
        except Exception as exc:
            yield f"без коммитов {tool.__name__}() упал: {exc}"
    config.PROJECT_DIR = repo({"a.txt": "x\n"}, commit=True)
    branch, log = git_mcp.git_branch(), git_mcp.git_log()
    if not re.match(r"[0-9a-f]{7,} init · ", branch["last_commit"]) or log["count"] != 1:
        yield f"с коммитом: last_commit {branch['last_commit']!r}, git_log — {log['count']} коммитов"


def l13():
    doc = WORK / "docs/api.md"
    if not doc.exists():
        yield "нет docs/api.md"
        return
    text = doc.read_text(encoding="utf-8")
    if not cyr(text):
        yield "docs/api.md не по-русски"
    for method, path in re.findall(r'@app\.(get|post|put|patch|delete)\("(/api/[^"]*)"',
                                   (WORK / "app/main.py").read_text(encoding="utf-8")):
        if f"{method.upper()} {path}" not in text:
            yield f"не описан {method.upper()} {path}"
    from app import crm_mcp, files_mcp, git_mcp
    for mount, module in (("/mcp/git/", git_mcp), ("/mcp/crm/", crm_mcp), ("/mcp/files/", files_mcp)):
        if mount.rstrip("/") not in text:
            yield f"не описан MCP-сервер {mount}"
        for tool in asyncio.run(module.server.list_tools()):
            if tool.name not in text:
                yield f"{mount}: не описан инструмент {tool.name}"


def l14():
    failures = list(unit("test_files_mcp.py"))
    yield from failures
    if failures:
        return
    if "PROJECT_DIR" not in (WORK / "tests/test_files_mcp.py").read_text(encoding="utf-8"):
        yield "тесты не подменяют PROJECT_DIR"
    yield from mutants("test_files_mcp.py", "app/files_mcp.py",
                       [("not full.is_relative_to(config.PROJECT_DIR) or ", ""), ('== ".git"', '== ".gitx"'),
                        ("rel in draft or (config.PROJECT_DIR / rel).exists()", "False")])


def l15():
    lines = answer("L-15", "Результат:")
    if not lines:
        yield "нет строки «Результат: пишут — …» в начале строки"
        return
    functions = {node.name for file in (WORK / "app").glob("*.py")
                 for node in ast.walk(ast.parse(file.read_text(encoding="utf-8")))
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    plain = re.sub(r"[\w/.]+\.py(:\d+)?|/[\w/]+", "", lines[0])  # пути файлов и адреса — не имена функций
    named = set(re.findall(r"\b[a-z_][a-z0-9_]*\b", plain)) & functions
    if named != {"apply_draft"}:
        yield f"названы {sorted(named) or '—'}, а пишет в PROJECT_DIR только apply_draft"
    if not any("POST /api/files/apply" in line and "apply_draft" in line for line in answer("L-15", "Путь:")):
        yield "нет строки «Путь: POST /api/files/apply → … → apply_draft»"


def l16():
    lint = tomllib.loads((WORK / "ruff.toml").read_text(encoding="utf-8")).get("lint", {})
    rules = lint.get("select", []) + lint.get("extend-select", [])
    if not any(rule == "Q" or rule.startswith("Q0") for rule in rules):
        yield f"в ruff.toml нет правил Q: {rules}"
    done = subprocess.run([RUFF, "check", "app", "tests"], cwd=WORK,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode:
        yield f"ruff check app tests: {tail(done)}"
    if (done := tests(WORK)).returncode:
        yield f"tests/run.py: {tail(done)}"


def l17():
    import httpx2
    import uvicorn

    from app import main
    server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(300):
        if server.started:
            break
        time.sleep(0.1)
    try:
        url = f"http://127.0.0.1:{PORT}/api/support/status"
        for params, want in (({}, 7), ({"closed": "true"}, 9)):
            crm = httpx2.get(url, params=params, trust_env=False, timeout=60).json().get("crm", {})
            if len(crm.get("tickets") or []) != want:
                yield (f"GET /api/support/status {params} → {len(crm.get('tickets') or [])} обращений, ждали {want}"
                       + (f": {crm['error']}" if crm.get("error") else ""))
    finally:
        server.should_exit = True


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Проверка задачи execution loop в копии проекта")
    parser.add_argument("task", nargs="?", help="номер задачи, например L-05")
    parser.add_argument("--base", default="HEAD", help="коммит до задачи")
    parser.add_argument("--health", action="store_true", help="тесты, ruff и импорт — JSON")
    args = parser.parse_args()
    BASE = args.base
    DOCS.mkdir(parents=True)
    (DOCS / "README.md").write_text(DOC, encoding="utf-8")
    try:
        if args.health:
            print(json.dumps(health()))
            sys.exit(0)
        try:
            failures = list(globals()[args.task.lower().replace("-", "")]())
        except Exception as exc:  # падение кода агента — тоже итог проверки
            failures = [f"проверка упала: {type(exc).__name__}: {exc}"]
        print("\n".join(failures) or "ok")
        sys.exit(1 if failures else 0)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
