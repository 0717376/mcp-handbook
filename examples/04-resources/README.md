# 04 — Resources

Те же задачи, но как resources (URI `tasks://...`), а не tools. `resources/list`, `resources/read`, `resources/subscribe`, `notifications/resources/list_changed`, `notifications/resources/updated`. Правило выбора: tool = LLM решает, resource = приложение решает.

Дополнительно раскрываем две смежные фичи:

- **Pagination** (`cursor` / `nextCursor`). Когда ресурсов сотни, `resources/list` отдаёт их страницами. Имитируем много задач и показываем, как клиент дотягивает остальные страницы по `nextCursor`. Те же правила действуют и для `tools/list` / `prompts/list`.
- **Resource templates** (`resources/templates/list`). Параметризованные URI вида `tasks://{status}/{id}` — сервер не перечисляет все конкретные URI, а описывает **шаблон**, по которому клиент их формирует. Полезно, когда пространство ресурсов большое или динамическое.

_TBD: сервер с resources + templates, subscribe/unsubscribe, эмуляция изменения данных, демо pagination на большом каталоге, поток notifications._