# 07 — Cancellation

Клиент отменяет долгий tool call через `notifications/cancelled`. Тонкости: race condition «cancel пришёл уже после response», graceful shutdown внутри async tool'а, что делать, если tool уже дошёл до побочного эффекта.

_TBD: tool с проверкой отмены, симуляция race condition, wire-дамп, упражнение «что если cancel пришёл и response одновременно»._