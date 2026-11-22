# cyberdoc — архитектура

AI-ассистент по научным статьям. Кейс ЮФУ + ВИНИТИ РАН, трек Cyber Garden.
Извлекает факты, формулы и числа из PDF, связывает каждый факт с точным
местом в статье, нормализует данные и показывает их в интерфейсе
с поиском и фильтрами.

## Структура модулей

    cyberdoc/
    ├── app.py                  # точка входа (QApplication, тема)
    ├── theme.py                # QSS-стили (тёмная тема), style_combo()
    ├── parser.py               # парсинг ответа LLM:
    │                           #   [[FORMULA p.N: ...]], [[REF p.N: "цитата"]],
    │                           #   [[PAGES:...]] → dict(text, formulas, anchors)
    ├── renderer.py             # LaTeX→PNG (matplotlib, base64), LaTeX→unicode,
    │                           #   ответ → HTML со ссылками anchor:/page:/formula:
    ├── pdfdoc.py               # PDFDocument (обёртка fitz):
    │                           #   текст, поиск, resolve_anchor (точный rect
    │                           #   цитаты с фолбэками), find_formula_rect
    │                           #   (кластеры векторных рисунков), закладки,
    │                           #   смещение нумерации страниц, оглавление
    ├── client.py               # DeepSeekClient: ключ ТОЛЬКО из окружения
    │                           #   (диалог ввода на сессию), retry×3 с backoff,
    │                           #   rank_pages — cosine-ранкинг страниц под
    │                           #   вопрос, build_prompt (системный промпт)
    ├── export_utils.py         # экспорт истории+закладок в JSON, сущностей в CSV
    ├── research.py             # извлечение и проверки для solar-домена
    ├── research_rag.py         # извлечение и проверки для RAG-домена
    │                           #   (7 таблиц по schema.json, present_not_extractable
    │                           #   → issues.csv, не в results.csv)
    ├── export_rag.py           # экспорт 7 CSV RAG-домена по schema.json
    ├── research_dialog.py      # окно «Научные данные»: 7 вкладок,
    │                           #   переключение домена solar/rag,
    │                           #   экспорт CSV + JSON
    └── ui/
        ├── main_window.py      # главное окно: список документов (мульти-PDF,
        │                       #   поиск по всем), вопрос/ответ, история ответов,
        │                       #   экспорт, статусбар («Контекст: стр. ...»),
        │                       #   горячие клавиши, автосохранение сессии
        ├── pdf_viewer.py       # вьюер: миниатюры страниц, оглавление (TOC),
        │                       #   закладки с заметками, маркер-рамка
        │                       #   (rubber band — выделяет и формулы, и графики),
        │                       #   навигация назад/вперёд (Alt+←/→), зум
        │                       #   (Ctrl+колесо, «по ширине»), индикатор
        │                       #   страниц с совпадениями (TickOverlay),
        │                       #   пульс-подсветка найденного места
        ├── answer_window.py    # отдельное окно ответа (поиск, листание)
        └── entity_panel.py     # таблица сущностей: числа с единицами + формулы,
                                #   фильтры (тип/текст/диапазон страниц),
                                #   двойной клик → переход к месту в PDF
    main.py                     # bootstrap: python main.py

## Поток данных

    PDF ──fitz──► pages_text ──rank_pages(question)──► top-12 страниц
                                                        │
                           системный промпт + контекст ▼
                                            DeepSeek API (retry ×3)
                                                        │
                                parse_answer: формулы [[FORMULA p.N:...]],
                                якоря [[REF p.N: "цитата"]] ──► entry
                                                        │
            ┌───────────────────────────────────────────┼────────────────────┐
            ▼                                           ▼                    ▼
    render_answer_html                        EntityPanel             resolve_anchor
    формулы→PNG, [стр. N]→ссылки             числа+единицы,          search_for(цитата)
    с ✓/⚠ подтверждением                      фильтры, экспорт       → fitz.Rect
            │                                           │                    │
            ▼                                           ▼                    ▼
      QTextBrowser ◄──── anchor:/formula: ──── PDFViewer: пульс+центрирование,
                                              миниатюры, закладки, маркер-рамка

## Два домена ТЗ

**Solar** (`research.py`) — параметры и результаты тонкоплёночных солнечных элементов: PCE, Voc, Jsc, FF, Rs, Rsh, T80, слои, условия измерения. Экспорт в 7 CSV: `publications, materials, devices, layers, measurements, results, issues` (схема `export_utils.export_submission_csv`).

**RAG** (`research_rag.py`) — метрики информационного поиска и RAG: Recall@k, Precision@k, MRR, NDCG, EM, F1, BLEU, ROUGE-L, UniEval, tokens per query, latency. Экспорт в 7 CSV по `submission_template/schema.json`: `publications, configurations, datasets, tasks, experiments, results, issues` (`export_rag.export_rag_submission`).

Таблицы и рисунки с метриками, которые строковый парсер не извлёк, попадают в `issues.csv` как `present_not_extractable` (не в `results.csv`), чтобы `check_submission.py` не падал на пустом `metric_name` и чтобы факт «значение есть, но не извлечено» был зафиксирован.

## Привязка факта к месту (ключевой критерий жюри)

1. Модель после каждого факта выдаёт `[[REF p.N: "дословная цитата"]]`.
2. `PDFDocument.resolve_anchor` ищет цитату `page.search_for()`; при
   неточном совпадении — фолбэк на первые/последние 10/7/5/3 слов.
3. Найденный `fitz.Rect` → вьюер центрируется на нём и показывает
   оранжевый «пульс» 2.5 с.
4. Если rect не найден — в ответе ⚠ «не подтверждено» (проверка достоверности).
5. Формулы: `find_formula_rect` кластеризует векторные рисунки и картинки
   страницы и выбирает кластер ниже якоря — формулы и графики в PDF
   «не текст», поэтому их bbox находится через get_drawings().

## Проверка сабмишна

    python tools/check_submission.py ~/p001_submission test --json-report report.json

Коды выхода: 0 — всё прошло; 1 — структурные ошибки (несовпадение колонок, дубли ключей, ссылки на несуществующие id); 2 — предупреждения (нужна проверка источников, в т.ч. цитат). Код 2 допустим по ТЗ.

## Запуск

    pip install -r requirements.txt
    python main.py

При первом поиске приложение открывает окно авторизации выбранного провайдера.
Ключи и ID действуют только в памяти текущего запуска и никуда не сохраняются.

## Горячие клавиши

| Клавиши | Действие |
|---|---|
| Ctrl+O | Загрузить PDF |
| Ctrl+F | Поиск по ответу |
| F3 / Shift+F3 | След./пред. совпадение в ответе |
| Ctrl+колесо | Зум в PDF |
| Alt+← / Alt+→ | Назад/вперёд по переходам в PDF |
