"""Скорость модели Ollama на этом железе: чтение промпта и генерация (ток/с), память под модель с этим контекстом.
Промпт — CLAUDE.md (~3 тыс. токенов); fim — подсказка автокомплита в середине app/rag.py; gpu=N — слоёв на видеокарте
(gpu=0 — только процессор; без него Ollama кладёт на видеокарту сколько влезет).
Запуск из корня: python experiment/bench.py <модель> [контекст] [fim] [gpu=N]"""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLLAMA = "http://127.0.0.1:11434"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # мимо системного прокси


def call(path, body=None):
    """Ответ Ollama — dict; без body — GET."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(OLLAMA + path, data=data, headers={"Content-Type": "application/json"})
    return json.load(opener.open(request, timeout=1800))


model, flags = sys.argv[1], sys.argv[2:]
ctx = int(flags[0]) if flags and flags[0].isdigit() else 8192
body = {"model": model, "stream": False, "keep_alive": "10m", "options": {"num_ctx": ctx, "temperature": 0.2, "num_predict": 128}}
for flag in flags:
    if flag.startswith("gpu="):
        body["options"]["num_gpu"] = int(flag[4:])
stamp = f"# {time.time()}\n"  # новое начало промпта: Ollama не возьмёт его из кэша прошлого замера
if "fim" in flags:
    code = (ROOT / "app" / "rag.py").read_text(encoding="utf-8")
    cut = code.index("\n", len(code) // 2)  # курсор — в середине файла
    # окно как у Continue с maxPromptTokens 1024: ~800 токенов до курсора и ~200 после
    body.update(prompt=stamp + code[max(0, cut - 2800):cut], suffix=code[cut:cut + 700])
    body["options"]["num_predict"] = 48
else:
    rules = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    body["prompt"] = f"{stamp}{rules}\n\nПеречисли пять главных запретов из правил выше."
    if "thinking" in call("/api/show", {"model": model}).get("capabilities", []):
        body["think"] = False  # замеряем скорость, а не длину размышлений
started = time.perf_counter()
answer = call("/api/generate", body)
total = time.perf_counter() - started
loaded = next(m for m in call("/api/ps")["models"] if m["name"] in (model, f"{model}:latest"))
prompt, generated = answer["prompt_eval_duration"] / 1e9, answer["eval_duration"] / 1e9
print(f"{model} · контекст {loaded.get('context_length', ctx)} · память {loaded['size'] / 2**30:.1f} ГБ, "
      f"на видеокарте {loaded['size_vram'] / loaded['size']:.0%} · "
      f"промпт {answer['prompt_eval_count']} ток. — {answer['prompt_eval_count'] / prompt:.0f} ток/с · "
      f"ответ {answer['eval_count']} ток. — {answer['eval_count'] / generated:.1f} ток/с · "
      f"загрузка {answer['load_duration'] / 1e9:.1f} с · всего {total:.1f} с")
