# Аудит снимка StudyForge и изменения 2.0

Дополнение 2.1: добавлены адаптер внешнего AI-провайдера, журнал бюджета, схемы ответов и тесты интеграции. Обновлены выбор провайдера, SQLite, API настроек и задач, отображение провайдера, источников и метрик. Кеш использует провайдера и модель. Проверено 34 Python-теста, включая адаптер на реальном SDK с подменённым HTTP-транспортом и тест миграции истории, 5 Node.js-тестов, оба сценария Chromium и миграция на копии рабочей SQLite. Платные запросы не отправлялись.

Дополнение по OCR: обновлены `app/config.py`, `app/schemas.py`, `app/routers/documents.py`, `app/services/pdf_service.py`, `app/static/api.js`, `app/static/app.js`, зависимости и инструкции. Добавлены `app/services/ocr.py`, `app/services/ocr_worker.py` и `tests/test_ocr.py`. Новый `GET /api/documents/upload-progress/{upload_id}` выдаёт ход обработки в рамках текущей сессии при передаче `X-Upload-ID` с загрузкой. Старый контракт загрузки без заголовка сохраняется. Проверены 24 Python-теста с реальными языковыми моделями, 5 Node.js-тестов и сценарий Chromium с четырёхстраничным сканом, прогрессом и генерацией конспекта.

Фактический корень снимка — `studyforge_kimi_snapshot/`. В нём находились Python-бэкенд, статические файлы, 14 тестов, окружение и SQLite. Разработка велась в отдельной копии исходников. Рабочая база, загруженные PDF и окружение из снимка не включены в поставку.

| Функция снимка | Файлы | Что обнаружено | Что изменилось |
|---|---|---|---|
| Инициализация и статическая раздача | `app/main.py` | FastAPI запускает SQLite и отдаёт HTML. JS в снимке — заглушка | Lifespan и полностью новый SPA |
| PDF | `app/routers/documents.py`, `app/services/pdf_service.py`, `storage.py` | Загрузка, метаданные и превью работали. OCR отсутствует. Ошибки отдельных страниц скрывались. Multipart обрабатывался до проверки файла | Предел тела до сохранения, лимиты страниц и символов, ошибки извлечения, обработка вне event loop |
| SQLite и сессия | `app/db.py`, `app/security.py` | WAL и фильтрация по cookie. Внешние ключи SQLite включались только на одном соединении | Каскады на каждом соединении, проверка существования сессии, добавление колонок при старте |
| Очередь и история | `app/routers/generations.py`, `app/services/jobs.py` | Кеш результатов и фоновые задачи. При дубле задача могла остаться в `pending` | Атомарное переиспользование активной задачи, явный статус, метка провайдера, защита от удаления источника во время задачи |
| Квота | `app/routers/quota.py`, `app/services/usage.py` | Резерв и последующее списание. Неделя расчёта могла меняться во время задачи, резерв пропадал при рестарте | Неделя хранится с резервом, расчёт и результат фиксируются вместе, рестарт возвращает резерв |
| LLM | `app/services/llm/`, `app/schemas.py` | Mock и OpenAI, три формы результата. Режим подменялся на Mock без метки, заглушка теста ставила верный ответ первым | Причина выбора Mock в API, режим у новых материалов, обработка ошибок провайдера, shuffle в режиме прохождения |
| Тесты | `tests/test_app.py`, `run_tests.py` | 14 исходных проверок прошли на копии до изменений | Сохранены и дополнены проверками SQLite, API, адаптера LLM, перестановок и Chromium |

## Контракты API

Маршруты снимка сохранены. Все операции над пользовательскими данными связываются с анонимным HttpOnly cookie `sf_client_id`. Идентификатор хранится в браузере, ключ провайдера остаётся в конфигурации сервера.

