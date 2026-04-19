# 10 — Streamable HTTP

Тот же tasks-сервер, но на HTTP вместо stdio. Показывает:

- Один endpoint, POST для отправки сообщений.
- Опциональный SSE-upgrade для серверных notifications и server→client requests.
- Сессии через `Mcp-Session-Id` header (выдаётся сервером в ответ на `initialize`).
- Версионирование через `MCP-Protocol-Version` header.
- Resumability через `Last-Event-ID` на переподключении SSE.

_TBD: сервер на FastMCP в HTTP-режиме, curl-команды для каждого шага handshake'а, демо обрыва и переподключения._