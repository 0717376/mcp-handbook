# 02 — REST-обёртка

Оборачиваем учебный REST API задач в MCP. Показывает: `inputSchema`, сгенерированный из Python type hints; content blocks (`text`, `structuredContent`); как выбирать типы возвращаемых значений, чтобы LLM не парсила JSON из строки.

Также показываем **tool annotations** — подсказки модели о природе операции: `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`. Для REST-обёртки это естественно ложится на HTTP-глаголы: `GET` → readOnly, `DELETE` → destructive, `PUT` → idempotent, `POST` — обычно нет. Хост использует эти подсказки, чтобы, например, требовать подтверждения пользователя перед destructive-вызовом.

_TBD: stub REST API (FastAPI), MCP-сервер с явно заданными annotations на всех tool'ах, wire-дамп `tools/list` (видны annotations) и `tools/call` с content blocks._