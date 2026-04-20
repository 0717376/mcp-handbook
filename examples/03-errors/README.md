# 03 — Ошибки: `isError: true` vs JSON-RPC error

В MCP два канала ошибок, не один. Цель главы — увидеть оба живьём, понять границу и сверить её с актуальной спекой 2025-11-25 и с реальным поведением Python-SDK (FastMCP 1.27.0 — то, что у тебя установилось в главе 02).

Нового кода **не пишем**: ошибки получаются сами собой на сервере из [`02-rest-wrapper`](../02-rest-wrapper/). Это важная мысль: в MCP правильная обработка ошибок — это в основном просто нормальный Python-код.

## Два канала — и зачем так

Первый канал — **JSON-RPC error** (`-32700`, `-32601`, `-32602`, ...). Это транспортная ошибка: «запрос не дошёл», «метод неизвестен», «структура сломана». Ответ приходит в поле `error`, без `result`.

```json
{"jsonrpc":"2.0","id":2,"error":{"code":-32601,"message":"Method not found"}}
```

Второй канал — **`isError: true`** внутри обычного успешного `result`. Это бизнес-ошибка: тул позвали корректно, но в процессе что-то не сошлось (задача не найдена, токен истёк, внешний API отдал 500).

```json
{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"Task not found"}],"isError":true}}
```

Зачем разделены? Цитата из комментария к полю `CallToolResult.isError` в `schema.ts` 2025-11-25:

> Any errors that originate from the tool SHOULD be reported inside the result object, with `isError` set to true, **not** as an MCP protocol-level error response. Otherwise, the LLM would not be able to see that an error occurred and self-correct.

Коротко: `-32xxx` идёт host'у, LLM об этом обычно **не узнаёт**. `isError: true` идёт **к LLM** как часть разговора — и модель может попробовать снова, уточнить аргументы, переключиться на другой тул.

## Запуск

Из папки главы 02:

```bash
cd ../02-rest-wrapper
uv sync

# терминал 1 — REST-downstream
uv run python rest_api.py

# терминал 2 — MCP-сервер под Inspector
npx @modelcontextprotocol/inspector uv run python server.py
```

Дальше — работаем с Inspector, а пару раз отправим JSON-RPC-сообщения вручную прямо на stdin сервера (как это выглядит — в сценарии 3).

## Сценарий 1 — бизнес-ошибка (`isError: true`)

В Inspector → **Tools** → `get_task` → в `task_id` введи `does-not-exist` → **Run Tool**.

Что видно:

1. В левой `History` вызов отмечен как **успешный** — никакого красного «Call failed», никакого timeout.
2. В правой карточке тула — плашка **«Tool Error»** с красной каймой. Это Inspector посмотрел на `result.isError` и нарисовал бейдж.
3. В `content` — текст ошибки, что-то вроде `Error executing tool get_task: Client error '404 Not Found' for url 'http://127.0.0.1:8765/tasks/does-not-exist'`.
4. **`structuredContent` отсутствует**. Логично: `outputSchema` объявлен как `Task`, а при ошибке ни одной валидной `Task` вернуть нельзя — FastMCP не кладёт structured-часть вовсе.

JSON в `History → Response`:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Error executing tool get_task: Client error '404 Not Found' for url 'http://127.0.0.1:8765/tasks/does-not-exist'\nFor more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404"
      }
    ],
    "isError": true
  }
}
```

Ключевое:

- На верхнем уровне — **`result`**, не `error`. С точки зрения JSON-RPC вызов **успешен**.
- Внутри `result` — **`isError: true`**. Это флаг бизнес-уровня.
- Текст — исключение `httpx.HTTPStatusError` (от `raise_for_status()`), обёрнутое FastMCP: префикс `Error executing tool get_task:` добавляет [`fastmcp/tools/base.py:117`](https://github.com/modelcontextprotocol/python-sdk/blob/v1.27.0/src/mcp/server/fastmcp/tools/base.py#L117) (`raise ToolError(f"Error executing tool {self.name}: {e}") from e`), после чего `lowlevel/server.py` ловит это и упаковывает в `isError: true`. **Мы не писали ни одного `try/except`**. Как это получилось — ниже.

## Сценарий 2 — как FastMCP ловит любое исключение

В коде `server.py` тула `get_task`:

```python
@mcp.tool(...)
def get_task(task_id: str) -> Task:
    """Fetch a single task."""
    r = http.get(f"/tasks/{task_id}")
    r.raise_for_status()         # на 404 → httpx.HTTPStatusError
    return Task(**r.json())