| Метод и путь | Вход | Результат |
|---|---|---|
| `GET /api/health` | — | `{"status":"ok"}` |
| `GET /api/quota` | — | `used`, `limit`, `remaining`, `week_start` |
| `POST /api/documents` | multipart, поле `file` | 201, документ и массив превью `pages` |
| `GET /api/documents` | — | Список документов с `id`, `filename`, `size`, `page_count`, `status`, `created_at` |
| `GET /api/documents/{id}` | Числовой ID | Документ и `pages`, каждое превью содержит `page_num` и `text_preview` |
| `DELETE /api/documents/{id}` | Числовой ID | 204. Вернёт 409, если по документу сейчас выполняется генерация |
| `POST /api/generations` | JSON с `document_id`, `page_from`, `page_to`, `material_type` | 201. `accepted` с `job_id` или `existing` с сохранённым `generation` |
| `GET /api/jobs/{job_id}` | ID задачи | `pending`, `running`, `done` или `error`, плюс сообщение ошибки или результат |
| `GET /api/generations` | Необязательный `?document_id=` | История успешных генераций |
| `GET /api/generations/{id}` | Числовой ID | Генерация с `result`, `tokens_used`, `created_at`, типом, документом и диапазоном. Добавлено поле `provider` |
| `GET /api/settings` **(новый)** | — | Фактический и настроенный режимы, причина fallback и лимиты загрузки и страниц |

Типы материалов: `summary` содержит `title` и `sections[{title, points}]`. `flashcards` содержит `title` и `cards[{question, answer}]`. `quiz` содержит `title` и `questions[{question, options, correct_index}]`, четыре варианта и индекс с нуля. Формы документированы в Swagger UI по `/docs`.

При прохождении теста исходная позиция служит ID варианта. Fisher–Yates переставляет пары ID и текста. Новый индекс и буква вычисляются из ID правильного варианта. Тесты перебирают все 24 перестановки для каждого из четырёх исходных индексов, включая одинаковые подписи. Содержимое и порядок на сервере сохранены для совместимости. Новые запросы к провайдеру предписывают избегать вариантов, ссылающихся на буквы или позиции.

## Изменённые и новые файлы

- Конфигурация и документация: `.env.example`, `.gitignore`, `README.md`, `AUDIT.md`, `requirements.txt`, `requirements-dev.txt`.
- Бэкенд: `app/config.py`, `app/db.py`, `app/main.py`, `app/schemas.py`, `app/security.py`, `app/routers/documents.py`, `app/routers/generations.py`.
- Сервисы: `app/services/jobs.py`, `app/services/pdf_service.py`, `app/services/storage.py`, `app/services/upload_limit.py`, `app/services/usage.py`, `app/services/llm/mock.py`, `app/services/llm/openai_provider.py`.
- Интерфейс: `app/static/index.html`, `app/static/styles.css`, `app/static/app.js`, `app/static/api.js`, `app/static/ui.js`, `app/static/study.js`, `app/static/quiz.mjs`, `app/static/mark.svg`.
- Ресурсы: `app/static/vendor/icons.svg`, `Inter-LICENSE.txt`, `Lucide-LICENSE.txt` и `inter-{latin,latin-ext,cyrillic,cyrillic-ext}-wght-normal.woff2` в том же каталоге.
- Тесты: `tests/test_reconstruction.py`, `tests/quiz.test.mjs`, `tests/browser_smoke.py`. Исходные `tests/test_app.py` и `run_tests.py` сохранены без изменений.

## Выполненные проверки

- На Windows с Python 3.12.10 установлены зависимости, `pip check` не нашёл конфликтов. Uvicorn запустился с отдельной тестовой базой.
- `pytest`: 21 из 21. Исходный `run_tests.py`: 14 из 14. В тестовом окружении Starlette предупреждает об устаревшем способе подключения HTTP-клиента.
- `node --test tests/quiz.test.mjs`: 5 из 5. Синтаксис модулей JavaScript проверен.
- Chromium через Playwright: загрузка PDF, ошибка битого файла, предпросмотр, проверка диапазона, три вида материалов в Mock Mode, перелистывание карточек, квиз с верным, неверным и пропущенными ответами, повтор теста, история, удаление, темы и восстановление после сетевой ошибки. Навигация с клавиатуры проверена. Ширины окна: 1440, 768, 390 и 320 px.
- Копия SQLite из снимка прошла миграцию при двух последовательных запусках и `PRAGMA integrity_check`. Число строк в исходных таблицах сохранилось.
- Реальный платный API и отдельные браузерные движки Firefox и WebKit не проверялись.

