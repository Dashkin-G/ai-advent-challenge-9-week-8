"""Одинаковая проверка боевой задачи для каждой генерации: GET /api/search без Ollama — векторы заглушкой.
Запуск из папки копии проекта: python <путь>/smoke.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.getcwd())
os.environ["DATA_DIR"] = tempfile.mkdtemp()  # заглушечные векторы не должны попасть в настоящий кэш

from fastapi.testclient import TestClient  # noqa: E402

from app import llm, main  # noqa: E402


async def fake_embed(texts):
    return [[float(len(t) % 7 + 1), 1.0] + [0.0] * 1022 for t in texts]


llm.embed = fake_embed
client = TestClient(main.app)  # без with: lifespan с MCP и прогревом модели не запускается
CASES = [{"q": "как запустить", "top": 2}, {"q": "как запустить"}, {}, {"q": "  "}, {"q": "x", "top": 11},
         {"q": "x", "top": 0}, {"q": "x", "top": "abc"}]
for params in CASES:
    response = client.get("/api/search", params=params)
    print(params, "→", response.status_code, str(response.json())[:220])
