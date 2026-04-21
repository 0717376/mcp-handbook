# 06 — Notifications

Первая глава, где **сервер сам пишет в клиент**, вне контекста чьего-то request'а. До этого всё шло так: клиент спросил — сервер ответил; в `03-errors/` видели, что error тоже возвращается на тот же request. Теперь сервер инициирует сообщения сам, по своей логике, и они прилетают асинхронно — в любой момент между обычными response'ами.

Цель главы — разобрать этот канал целиком, на всех его флаварах, потому что в протоколе они устроены одинаково (JSON-RPC notification без `id`), а семантически закрывают разные задачи:

| Флавор | Что говорит | Привязка |
|---|---|---|
| `notifications/<kind>/list_changed` | «каталог чего-то поменялся — перечитай список» | к примитиву (tools / prompts / resources) |
| `notifications/resources/updated` | «вот этот URI обновился — перечитай, если интересно» | к конкретному ресурсу, на который ты подписан |
| `notifications/progress` | «долгая работа по твоему request'у — вот текущее состояние» | к request'у через `_meta.progressToken` |
| `notifications/message` | «я хочу залогировать что-то уровня X» | к сессии целиком |

Одна концептуальная модель «server→client async», четыре канала с разным смыслом. Разбираем все в этой главе, чтобы не расщеплять понимание.

## Мотивация: «живой сайдбар» из 05

