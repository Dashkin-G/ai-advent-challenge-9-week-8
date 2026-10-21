"""Прогон тестов без Ollama, настоящего кэша векторов и ML-проекта: тест, который полез к ним без заглушки, упадёт здесь,
а не испортит data/ и проект. Запуск: .venv/Scripts/python.exe tests/run.py [-v]"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).parent

# настройки app читаются при импорте — подменяем до него; папки удалятся при выходе
data, project = tempfile.TemporaryDirectory(), tempfile.TemporaryDirectory()
os.environ.update(OLLAMA_URL="http://127.0.0.1:9", DATA_DIR=data.name, PROJECT_DIR=project.name)  # на порту 9 никого нет
sys.path.insert(0, str(TESTS.parent))

if __name__ == "__main__":
    sys.stderr.reconfigure(encoding="utf-8")  # unittest пишет в stderr; иначе русские докстринги — кракозябры
    unittest.main(module=None, argv=["unittest", "discover", "-s", str(TESTS), *sys.argv[1:]])
