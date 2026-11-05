# Построитель чертежей для школьной планиметрии

Локальное приложение, преобразующее русскоязычное условие задачи в проверяемый геометрический чертёж.
**Streamlit + Canvas → FastAPI → правила / Ollama → Pydantic → SymPy + SciPy.**
Облачные API и ключи не требуются. Программа строит один допустимый экземпляр, но не решает задачу и не доказывает теоремы.

## Запуск

Проверенная среда — Python 3.10, Node.js 22 (только JS-тест), Chrome (только браузерный тест).
Установите [Ollama](https://ollama.com/) и подготовьте окружение:

```powershell
py -3.10 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
ollama pull deepseek-coder-v2:16b
# Если Ollama ещё не запущена:
ollama serve
```

Не перезаписывайте существующий `.env` командой копирования. После установки модели:

```powershell
.venv\Scripts\python launch.py
```

- Интерфейс: http://127.0.0.1:8501
- Документация API: http://127.0.0.1:8000/docs
- `Ctrl+C` останавливает API и интерфейс; Ollama остаётся работать.

Раздельный запуск из корня проекта:

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
python -m streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501
```

Модель по умолчанию — `deepseek-coder-v2:16b`, контекст 4096. Для неё рекомендуется GPU с 12 ГБ VRAM; доступность и скорость зависят от оборудования. Можно выбрать другую установленную совместимую модель через `OLLAMA_MODEL` в `.env`. Для работы без нейросети явно установите `PARSER_MODE=rules` и перезапустите API. При недоступности Ollama скрытого переключения на правила нет.

Переменные `.env`: `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT`, `OLLAMA_CONTEXT`, `PARSER_MODE`. Адрес backend для Streamlit при необходимости задаётся переменной окружения `GEOMETRY_API_URL`.

## Работа с приложением

1. Введите условие или загрузите готовый пример из боковой панели.
2. Нажмите «Сгенерировать чертёж».
3. Сверьте распознанные объекты, параметры и отношения с исходным текстом. Численная проверка относится к распознанной схеме и не гарантирует полноту понимания условия.
4. Колесо мыши меняет масштаб, перетаскивание фона перемещает вид. Кнопка «Сбросить вид» центрирует построение. Реализован pinch двух указателей, но физический сенсорный жест требует ручной проверки.
5. Перетащите точку: после отпускания сервер пересчитает зависимые объекты. При отказе останется прежнее построение.
6. Скачайте PNG (300 DPI) или SVG отдельными кнопками.
7. Успешные генерации доступны через «Обновить историю» и «Открыть построение». История хранится в `data/history.sqlite3`, создаваемой автоматически; перемещения точек отдельно в неё не записываются.

## Архитектура и файлы

| Путь | Назначение |
|---|---|
| `backend/main.py` | HTTP API, построение, редактирование, экспорт и история |
| `backend/parser.py`, `*constructions.py`, `advanced_graphs.py` | Правила распознавания и графы геометрических связей |
| `backend/llm_parser.py`, `semantic_validation.py`, `text_normalization.py` | Ollama, нормализация чисел и проверка сохранения условий |
| `backend/models.py` | Схема Pydantic и валидация ссылок/чисел |
| `backend/sympy_solver.py` | Вычисление координат и проверка ограничений |
| `backend/config.py`, `history.py`, `sample_tasks.py` | Конфигурация, SQLite, готовые примеры |
| `frontend/app.py`, `geometry_component/index.html` | Streamlit и интерактивный Canvas |
| `frontend/drawing.py`, `highlight.py` | Экспорт и безопасная подсветка текста |
| `tests/` | Все тесты и исходные данные проверок |
| `OLD/` | Неизменённая прежняя версия репозитория, не часть текущего запуска |
| `final_bshakurov_application.md` | Актуальное описание проекта |
| `final_bshakurov_userscripts.md` | Актуальные пользовательские сценарии |

Старый решатель, PDF и парсер учебника сохранены только в `OLD`. Данные учебника для тестового запускателя находятся в `tests/fixtures/textbook.json`. Отдельный debug-интерфейс удалён; служебные проверки доступны через API и тесты.

## API

- `GET /health` — состояние API, не готовность нейросети.
- `GET /ollama` — доступность Ollama и список моделей.
- `GET /schema` — JSON Schema геометрических данных.
- `POST /parse`, `POST /solve` — `{"text":"...", "parser_mode":"ollama"}`; необязательный `model`. `/solve` также принимает `custom_schema`.
- `POST /update-point` — `schema_data`, `points`, `point_name`, `new_coords`.
- `POST /export/png`, `POST /export/svg` — `schema_data`, `points`; перед экспортом проверяются ограничения.
- `GET /history`, `GET /history/{id}` — сохранённые генерации.

HTTP 422 — некорректный ввод, неподдержанная конфигурация или неудачное построение; HTTP 503 — ошибка Ollama. Ошибка не заменяется выдуманным чертежом.

## Тесты и стиль

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m unittest discover -s tests -v
python -m backend.check_samples
node tests/component_smoke.cjs
python tests/services_smoke.py
python tests/browser_smoke.py
python -m ruff check .
python -m ruff format --check .
```

Браузерная проверка требует установленный Google Chrome. `pytest` запускает весь offline-набор; `unittest` — классы регрессионных тестов. HTTP- и браузерные smoke-тесты самостоятельно запускают сервисы на временных портах. JS-тест использует имитацию DOM, браузерный тест — настоящий Chrome.

Интеграционные проверки с реальной Ollama (могут занимать несколько минут):

```powershell
python -m backend.check_samples --mode ollama
python tests/integration/recheck_advanced_20.py
python tests/integration/recheck_advanced_qwen.py
python tests/integration/recheck_ege_93749202.py
python tests/integration/recheck_ege_93751277.py
```

Они сохраняют отчёты и изображения в игнорируемую папку `artifacts/`; внешние наборы используют изолированную историю. Исследовательский запуск по учебнику: `python tests/textbook_runner.py --limit 10 --mode rules`. Он сообщает отказы и не является эталоном поддержки всего учебника.

Результаты проверки после очистки: [docs/verification.md](docs/verification.md). Ограничения: [docs/requirements.md](docs/requirements.md).

## Ограничения и приватность

- Поддержаны не все произвольные формулировки, касательные, дуги и многосоставные конфигурации. Недостающие связи исходного рисунка нужно описать словами.
- Правила дополняют ответ Ollama; поддержанные детерминированные конструкции имеют приоритет. Это отражается в `parser_engine`.
- Геометрия решается преимущественно численно: малая невязка не доказывает утверждение задачи и не означает единственности решения.
- Natasha не используется, интерактивная графика выполнена на Canvas, Matplotlib используется для экспорта.
- `.env`, пользовательская история, локальные зависимости и результаты прогонов не публикуются. Тексты сохраняются локально в SQLite; используйте локальный адрес Ollama для локальной обработки.
- Запуск предназначен для loopback, без публичного размещения: авторизации и ограничений запросов нет.
