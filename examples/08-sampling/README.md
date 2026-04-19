# 08 — Sampling (server → client request)

Сервер отправляет `sampling/createMessage` **клиенту** — просит host прогнать prompt через LLM и вернуть результат. Здесь симметричность протокола из §3 перестаёт быть теорией: роли request-sender и responder меняются местами.

Нужен клиент, который умеет sampling. MCP Inspector подходит, продвинутые host'ы тоже. Claude Desktop на момент написания sampling не поддерживает — потребуется Inspector или самописный клиент.

_TBD: сервер с tool, который внутри себя делает sampling к клиенту; wire-дамп обеих сторон; обсуждение, почему proxy/gateway часто ломаются на этом направлении._