Возвращаемся к сценарию, обещанному в [05-resources § Как это выглядит в реальном host'е](../05-resources/README.md#как-это-выглядит-в-реальном-hoste). Там мы сказали: панель «Мои задачи» в UI подписана на `tasks://all`, при любом изменении сервер шлёт `notifications/resources/updated`, клиент перечитывает, панель обновляется — без рефреша, без запроса к модели. Вот этот поток тут и соберём на реальном сервере задач из 05.

## Что трогаем

1. **`list_changed`** — `notifications/resources/list_changed`, `tools/list_changed`, `prompts/list_changed`. Три метода с одинаковым скелетом.
2. **`subscribe` + `updated`** — `resources/subscribe` / `resources/unsubscribe` + `notifications/resources/updated`. Single-resource feed.
3. **FastMCP-баг с `subscribe: false`** — SDK 1.27.0 хардкодит capability в false, параллель к [03-errors/](../03-errors/). Обход через lowlevel-Server.
4. **`progress`** — `notifications/progress` с `_meta.progressToken`. Bidirectional flow, привязка notification к конкретному long-running tool call.
5. **`logging`** — `logging/setLevel` + `notifications/message`. Session-scoped лог-поток, не привязанный к request'у.

_TBD по каждой подсекции: живой wire через Inspector + ручной `echo | uv run python server.py` там, где нужен сырой поток (subscribe в обход FastMCP)._

## Топология

_TBD: diagram тот же, что в 05, но со стрелкой notifications от server к client отдельно подсвеченной._

## Содержимое папки

```
06-notifications/
├── pyproject.toml    # mcp, fastapi, uvicorn, httpx + что добавится под subscribe
├── rest_api.py       # копия из 05
├── server.py         # базируется на 05: tools + resources + progress-tool + subscribe-хендлеры
└── README.md         # этот файл
```

_TBD: переносим server.py из 05 как базу; добавляем (а) long-running tool с progress; (б) lowlevel-хендлеры subscribe/unsubscribe; (в) вызовы `send_resource_updated` из мутирующих tools._

## Установка и запуск

_TBD: как в 05 — два терминала, rest_api + Inspector._

## Шаг 1 — `list_changed` (каталог поменялся)

_TBD motivation: когда через tool появляется/уходит concrete resource. Для статического каталога 05 list_changed никогда не сработает — добавим tool `pin_task_as_resource(task_id)`, который регистрирует динамический concrete `tasks://pinned/{id}` через `mcp.add_resource()` и тут же триггерит `send_resource_list_changed()`. Параллельно: тот же механизм для tools/list_changed и prompts/list_changed._

_TBD wire: `{"jsonrpc": "2.0", "method": "notifications/resources/list_changed"}` — без id, без params. В Inspector → Server Notifications._

_TBD details: кто ответственен за повторный `resources/list` (клиент сам), почему нет `params` (ничего не говорим кроме самого факта), как это связано с capability `resources.listChanged: true`._

## Шаг 2 — `subscribe` + `updated` (конкретный URI обновился)

_TBD: `resources/subscribe` c `uri` — обычный request, возвращает `EmptyResult`. Дальше при каждом изменении — `notifications/resources/updated` с тем же `uri`. Клиент сам решает, перечитывать или нет (обычно перечитывает)._

_TBD code: in-memory список подписчиков, хуки в create/update/delete-tools для отправки `send_resource_updated`. В идеале — подписка на `tasks://all` + `tasks://stats` + на конкретный `tasks://id/{...}`._

_TBD wire: последовательность из пяти сообщений — subscribe (request→EmptyResult), затем create_task (tool call), одновременно notifications/resources/updated, затем клиент ре-читает resource через resources/read._

_TBD UI: Inspector → вкладка Subscriptions. Что там видно, какой интерактив._

## Шаг 3 — что сломано в FastMCP 1.27.0

_TBD: симметричный кейс к [03-errors/](../03-errors/). В [`lowlevel/server.py:211-213`](https://github.com/modelcontextprotocol/python-sdk/blob/v1.27.0/src/mcp/server/lowlevel/server.py#L211) `subscribe=False` **захардкожен** в `ResourcesCapability`, независимо от того, зарегистрирован ли `subscribe_resource` handler. Клиент в `initialize` видит `"subscribe": false` и по спеке **не должен** звать `resources/subscribe`._

_TBD: в main после PR #1951 исправлено — `subscribe="resources/subscribe" in self._request_handlers`. Та же природа, что issue [#2473](https://github.com/modelcontextprotocol/python-sdk/issues/2473): SDK декларирует capabilities не глядя на реальные регистрации._

_TBD: воспроизведение + обход. Три варианта: (а) спуститься в lowlevel `mcp._mcp_server` и регистрировать хендлеры там, одновременно форсируя capability через `notification_options`; (б) monkey-patch `get_capabilities` на инстансе; (в) ждать 1.28.x. Разобрать плюсы/минусы, в главе используем (а)._

## Шаг 4 — `progress` (долгий tool + токен)

_TBD (это был исходный сценарий 06): long-running tool, который шлёт `notifications/progress` пока работает. Клиент отправляет request с `_meta.progressToken`, сервер шлёт нотификации с тем же токеном пока занят, и финальный response в конце._

_TBD code: tool `slow_import(n: int)` или что-то, что имитирует долгую обработку, с `await ctx.report_progress(progress=i, total=n)` внутри цикла._

_TBD wire: interleaved — tools/call request (с `_meta.progressToken`), серия `notifications/progress` с тем же токеном, финальный response на оригинальный request._

_TBD details: чем progress отличается от logging — привязкой к request'у через token vs session-scope, и как их отличают клиенты._

## Шаг 5 — `logging` (session-scoped лог-поток)

_TBD: capability `logging` в initialize, `logging/setLevel` от клиента, `notifications/message` от сервера. Уровни `debug` / `info` / `notice` / `warning` / `error` / `critical` / `alert` / `emergency`._

_TBD code: в server.py добавить вызовы `await ctx.log_info(...)` / `await ctx.log_warning(...)` из разных мест — при старте, при tool-call, при ошибке внутри long-running tool._

_TBD wire: `logging/setLevel` запрос-ответ, затем поток `notifications/message` в интерливе с прочими сообщениями. Inspector → вкладка Logs._

_TBD: чем logging отличается от progress — не привязан к request'у, принадлежит всей сессии. Как host'ы обычно отрисовывают: отдельной debug-панелью, не в чате._

## Сводная: четыре типа уведомлений

_TBD: таблица — тип, wire-форма, привязка (к чему), capability, типичный UX._

## Что потрогать

_TBD 4-5 упражнений. Предварительно:_

1. _Сделать subscribe на `tasks://stats` и посмотреть, как он обновляется при mutations._
2. _Отписаться через `resources/unsubscribe` и проверить, что `updated` больше не приходит._
3. _Вызвать progress-tool одновременно из двух клиентских сессий — убедиться, что токены не пересекаются._
4. _Переключить log-уровень на `error` и посмотреть, как фильтруется поток._
5. _Запустить tool с progress без передачи `_meta.progressToken` — посмотреть, что делает сервер (по спеке не обязан слать прогресс, если токена нет)._

## Что разобрали

_TBD итоговые буллеты после наполнения._

- _Четыре вида уведомлений, одна механика JSON-RPC._
- _Subscribe vs list_changed — область действия: конкретный URI vs каталог._
- _Progress привязан к request'у (через token), logging — к сессии. Разная механика «куда клиент это рисует»._
- _FastMCP 1.27.0 не объявляет `subscribe: true` — параллель к багу из [03-errors/](../03-errors/)._
- _Bidirectional flow — переход от синхронного «request→response» к «клиент и сервер шлют друг другу что угодно в любой момент». Следующая глава ([`07-cancellation/`](../07-cancellation/)) продолжит тему с обратной стороны — клиент сам шлёт notification серверу, чтобы отменить долгий tool._

Дальше — [`07-cancellation/`](../07-cancellation/): отмена долгих tool call'ов через `notifications/cancelled`.
