"""Ассистент для smoke-сценариев: порт 8765 — рабочий 8001 не занимаем; через 30 минут процесс завершается сам,
чтобы сервер, запущенный агентом в фоне, не остался висеть после прогона.
Запуск: .venv/Scripts/python.exe tests/serve.py → http://127.0.0.1:8765"""
import os
import sys
import threading
from pathlib import Path

os.environ.setdefault("PORT", "8765")  # настройки app читаются при импорте
sys.path.insert(0, str(Path(__file__).parent.parent))  # запуск файлом, а не модулем: app — из корня проекта

import uvicorn  # noqa: E402

from app import config, main  # noqa: E402

LIFETIME = 1800  # секунд: все сценарии с ответами модели проходят минут за 15

if __name__ == "__main__":
    stop = threading.Timer(LIFETIME, os._exit, [0])
    stop.daemon = True  # Ctrl+C останавливает сервер сразу, не дожидаясь таймера
    stop.start()
    uvicorn.run(main.app, host=config.HOST, port=config.PORT)
