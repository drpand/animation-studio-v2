# E2E Test Report — Animation Studio v2 «РОДИНА»
## Сцена 1: кабина самолёта, Ева и Гарри, ночь

**Дата:** 2026-04-05  
**Тестировщик:** QA-Engineer (Playwright + MCP)  
**Сервер:** localhost:7860  
**Круги Critic/Fixer:** 2 (6/10 → 7/10)

---

## Итоговый результат: ⚠️ PARTIAL PASS

| Категория | Результат |
|-----------|-----------|
| Сервер (health) | ✅ PASS |
| UI — главная страница | ✅ PASS |
| UI — 10 агентов | ✅ PASS |
| UI — навигация | ✅ PASS |
| Загрузка PDF сценария | ✅ PASS (после фикса datetime bug) |
| Конвейер — Writer | ✅ PASS (APPROVED round 1) |
| Конвейер — Director | ✅ PASS (APPROVED round 1-2) |
| Конвейер — HR Casting | ✅ PASS (APPROVED round 1-3) |
| Конвейер — DOP+Art+Sound | ❌ FAIL — **DEADLOCK** |
| Конвейер — Storyboarder финал | ⏸️ НЕ ДОСТИГНУТ |
| Конвейер — Kie.ai генерация | ⏸️ НЕ ДОСТИГНУТ |
| Storyboard UI | ✅ PASS (карточка отображается) |
| Негативные тесты | 10/12 PASS |

---

## Найденные баги

### 🔴 CRITICAL: Deadlock на шаге 4 (параллельные DOP+Art+Sound)
**Описание:** `asyncio.gather` для трёх агентов (dop, art_director, sound_director) не завершается.
**Причина:** Два одновременных запуска конвейера в 16:54:54 (дубликаты) — вероятно race condition в файловой блокировке discussion_log.json.
**Влияние:** Конвейер не доходит до Storyboarder финал, Kie.ai генерации, сохранения в БД.
**Статус:** НЕ ИСПРАВЛЕН

### 🟡 MEDIUM: datetime import shadowing в orchestrator_api.py
**Описание:** `from datetime import datetime` внутри try-блока функции `upload_script` затенял модульный import, вызывая `UnboundLocalError`.
**Исправление:** Удалён дублирующий import (строка ~274).
**Статус:** ✅ ИСПРАВЛЕН

### 🟡 MEDIUM: Валидация пробелов не работает
**Описание:** Отправка задачи с `"   "` (только пробелы) возвращает 200 вместо 400.
**Статус:** НЕ ИСПРАВЛЕН

### 🟡 LOW: Защита от дубликатов upload-script не сработала
**Описание:** Повторная загрузка того же файла не вернула `duplicate: true`.
**Статус:** НЕ ИСПРАВЛЕН

---

## Что работает

1. ✅ Сервер FastAPI на порту 7860 — health check OK
2. ✅ 10 AI-агентов загружены, все в статусе idle/working
3. ✅ Навигация: Пульт, Сториборд, Агенты, Персонажи
4. ✅ Загрузка PDF сценария через Orchestrator (после фикса)
5. ✅ Critic/Fixer цикл — Writer, Director, HR Casting проходят оценку
6. ✅ Storyboard UI отображает карточку сцены
7. ✅ Негативные тесты: пустая задача (400), несуществующий endpoint (404), несуществующая сцена (not_found), невалидный файл (400), health check, agents list, registry, characters API

---

## Рекомендации

1. **Исправить deadlock** — добавить mutex для параллельных вызовов в `run_scene_pipeline`, или ограничить concurrency через `asyncio.Semaphore`
2. **Добавить debounce** для кнопки «Выполнить» чтобы предотвратить дублирующие запуски
3. **Исправить валидацию пробелов** — `if not task.strip()` вместо `if not task`
4. **Добавить timeout** для `asyncio.gather` в параллельных вызовах DOP+Art+Sound
5. **Исправить защиту от дубликатов** — проверить логику сравнения timestamps

---

## Скриншоты

- `e2e-step1-main-page.png` — главная страница, 10 агентов
- `e2e-storyboard.png` — Storyboard с карточкой Сцена 1
