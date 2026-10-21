# Прогон qa-feature-v1 — qwen3.5-122b-a10b (alibaba), профиль qa, задача qa-feature, 21.10.2026 16:45

Время: 649 с · ходов: 71 · ошибок инструментов: 4 · 
токенов: вход 2315908, выход 8217
Инструменты: Bash ×10, Edit ×2, Glob ×2, mcp__playwright__browser_click ×6, mcp__playwright__browser_close ×1, mcp__playwright__browser_find ×1, mcp__playwright__browser_navigate ×5, mcp__playwright__browser_snapshot ×2, mcp__playwright__browser_take_screenshot ×14, mcp__playwright__browser_type ×5, mcp__playwright__browser_wait_for ×15, Read ×5, Write ×1

## Ответ Claude Code

Сервер остановится сам через 30 минут (timeout по умолчанию).

---

**Итог: ✅ всё прошло** · тесты: 30/30 · smoke: 9/9 сценариев

Отчёт: `reports/2026-10-21_16-45/report.md`

**Что изменилось:** добавлен поиск по очереди тикетов в `static/support.html` — проверено новым сценарием С5 (5 шагов, все прошли).

**Ничего не сломалось.**