```

Ни одного `try/except`. Откуда тогда аккуратный `isError: true` с нужным текстом?

Работа делится на два слоя python-sdk:

1. **`fastmcp/tools/base.py:117`** — `Tool.run()` оборачивает любое исключение из тела тула в `ToolError` с префиксом:
   ```python
   except Exception as e:
       raise ToolError(f"Error executing tool {self.name}: {e}") from e
   ```
2. **`lowlevel/server.py:521-584`** — хендлер `tools/call` ловит это (и любое другое исключение — из jsonschema-валидации, из `ToolError("Unknown tool: ...")`) и превращает в `CallToolResult`:
   ```python
   try:
       # 1. валидация аргументов по inputSchema (jsonschema)
       # 2. вызов нашей функции → get_task(...) через Tool.run
       results = await func(tool_name, arguments)
       return CallToolResult(content=..., isError=False)
   except Exception as e:
       return CallToolResult(
           content=[TextContent(type="text", text=str(e))],
           isError=True,
       )
   ```

Любое исключение — из тела тула, из предвалидации аргументов, из `ToolError`ов SDK — попадает в `CallToolResult(isError=True)` с текстом. SDK никогда не роняет вызов.

Проверь сам: в `server.py` в `update_task` первой строкой впиши:

```python
raise ValueError("simulated boom")
```

В Inspector нажми **Disconnect** → **Connect**, вызови `update_task(task_id="x", title="y")`. В `content` придёт ровно `simulated boom`, `isError: true`. Без единой строчки обвязки.

Практический вывод — **в тулах не нужно заворачивать всё в `try/except` ради корректных MCP-ошибок**. SDK это делает сам. `try/except` стоит писать только когда хочется:

- **дружелюбнее текст** для модели — без типа исключения и HTTP-тейла;
- **специфичную реакцию** — сжать ошибку в короткую подсказку типа «попробуй `list_tasks`, такого id нет».

Как это выглядит, если хочется для 404 получить чистый текст `Task <id> not found`:

```python
from httpx import HTTPStatusError

@mcp.tool(...)
def get_task(task_id: str) -> Task:
    """Fetch a single task."""
    r = http.get(f"/tasks/{task_id}")
    try:
        r.raise_for_status()
    except HTTPStatusError as e:
        if e.response.status_code == 404:
            raise ValueError(f"Task {task_id} not found")
        raise
    return Task(**r.json())
```

Под капотом будет всё тот же `isError: true`, но текст — `Task does-not-exist not found`, чище для LLM. Это эстетика, не обязательность.

## Сценарий 3 — протокольная ошибка (`-32xxx`)

Теперь в другую сторону: хочется увидеть живой JSON-RPC error. Inspector для этого плохо подходит — в UI он показывает только зарегистрированные тулы и сам валидирует аргументы до отправки. Поэтому идем в терминал.

`rest_api.py` в терминале 1 можно оставить, но он не нужен: мы бьём напрямую в MCP-сервер, без REST. В **третьем** терминале, из папки `02-rest-wrapper/`:

```bash
(
  echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"x","version":"0"}},"id":1}'
  echo '{"jsonrpc":"2.0","method":"notifications/initialized"}'
  echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"do_magic","arguments":{}},"id":2}'
) | uv run python server.py
```

Инкапсулированный handshake + один `tools/call` с несуществующим `name`.

По **букве спеки** 2025-11-25 (`tools.mdx` → Error Handling → канонический пример) ответ на третье сообщение должен быть:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "error": {
    "code": -32602,
    "message": "Unknown tool: do_magic"
  }
}
```

`error` вместо `result`. Код `-32602` (Invalid params). `id` echo-нулся из запроса. Ни `content`, ни `isError` — классический JSON-RPC error.

