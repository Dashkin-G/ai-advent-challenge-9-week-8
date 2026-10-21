"""Проверка задачи bug-fix: сервер ассистента с HOST=0.0.0.0 и с HOST=127.0.0.1 — отвечают ли все три MCP-сервера:
git — ветка в /api/status, crm — очередь в /api/support/status, files — контекст в /api/files/run. Ollama не нужен.
Запуск из папки копии проекта: python <путь>/bug-fix.py"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

PORT = 8799  # не 8001 — там может работать настоящий ассистент
HOSTS = ["0.0.0.0", "127.0.0.1"]  # из бага и обычный запуск


def check(host):
    """Сервер с этим HOST в потоке → три запроса через MCP → строка итога."""
    os.environ.update({"HOST": host, "PORT": str(PORT), "DATA_DIR": tempfile.mkdtemp(),  # заглушки не в настоящий data/
                       "OLLAMA_URL": "http://127.0.0.1:9"})  # Ollama нет: прогрев и шаг модели сразу падают
    sys.path.insert(0, os.getcwd())
    import httpx2
    import uvicorn

    from app import main

    server = uvicorn.Server(uvicorn.Config(main.app, host=host, port=PORT, log_level="critical"))
    threading.Thread(target=server.run, daemon=True).start()
    started = time.perf_counter()
    while not server.started and time.perf_counter() - started < 20:
        time.sleep(0.1)
    try:
        with httpx2.Client(base_url=f"http://127.0.0.1:{PORT}", trust_env=False, timeout=60) as client:
            project = client.get("/api/status").json()["project"]
            crm = client.get("/api/support/status").json()["crm"]
            events = [json.loads(line) for line in client.post("/api/files/run", json={"goal": "x"}).text.splitlines()]
    finally:
        server.should_exit = True
    context = any(e["type"] == "context" for e in events)
    error = next((e["message"] for e in events if e["type"] == "error"), "")
    return " · ".join([
        f"git ✓ ветка {project['branch']}" if project.get("branch") else f"git ✗ {project.get('error')}",
        f"crm ✓ обращений {len(crm['tickets'])}" if "tickets" in crm else f"crm ✗ {crm.get('error')}",
        "files ✓ контекст получен" if context else f"files ✗ {error}",
    ])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")  # лог приложения по-русски, по умолчанию — cp1251
    if len(sys.argv) > 1:
        print(check(sys.argv[1]))
    else:  # настройки читаются при импорте app — каждый HOST в своём процессе
        for host in HOSTS:
            done = subprocess.run([sys.executable, __file__, host], capture_output=True, text=True, encoding="utf-8")
            print(f"HOST={host}: {done.stdout.strip() or done.stderr.strip().splitlines()[-1]}")
