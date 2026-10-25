"""Execution loop: Claude Code сам берёт первую открытую задачу из трекера TASKS.md → выполняет → коммитит; стенд
перезапускает его с тем же промптом, пока открытые задачи не кончатся, и после каждой независимо проверяет её «Готово, когда».
Запуск из корня проекта:
  .venv/Scripts/python.exe experiment/loop.py loop-v2 --model qwen3.5-122b-a10b              текущие правила проекта
  .venv/Scripts/python.exe experiment/loop.py loop-v1b --rules experiment/loop-v1/rules       правила прогона v1
  .venv/Scripts/python.exe experiment/loop.py loop-local --provider ollama --model qwen3-coder:30b --context 49152 --gpu 32
  --limit N — не больше N заходов; --resume — продолжить прерванный прогон; --stop-on-fail — до первого сбоя;
  --report — пересобрать log.md
Проект не меняется: агент работает в копии %TEMP%\\claude-rules\\<имя>, ML-проект — тоже копия. Итог — experiment\\<имя>\\:
log.md — задача → профиль → результат → время и итоги прогона; L-NN.jsonl — лог агента; rules\\ — с какими правилами шёл."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOOP = Path(__file__).parent / "loop"
ML = ROOT.parent / "ml-student-dropout"
CODE = ["app", "static", "support", "tests", "requirements.txt", "ruff.toml", ".gitignore", "CLAUDE.md", ".claude"]
# тип задачи и профиль, которого ждём; агент их не видит — профиль выбирает сам
KINDS = {"L-01": ("баг", "bug-fix"), "L-02": ("тесты", "qa"), "L-03": ("фича", "сам"), "L-04": ("рефакторинг", "сам"),
         "L-05": ("баг", "bug-fix"), "L-06": ("вопрос", "research"), "L-07": ("документация", "сам"),
         "L-08": ("баг", "bug-fix"), "L-09": ("тесты", "qa"), "L-10": ("фича", "сам"), "L-11": ("баг", "bug-fix"),
         "L-12": ("баг", "bug-fix"), "L-13": ("документация", "сам"), "L-14": ("тесты", "qa"),
         "L-15": ("вопрос", "research"), "L-16": ("рефакторинг", "сам"), "L-17": ("фича", "сам")}
WORKERS = {"bug-fix", "research", "qa"}  # профили-исполнители; style-reviewer и прочие — помощники
HEAD = re.compile(r"^## (L-\d+)\. (.+)\n+Статус: (.+)$", re.M)
SIGNS = re.compile(r"co-authored-by|generated with|🤖|noreply@anthropic", re.I)  # подписи ИИ в коммитах
DASHSCOPE = "https://ws-q1vxaj37wm4fa9q8.ap-southeast-1.maas.aliyuncs.com/apps/anthropic"
SETTINGS = {"attribution": {"commit": "", "pr": ""}}  # коммит без подписи Claude Code
# цикл ведёт стенд: в v1 агент, пока ждал субагента, вызвал ScheduleWakeup с промптом цикла — и через минуту взял
# следующую задачу в том же контексте, мимо её проверки
DENIED = "ScheduleWakeup,CronCreate,CronDelete,CronList,Workflow"
SESSION = ("turns", "tools", "errors", "skills", "tokens_in", "tokens_out", "answer")


def sh(*cmd, cwd=None):
    done = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode:
        raise SystemExit(f"{' '.join(map(str, cmd))}: {done.stderr.strip() or done.stdout.strip()}")
    return done.stdout


def tracker(work):
    """Задачи трекера по порядку: номер → (название, статус)."""
    return {m[1]: (m[2].strip(), m[3].strip()) for m in HEAD.finditer((work / "TASKS.md").read_text(encoding="utf-8"))}


def state(status):
    plain = re.sub(r"[*_`]", "", status).strip().lower()
    return next((s for s in ("открыта", "сделана", "не сделана") if plain.startswith(s)), "другое")


def provider(args):
    """Переменные Claude Code на время прогона и имя модели: Qwen в DashScope или локальная модель Ollama."""
    if args.provider == "alibaba":
        key = os.getenv("DASHSCOPE_API_KEY")
        for file in (ROOT / ".env", ROOT.parent / "ai-advent-challenge-9-week-7" / ".env"):
            if not key and file.exists():
                key = next((line.split("=", 1)[1].strip().strip("\"' ") for line in file.read_text(encoding="utf-8").splitlines()
                            if line.startswith("DASHSCOPE_API_KEY=")), None)
        if not key:
            raise SystemExit("Нет ключа DASHSCOPE_API_KEY — задайте переменную или положите .env в корень")
        env, model = {"ANTHROPIC_BASE_URL": DASHSCOPE, "ANTHROPIC_AUTH_TOKEN": key}, args.model
    else:
        # контекст Anthropic API не передаёт — вариант модели со своим num_ctx; num_gpu — слоёв на видеокарте
        model = f"{args.model}-{args.context // 1024}k" + (f"-gpu{args.gpu}" if args.gpu >= 0 else "")
        modelfile = Path(os.environ["TEMP"]) / f"{args.name}.Modelfile"
        modelfile.write_text(f"FROM {args.model}\nPARAMETER num_ctx {args.context}\n"
                             + (f"PARAMETER num_gpu {args.gpu}\n" if args.gpu >= 0 else ""), encoding="ascii")
        created = subprocess.run(["ollama", "create", model, "-f", str(modelfile)], capture_output=True)
        modelfile.unlink()
        if created.returncode:
            raise SystemExit(f"Нет модели {args.model} в Ollama — скачайте: ollama pull {args.model}")
        env = {"ANTHROPIC_BASE_URL": "http://127.0.0.1:11434", "ANTHROPIC_AUTH_TOKEN": "ollama",  # ключ Ollama не проверяет
               "API_TIMEOUT_MS": "3600000", "NO_PROXY": "127.0.0.1,localhost"}  # первый ответ локальной модели — минуты
    # фоновые задачи и субагенты — та же модель, не подписка
    for name in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                 "ANTHROPIC_DEFAULT_HAIKU_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL"):
        env[name] = model
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    return env, model


def setup(work, ml, out, rules=None):
    """Копия проекта с трекером, где агент коммитит, и копия ML-проекта — PROJECT_DIR агента: настоящие не трогаем.
    rules — папка rules\\ прошлого прогона: CLAUDE.md, .claude и промпт цикла берутся из неё."""
    for file in sh("git", "-c", "core.quotepath=false", "ls-files", "--cached", "--others", "--exclude-standard", "--", *CODE,
                   cwd=ROOT).splitlines():
        if (ROOT / file).exists():  # удалённые в проекте, но ещё не закоммиченные — пропускаем
            (work / file).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / file, work / file)
    if rules:
        shutil.rmtree(work / ".claude")
        shutil.copytree(rules / ".claude", work / ".claude")
        shutil.copy2(rules / "CLAUDE.md", work / "CLAUDE.md")
    shutil.copy2(LOOP / "tasks.md", work / "TASKS.md")
    sh("git", "init", "-q", cwd=work)
    for key, value in (("core.autocrlf", "false"), ("user.name", "loop"), ("user.email", "loop@example.com")):
        sh("git", "config", key, value, cwd=work)
    with open(work / ".git" / "info" / "exclude", "a", encoding="utf-8") as exclude:
        exclude.write(".venv\n")  # «.venv/» из .gitignore не ловит ссылку-junction
    sh("cmd", "/c", "mklink", "/J", work / ".venv", ROOT / ".venv")  # команды проверки из CLAUDE.md
    sh("git", "add", "-A", cwd=work)
    sh("git", "commit", "-q", "-m", "baseline", cwd=work)
    sh("git", "clone", "-q", ML, ml)
    (out / "rules").mkdir(parents=True)
    for item in ("CLAUDE.md", ".claude"):  # с какими правилами и профилями шёл прогон
        (shutil.copytree if (work / item).is_dir() else shutil.copy2)(work / item, out / "rules" / item)
    shutil.copy2((rules or LOOP) / "prompt.md", out / "rules" / "prompt.md")


def claude(work, env, model, prompt, log, minutes):
    """Один заход агента: промпт цикла на вход, лог stream-json — в файл; дольше minutes — останавливаем вместе с детьми."""
    shim = Path(shutil.which("claude"))
    native = shim.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"  # .cmd-обёртка ломает JSON
    settings = json.loads((work / ".claude" / "settings.json").read_text(encoding="utf-8"))
    allowed = [rule for rule in settings["permissions"]["allow"] if not rule.startswith("mcp__")]  # MCP в цикле нет
    allowed += ["Bash(git add:*)", "Bash(git commit:*)"]  # коммит — часть цикла
    # только правила проекта: глобальный CLAUDE.md и плагины спорят с промптом цикла и тратят токены на каждом ходу
    cmd = [native if native.exists() else shim, "-p", "--permission-mode", "acceptEdits", "--output-format", "stream-json",
           "--verbose", "--setting-sources", "project,local", "--strict-mcp-config", "--settings", json.dumps(SETTINGS),
           "--model", model, "--disallowedTools", DENIED, "--allowedTools", *allowed]
    started = time.perf_counter()
    with open(prompt, "rb") as stdin, open(log, "wb") as stdout:
        process = subprocess.Popen([str(c) for c in cmd], cwd=work, env={**os.environ, **env}, stdin=stdin, stdout=stdout,
                                   stderr=subprocess.STDOUT)
        try:
            process.wait(timeout=minutes * 60)
            hung = False
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)  # и серверы агента
            process.wait()
            hung = True
    return round(time.perf_counter() - started), hung


def stats(log):
    """Из лога stream-json: ходы, токены с субагентами, вызовы инструментов, профили по задачам, ошибки, ответ."""
    events = []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue  # не JSON — сообщения Claude Code в stderr
    results = [e for e in events if e.get("type") == "result"]
    calls = [(e.get("parent_tool_use_id"), block) for e in events if e.get("type") == "assistant"
             for block in e["message"].get("content") or [] if block.get("type") == "tool_use"]
    # modelUsage — накопительно за заход и вместе с субагентами: берём последний
    tokens = max(((sum(u.get("inputTokens", 0) + u.get("cacheReadInputTokens", 0) + u.get("cacheCreationInputTokens", 0)
                       for u in (r.get("modelUsage") or {}).values()),
                   sum(u.get("outputTokens", 0) for u in (r.get("modelUsage") or {}).values())) for r in results), default=(0, 0))
    if not tokens[0]:  # агента остановили — токены по его сообщениям, без субагентов
        last = {e["message"].get("id"): e["message"].get("usage") or {} for e in events if e.get("type") == "assistant"}
        tokens = (sum(u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) for u in last.values()),
                  sum(u.get("output_tokens", 0) for u in last.values()))
    # профили по задачам: удачные вызовы Agent до коммита «L-NN: …» — этой задачи; «Agent type not found» — не выбор
    failed = {block.get("tool_use_id") for e in events if e.get("type") == "user" for block in e["message"].get("content") or []
              if isinstance(block, dict) and block.get("is_error")}
    calls = [(parent, block) for parent, block in calls if not (block["name"] in ("Agent", "Task") and block["id"] in failed)]
    by_task, current = {}, []
    for parent, block in calls:
        if parent:
            continue
        if block["name"] in ("Agent", "Task"):
            current.append(block["input"].get("subagent_type", "?"))
        command = block["input"].get("command", "") if block["name"] == "Bash" else ""
        if "git commit" in command and (task := re.search(r"L-\d+", command)):
            by_task.setdefault(task[0], []).extend(current)
            current = []
    return {"turns": sum(r.get("num_turns", 0) for r in results), "tools": len(calls),
            "errors": sum(1 for e in events if e.get("type") == "user" for block in e["message"].get("content") or []
                          if isinstance(block, dict) and block.get("is_error")),
            "profiles": [b["input"].get("subagent_type", "?") for parent, b in calls
                         if not parent and b["name"] in ("Agent", "Task")], "by_task": by_task,
            "skills": [b["input"].get("skill", "?") for _, b in calls if b["name"] == "Skill"],
            "tokens_in": tokens[0], "tokens_out": tokens[1], "started": bool(results or calls),
            "answer": " ".join((results[-1].get("result") or "").split()) if results else "",
            "failed": next((r.get("result") or r.get("subtype") for r in results if r.get("is_error")), None)}


def check(where, *args):
    done = subprocess.run([sys.executable, LOOP / "check.py", *args], cwd=where, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=1800)
    return done.returncode, done.stdout.strip() or " / ".join(done.stderr.strip().splitlines()[-2:])


def at(work, sha, *args):
    """check.py на коммите sha: в самой копии, если это HEAD, иначе — в отдельной рабочей папке на этом коммите."""
    if sha == sh("git", "rev-parse", "HEAD", cwd=work).strip():
        return check(work, *args)
    path = Path(tempfile.mkdtemp(prefix="loop-tree-")) / "tree"
    sh("git", "worktree", "add", "-q", "--detach", path, sha, cwd=work)
    try:
        return check(path, *args)
    finally:
        sh("git", "worktree", "remove", "--force", path, cwd=work)
        shutil.rmtree(path.parent, ignore_errors=True)


def health(work, sha):
    return json.loads(at(work, sha, "--health")[1].splitlines()[-1])


def close(work, number, why):
    """Задача осталась открытой — цикл отмечает её сам, иначе следующий заход взял бы её снова."""
    path = work / "TASKS.md"
    text = re.sub(rf"(^## {number}\..*\n+)Статус: открыта", lambda m: f"{m[1]}Статус: не сделана — {why} (отметка цикла)",
                  path.read_text(encoding="utf-8"), count=1, flags=re.M)
    path.write_text(text, encoding="utf-8")
    sh("git", "add", "TASKS.md", cwd=work)
    sh("git", "commit", "-q", "-m", f"{number}: не закрыта агентом — отметка цикла", cwd=work)


def attempt(work, number, env, model, out, minutes):
    """Заход агента: работа → откат незакоммиченного → по каждой закрытой задаче проверка критерия и регрессии на её
    последнем коммите. Обычно задача одна; взял агент за заход и следующие — каждая проверяется на своём коммите."""
    base = sh("git", "rev-parse", "HEAD", cwd=work).strip()
    opened = [n for n, (_, status) in tracker(work).items() if state(status) == "открыта"]
    healthy = {base: health(work, base)}
    started = time.time()
    seconds, hung = claude(work, env, model, out / "rules" / "prompt.md", out / f"{number}.jsonl", minutes)
    info = stats(out / f"{number}.jsonl")
    if not hung and (not info["started"] or info["failed"] and "API" in info["failed"] and not info["tools"]):
        # агент не начал работу: ключ, сеть, модель — сбой стенда, а не задачи; её не закрываем и не считаем
        sh("git", "reset", "-q", "--hard", cwd=work)
        tail = " / ".join((out / f"{number}.jsonl").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-2:])
        raise SystemExit(f"{number}: агент не начал работу — {info['failed'] or tail[:300]}. Исправьте и запустите с --resume")
    claimed = {n: status for n, (_, status) in tracker(work).items()}  # что агент написал в трекере, до отката
    log = sh("git", "log", "--reverse", "--format=%H%x1f%ct%x1f%s%x1f%b%x1e", f"{base}..HEAD", cwd=work)
    commits = [c.strip("\n").split("\x1f") for c in log.split("\x1e") if c.strip()]  # хеш, время, тема, текст
    left = [line[3:] for line in sh("git", "status", "--porcelain", cwd=work).splitlines()]
    if left:  # незакоммиченное не сдано: следующая задача начинается с последнего коммита
        sh("git", "reset", "-q", "--hard", cwd=work)
        sh("git", "clean", "-q", "-fd", cwd=work)
    closed = [n for n in opened if state(tracker(work)[n][1]) != "открыта"]
    if number not in closed:
        close(work, number, f"зависла дольше {minutes} мин" if hung else "агент не закрыл задачу")
        closed.insert(0, number)
    own = {n: [c for c in commits if re.match(rf"{n}\b", c[2])] for n in closed}
    own[number] += [c for c in commits if not re.match(r"L-\d+\b", c[2])]  # коммит без номера — задаче захода
    closed.sort(key=lambda n: max((commits.index(c) for c in own[n]), default=len(commits)))
    rows, boundary = [], started
    for i, n in enumerate(closed):
        mine = sorted(own[n], key=commits.index)
        sha = mine[-1][0] if mine else sh("git", "rev-parse", "HEAD", cwd=work).strip()
        parent = sh("git", "rev-parse", f"{mine[0][0]}^", cwd=work).strip() if mine else base
        before = healthy[parent] if parent in healthy else health(work, parent)
        code, text = at(work, sha, n, "--base", parent)
        if sha not in healthy:
            healthy[sha] = health(work, sha)
        after = healthy[sha]
        end = started + seconds if i == len(closed) - 1 or not mine else int(mine[-1][1])
        # счётчики захода — первой его задаче, следующим — нули: делить их по задачам не по чему
        session = {k: info[k] if not i else 0 for k in SESSION}
        if i:
            session |= {"skills": [], "answer": f"в заходе {number}"}
        row = {"task": n, "title": tracker(work)[n][0], "seconds": round(max(end - boundary, 0)), "session": number,
               "hung": hung and n == number and state(claimed.get(n, "")) == "открыта", "claimed": claimed.get(n, ""),
               "commits": [[c[0][:7], c[2]] for c in mine], "left": left if not i else [], "check": text,
               "profiles": info["by_task"].get(n, info["profiles"] if n == number else []), **session}
        boundary = end
        reasons = [f"не уложилась в {minutes} мин"] if row["hung"] else []
        if state(row["claimed"]) != "сделана":
            reasons.append(f"агент: {row['claimed'] or 'нет статуса'}")
        elif state(tracker(work)[n][1]) != "сделана":
            reasons.append("агент не закоммитил статус")
        if not mine:
            reasons.append("нет коммита")
        if any(SIGNS.search(c[2] + c[3]) for c in mine):
            reasons.append("подпись ИИ в коммите")
        if code:
            reasons.append(f"проверка: {text.splitlines()[0]}")
        if after["failed"] > before["failed"] or after["tests"] < before["tests"]:
            reasons.append(f"тесты: {before['tests']} → {after['tests']}, падений {before['failed']} → {after['failed']}")
        if after["ruff"] > before["ruff"]:
            reasons.append(f"ruff: ошибок {before['ruff']} → {after['ruff']}")
        if before["import"] and not after["import"]:
            reasons.append("import app.main падает")
        row["reasons"] = reasons
        rows.append(row)
    return rows


def dec(x, digits=1):
    return f"{x:.{digits}f}".replace(".", ",")


def profile(row):
    workers = [p for p in row["profiles"] if p in WORKERS]
    return "+".join(dict.fromkeys(workers)) or "сам"


def report(out, rows, meta):
    """log.md: итоги прогона — подряд без вмешательства, с первого раза, среднее время, — и строка на задачу."""
    streak = next((i for i, row in enumerate(rows) if row["reasons"]), len(rows))
    passed = [row for row in rows if not row["reasons"]]
    right = [row for row in rows if profile(row) == KINDS.get(row["task"], ("", ""))[1]]
    total = sum(row["seconds"] for row in rows)
    first = next((row for row in rows if row["reasons"]), None)
    lines = [f"# Execution loop {meta['name']} — {meta['model']} ({meta['provider']}), {meta['started']}", "",
             f"Правила: `experiment/{meta['name']}/rules/` — CLAUDE.md, .claude, prompt.md · задач в трекере: {len(KINDS)} · "
             f"пройдено: {len(rows)} · лимит на задачу: {meta['minutes']} мин", "",
             f"**Подряд без вмешательства: {streak} задач — {dec(sum(r['seconds'] for r in rows[:streak]) / 60)} мин** · "
             f"с первого раза: {len(passed)} из {len(rows)} ({round(100 * len(passed) / max(len(rows), 1))} %) · "
             f"среднее время на задачу: {dec(total / max(len(rows), 1) / 60)} мин · всего {dec(total / 60)} мин · "
             f"профиль выбран верно: {len(right)} из {len(rows)} · токенов: вход "
             f"{dec(sum(r['tokens_in'] for r in rows) / 1e6, 2)} млн, выход {dec(sum(r['tokens_out'] for r in rows) / 1e3)} тыс.",
             "", f"Первый сбой: {first['task']} «{first['title']}» — {'; '.join(first['reasons'])}." if first else "Сбоев нет.",
             "", "| Задача | Тип | Профиль (ждали) | Результат | Время, мин | Ходы | Вызовы | Токены, тыс. | Коммит |",
             "|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        kind, want = KINDS.get(row["task"], ("?", "?"))
        chosen = profile(row)
        mark = " ✓" if chosen == want else f" ✗ ({want})"
        extra = "".join(f", {p}" for p in row["profiles"] if p not in WORKERS) + "".join(f", скилл {s}" for s in row["skills"])
        result = "✅" if not row["reasons"] else "❌ " + "; ".join(row["reasons"])
        commit = " · ".join(f"`{h}` {s}" for h, s in row["commits"]) or "—"
        lines.append(f"| {row['task']} {row['title']} | {kind} | {chosen}{mark}{extra} | {result} | {dec(row['seconds'] / 60)} | "
                     f"{row['turns']} | {row['tools']} | {round(row['tokens_in'] / 1e3)} | {commit} |")
    lines += ["", "## Ответы агента и проверки", ""]
    for row in rows:
        lines.append(f"- **{row['task']}** — статус «{row['claimed']}»; проверка: {row['check'].replace(chr(10), '; ')}"
                     f"{'; не закоммичено и откатано: ' + ', '.join(row['left']) if row['left'] else ''}; "
                     f"ошибок инструментов {row['errors']}. Ответ: {row['answer'][:300] or '—'}")
    (out / "log.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Execution loop: агент берёт задачи из трекера и коммитит, стенд проверяет")
    parser.add_argument("name", help="имя прогона: папка experiment/<имя>")
    parser.add_argument("--provider", choices=["alibaba", "ollama"], default="alibaba")
    parser.add_argument("--model", default="qwen3.5-122b-a10b")
    parser.add_argument("--context", type=int, default=65536, help="контекст локальной модели")
    parser.add_argument("--gpu", type=int, default=-1, help="слоёв локальной модели на видеокарте; -1 — решит Ollama")
    parser.add_argument("--rules", type=Path, help="папка rules\\ прошлого прогона: его CLAUDE.md, .claude и промпт цикла")
    parser.add_argument("--minutes", type=int, default=15, help="лимит на задачу: дольше — зависла")
    parser.add_argument("--limit", type=int, help="не больше стольких задач за запуск")
    parser.add_argument("--stop-on-fail", action="store_true", help="остановиться на первом сбое")
    parser.add_argument("--resume", action="store_true", help="продолжить прерванный прогон")
    parser.add_argument("--report", action="store_true", help="только пересобрать log.md по results.jsonl и логам агента")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    out = ROOT / "experiment" / args.name
    work = Path(os.environ["TEMP"]) / "claude-rules" / args.name
    ml = work.with_name(f"{args.name}-ml")
    results = out / "results.jsonl"
    if args.report:  # профили — заново из логов: подсчёт мог поменяться после прогона
        rows = [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines()]
        for row in rows:
            info = stats(out / f"{row['session']}.jsonl")
            row["profiles"] = info["by_task"].get(row["task"], info["profiles"] if row["task"] == row["session"] else [])
        results.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        report(out, rows, json.loads((out / "meta.json").read_text(encoding="utf-8")))
        return
    if not args.resume:
        if out.exists() or work.exists():
            raise SystemExit(f"experiment/{args.name} или {work} уже есть — другое имя или --resume")
        setup(work, ml, out, args.rules and args.rules.resolve())
    elif not (out / "rules").exists():
        raise SystemExit(f"Прогона {args.name} нет — запустите без --resume")
    env, model = provider(args)
    env["PROJECT_DIR"] = str(ml)
    rows = [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines()] if results.exists() else []
    meta = {"name": args.name, "model": model, "provider": args.provider, "minutes": args.minutes,
            "started": datetime.now().strftime("%d.%m.%Y %H:%M")}
    if not (out / "meta.json").exists():
        (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))  # при --resume — дата и модель первого запуска
    done = 0
    while args.limit is None or done < args.limit:
        tasks = tracker(work)
        task = next((n for n, (_, status) in tasks.items() if state(status) == "открыта"), None)
        if not task:
            break
        print(f"{task} {tasks[task][0]} …", flush=True)
        session = attempt(work, task, env, model, out, args.minutes)
        rows += session
        done += 1
        with open(results, "a", encoding="utf-8") as file:
            file.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in session)
        report(out, rows, meta)
        for row in session:
            print(f"   {row['task']} {'✅' if not row['reasons'] else '❌ ' + '; '.join(row['reasons'])} · {row['seconds']} с · "
                  f"{profile(row)} · {round(row['tokens_in'] / 1e3)} тыс. токенов", flush=True)
        if args.stop_on_fail and any(row["reasons"] for row in session):
            break
    shutil.copy2(work / "TASKS.md", out / "TASKS.md")
    (out / "commits.txt").write_text(sh("git", "log", "--reverse", "--format=%h %s", cwd=work), encoding="utf-8")
    print(f"Готово: experiment/{args.name}/log.md; копия проекта — {work}")


if __name__ == "__main__":
    main()
