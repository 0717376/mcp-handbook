# 06 — Progress

Long-running tool, который шлёт `notifications/progress` пока работает. Показывает: `_meta.progressToken` в request → notification с тем же токеном → финальный response. Первый реальный bidirectional flow в проекте (сервер шлёт нотификации параллельно обработке request'а).

Заодно раскрываем **logging capability**. Сервер объявляет в `initialize` капабилити `logging`, клиент может задать уровень через `logging/setLevel`, а сервер шлёт структурированные записи через `notifications/message` (`debug` / `info` / `warning` / `error` / и т.д.). Логи относятся ко всей сессии, в отличие от `progress`, привязанного к конкретному request'у через токен. Показываем, как эти два потока нотификаций сосуществуют в одном соединении и чем они отличаются семантически.

_TBD: tool с эмулированной долгой работой, wire-дамп с interleaved progress + logging + финальным response, разбор того, как token связывает progress с request'ом, и почему logs — session-scoped._