**А по факту в выводе ты увидишь не это.** FastMCP 1.27.0 на unknown tool всё равно отвечает `result` с `isError: true`:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [{"type": "text", "text": "Unknown tool: do_magic"}],
    "isError": true
  }
}
```

Почему так — видно в `mcp/server/lowlevel/server.py:521-584`: любое исключение, включая `ToolError("Unknown tool: ...")` и `jsonschema.ValidationError`, ловится одним `except Exception` и заворачивается в `isError: true`. Это осознанное решение python-sdk: «лучше дадим модели шанс самокорректироваться, чем спрячем ошибку в JSON-RPC». Спека это явно не запрещает — в `schema.ts` комментарий говорит _«errors in finding the tool … should be reported as an MCP error response»_, без конкретного кода, а пример в `tools.mdx` показывает `-32602`, но не делает его нормативным.

Итог: **`-32602` на unknown tool в FastMCP ты не увидишь**. Другие SDK — особенно TypeScript SDK — возвращают именно `-32602`, по канону спеки.

Попробуем «неизвестный метод» — по букве спеки должно быть `-32601 Method not found`. Подменим в запросе `tools/call` на `foo/bar` и прогоним тот же однострочник.

Фактически на stdout:

```json
{"jsonrpc":"2.0","id":2,"error":{"code":-32602,"message":"Invalid request parameters","data":""}}
```

В stderr — длинный Pydantic-дамп (20+ строк). Причина: SDK валидирует входящее сообщение против списка из ~28 известных типов запроса и падает раньше диспетчера, где лежит `-32601`. Так же отвечают `tools/call` без `name` и `initialize` без `protocolVersion` — всё это SDK превращает в один общий `-32602 "Invalid request parameters"`.

А вот чего **не** случается:

- **Битый JSON** (`{broken`) — JSON-RPC error на проводе не идёт (у невалидного сообщения нет `id`, отвечать некому). Сервер логирует warning и шлёт `notifications/message` с `level: "error"`, сам продолжает работать.
- **`initialize` с чем угодно в `protocolVersion`** (`"1999-01-01"`, `"garbage"`) — сервер просто возвращает свою версию в успешном `result`. Никакой проверки формата.

Итог: **в живой FastMCP-сессии 1.27.0 ты увидишь почти всегда только `-32602`** (на всё, что не пролезло Pydantic-валидацию на входе). `-32601` и `-32700` в коде SDK есть, но до них не доходит.

## Граница: куда что относить

Сводная таблица — как должна выглядеть граница по спеке, и что **фактически** делает FastMCP 1.27.0:

| Ситуация                                                         | Спека 2025-11-25                    | FastMCP 1.27.0 фактически                                 |
|------------------------------------------------------------------|-------------------------------------|-----------------------------------------------------------|
| Python-исключение в теле тула                                    | `isError: true`                     | `isError: true` с префиксом `Error executing tool …:`      |
| Бизнес-ошибка (`raise ValueError`, 404 от downstream)            | `isError: true`                     | `isError: true` ✓                                         |
| Аргумент не прошёл `inputSchema` (`title: 42` вместо string)     | `isError: true` (SEP-1303)          | `isError: true` ✓                                         |
| Неизвестное имя тула (`name: "do_magic"`)                        | `-32602` (пример в спеке)           | `isError: true` (SDK-прагматика)                          |
| `tools/call` без `name` (сломан CallToolRequest)                 | `-32602`                            | `-32602 "Invalid request parameters"` + pydantic-дамп     |
| Неизвестный метод JSON-RPC (`foo/bar`)                           | `-32601`                            | **`-32602`** (pydantic ловит раньше диспетчера)           |
| Неподдерживаемый `protocolVersion` в `initialize`                | `-32602` + supportedVersions        | **Тихий downgrade** — сервер возвращает свою версию       |
| `initialize` без `protocolVersion`                               | `-32602`                            | `-32602` ✓                                                |
| Битый JSON                                                       | `-32700 Parse error`                | **Нет response**; `notifications/message` `level=error`   |

Эвристика: **в FastMCP 1.27.0 ты увидишь по сути только два кода — `-32602` и ничего**. Всё, что спека ожидает как `-32601`, `-32700`, handshake-версии с `-32602+supportedVersions` — SDK либо превращает в `-32602 "Invalid request parameters"` (через Pydantic-валидацию на входе), либо в `isError: true` (через tools-хэндлер), либо в server→client notification `level=error` (битый JSON). Это осознанный инженерный выбор SDK: любую ошибку, которую модель могла бы прочитать, отдавать как `isError: true`; всё, что сломало конверт — как один общий `-32602`.

## Что видит LLM

Связка с главой 01 — как это попадает в модель:

- **`isError: true`** → host передаёт `content[0].text` как `tool_result` в Anthropic Messages API или как сообщение с `role: "tool"` в OpenAI chat.completions. Модель читает текст **как часть разговора** и чаще всего говорит что-то вроде «id не нашёлся, попробую `list_tasks`». В этом вся соль `isError: true`: LLM работает с ошибкой как с любым другим ответом.

- **JSON-RPC `-32xxx`** → host обычно **не** передаёт модели. Спека, `tools.mdx`: _«Clients MAY provide protocol errors to language models, though these are less likely to result in successful recovery»_. Типовое поведение host'а: залогировать, показать плашку пользователю, иногда коротко сообщить модели «сорвался вызов, попробуй что-то ещё». Детали ошибки до LLM не доходят.

Простой практический вывод: **хочешь, чтобы модель адекватно реагировала на ошибку — возвращай её через `isError: true`**. Если ошибка про сам протокол (handshake, неизвестный метод) — `-32xxx`, но про это SDK уже заботится автоматически.

## Что потрогать

1. **Сорвать downstream.** Останови `rest_api.py` в терминале 1 (Ctrl-C), но оставь MCP-сервер. В Inspector вызови `list_tasks`. Увидишь `isError: true` с `httpx.ConnectError`. Ни строчки нового кода — просто нормальный `httpx` поднялся и упал, FastMCP поймал.

2. **Ручное исключение.** Впиши `raise ValueError("simulated boom")` первой строкой в `update_task`. **Disconnect** → **Connect** в Inspector. Вызови `update_task`. Текст `simulated boom` придёт модели как `isError: true`. Никакого дополнительного кода.

3. **Protocol error руками.** Прогони однострочник с `name: "do_magic"` — FastMCP возвращает `isError: true`. Потом — с `{"method": "foo/bar"}` — увидишь `-32602 "Invalid request parameters"` и в stderr длинный Pydantic-дамп на 28 строк. Потом — с `{"method": "tools/call", "params": {}}` (без `name` в params) — тот же `-32602`, чуть короче дамп. Разница: unknown tool долетает до tools-хэндлера (там `isError`), а `foo/bar` и `tools/call` без `name` падают на Pydantic-валидации union'а `ClientRequest` раньше диспетчера (там `-32602`).

4. **Сломанный JSON.** Пошли в stdin `{broken` без закрывающей скобки. На stdout **не будет** JSON-RPC error — SDK ловит исключение внутри себя и вместо ответа шлёт **server→client notification** `notifications/message` с `level: "error"` и `data: "Internal Server Error"`. Ответить нечему — у битого сообщения нет `id`. Сервер при этом остаётся жив и ждёт следующих корректных сообщений. Это чуть ли не единственный способ увидеть server→client notification вне полноценного Inspector-флоу.

5. **Убрать `raise_for_status()`.** Выкинь его из `get_task`. REST 404 больше не превращается в исключение, `r.json()` вернёт `{"detail": "Not Found"}`, попытка собрать `Task(**...)` упадёт на Pydantic-валидации — **всё равно** придёт `isError: true`, но с текстом про отсутствующие поля, а не про 404. Хорошая иллюстрация, почему `raise_for_status()` — базовая гигиена.

## Что разобрали

- **Два канала.** JSON-RPC `-32xxx` — для host'а, сломан конверт запроса. `isError: true` внутри `result` — для LLM, сломалась бизнес-логика. Разделение намеренное: модель должна видеть ошибку как часть разговора и самокорректироваться.

- **FastMCP оборачивает любое исключение автоматически.** Не нужен ручной `try/except` в тулах ради корректных MCP-ошибок. Любое `raise` → `isError: true` с текстом. `try/except` пишется только ради формулировки, не ради корректности.

- **SDK идёт дальше спеки.** Python SDK 1.27.0 отвечает `isError: true` даже на unknown tool и `inputSchema`-валидацию, хотя спека показывает пример `-32602`. Осознанное решение: дать модели максимум шансов самокорректироваться. Другие SDK (TypeScript) ведут себя иначе.

- **Настоящий `-32xxx` в FastMCP ты увидишь редко и почти всегда только `-32602`.** Всё, что нарушает конверт JSON-RPC (unknown method, поломанный `CallToolRequest`, отсутствие required-полей в `initialize`), Pydantic-валидация на входе превращает в один общий `-32602 "Invalid request parameters"` — и в stderr сыплет длинным дампом. `-32601` и `-32700` в коде SDK есть, но в живой сессии не достижимы. Unsupported `protocolVersion` — тоже не ошибка, а тихий downgrade.


Дальше — [`04-resources/`](../04-resources/): первая смена примитива. Resources вместо tools, подписки, `notifications/resources/updated`.
