# 04 — Prompts

Prompts — это **параметризованные шаблоны, которые пользователь явно выбирает из UI** (обычно slash-команды). Если tools — это «модель сама решает, когда позвать», то prompts — противоположный полюс: инициатива **всегда у пользователя**. Цитата из [спеки 2025-11-25](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/server/prompts.mdx):

> Prompts are designed to be **user-controlled**, meaning they are exposed from servers to clients with the intention of the user being able to explicitly select them for use.

Из этой разницы в инициаторе — всё остальное: плоские строковые аргументы (не JSON Schema), ответ в виде `messages[]` (не `content` + `structuredContent`), отсутствие канала `isError`. По ходу главы разберём каждое из этих отличий на живом wire.

## Содержимое папки

```
04-prompts/
├── pyproject.toml    # одна зависимость: mcp
├── server.py         # 3 prompt'а: простой, multi-turn, с optional-аргументом
└── README.md         # этот файл
```

`demo.py` здесь нет: handshake и lifecycle уже разобраны в [`01-hello/`](../01-hello/), а для ощущения UX лучше взять Inspector. Wire там, где он интересен, снят через ручные `echo | python server.py` — как в [`03-errors/`](../03-errors/).

## Установка

```bash
uv sync
```

## server.py — три prompt'а

```python
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts.base import AssistantMessage, Message, UserMessage

mcp = FastMCP("prompts")


@mcp.prompt(title="Review code")
def review_code(code: str) -> str:
    """Провести подробное ревью фрагмента кода: баги, неидиоматичные места, конкретные правки."""
    return (
        "Посмотри код ниже. Укажи баги, неидиоматичные места и граничные случаи. "
        "Предлагай конкретные правки, а не общие рассуждения.\n\n"
        f"```python\n{code}\n```"
    )


@mcp.prompt(title="Debug an error")
def debug_error(error: str) -> list[Message]:
    """Заготовка разговора про разбор ошибки: user кидает стектрейс, assistant задаёт уточнения."""
    return [
        UserMessage("Я ловлю такую ошибку:"),
        UserMessage(error),
        AssistantMessage(
            "Давай сузим. Какой командой ты это воспроизвёл, "
            "и раньше этот код работал? Были ли недавние обновления зависимостей?"
        ),
    ]


@mcp.prompt(title="Commit message")
def commit_message(diff: str, tone: str = "нейтральный") -> str:
    """Составить commit-сообщение для diff.

    `tone` — опциональный: "нейтральный" (по умолчанию), "сухой" или "шутливый".
    """
    ...
```

Три намеренно разных случая:

- **`review_code`** возвращает `str`. FastMCP обернёт его в **один** `UserMessage` с `TextContent`. Самый частый паттерн.
- **`debug_error`** возвращает `list[Message]` — готовый «заготовленный разговор» user → user → assistant. Зачем нужна роль `assistant` в prompt'е — увидим живьём в Inspector и разберём сразу после.
- **`commit_message`** — первый с **опциональным** аргументом: `tone` имеет default. В `PromptArgument` это превращается в `required: false`.

Из type hints FastMCP сам вытаскивает имена аргументов и флаг `required`. **JSON Schema не генерируется** — в отличие от tools, у prompt-аргументов её просто нет в спеке. Только имя, описание и опциональный `required`.

## Пробуем в Inspector

MCP Inspector — визуальный дебаггер, запускается прямо поверх нашего сервера:

```bash
npx @modelcontextprotocol/inspector uv run python server.py
```

Отдельно запускать `server.py` не нужно — Inspector сам спавнит его как child-процесс по stdio (ровно как `demo.py` в [`01-hello/`](../01-hello/)). Всё, что идёт после `inspector`, — это команда, которой Inspector поднимет сервер.

Откроется вкладка в браузере. В левой панели жми **Connect** — сервер поднимется и пройдёт handshake. В шапке — таб **Prompts**, переходи туда и жми **List Prompts**.

В каталоге видно три prompt'а: `title` жирным, `description` серым. Рядом с каждым обязательным аргументом — звёздочка. Это **ровно то, что увидит пользователь Claude Desktop или Cursor** в выпадающем списке slash-команд, когда наберёт `/`. Ниже — пройдёмся по каждому prompt'у и посмотрим, во что он разворачивается.

### Шаг 1 — `review_code` (одно сообщение из строки)

Кликни на `review_code`. Справа форма с одним полем `code` (required). Вставь туда любой фрагмент:

```python
def f(x):
    return x+1
```

Жми **Get Prompt**. В нижней панели Inspector — preview сгенерированных сообщений: **одно**, роль **user**, внутри — наш русскоязычный текст запроса на ревью с кодом, обёрнутым в markdown-блок.

Что сделал FastMCP: Python-функция вернула `str`, SDK автоматически завернул его в `UserMessage` с `TextContent`. Самый частый паттерн — шаблон «одного обращения к модели».

### Шаг 2 — `debug_error` (multi-turn с ролью assistant)

Вернись к каталогу, кликни `debug_error`. Поле `error` — обязательное. Вставь что-нибудь:

```
ModuleNotFoundError: No module named 'mcp'
```

**Get Prompt** — preview уже **три** сообщения: два user (intro + текст ошибки) и **последнее — assistant** с уточняющим вопросом. В Inspector они визуально отделены цветом/отступом в зависимости от роли.

Это уже не «шаблон одного запроса», а целая заготовка разговора. Про то, зачем в prompt'е бывает `assistant` и как это используется — сразу после Inspector-прогона.

### Шаг 3 — `commit_message` (optional-аргумент)

Третий prompt. В форме два поля: `diff` (со звёздочкой, обязательное) и `tone` (**без** звёздочки — optional). Вставь любой diff в `diff`, `tone` оставь **пустым**:

```diff
-print("hello")
+print("world")
```

**Get Prompt** — в preview появится одно user-сообщение с тоном `нейтральный`. Default из Python-сигнатуры (`tone: str = "нейтральный"`) подставился **на стороне сервера**, когда хост не прислал значение.

Теперь впиши `шутливый` в `tone` и нажми **Get Prompt** ещё раз — увидишь, что текст обновился. Ключевой wire-момент: `tone` в запросе будет **строкой** `"шутливый"`, а не enum и не bool. В `PromptArgument` в принципе нет типов — только имя, описание и `required`. Почему так — дальше в секции про wire.

## Зачем prompt, возвращающий `assistant`-сообщение

Вернёмся к тому, что увидели в шаге 2. Роль `assistant` внутри prompt'а **не значит «модель уже ответила»**. Это — **заготовка разговора**: набор реплик, которые host подставит модели как уже случившиеся, прежде чем модель начнёт писать свой ответ. В `debug_error` три сообщения вместе означают: «представь, что пользователь уже прислал ошибку, а ты уже ответил уточняющим вопросом — теперь пусть пользователь ответит на него». Это классический few-shot seed: prompt задаёт и стиль ответа, и первый ход дальнейшего разговора.

Живая связка «prompt как seed для sampling» появится в [`08-sampling/`](../08-sampling/) — там сервер сам прогоняет эти сообщения через LLM клиента. Здесь мы видим только **структуру** заготовки; как по ней идёт реальная генерация — в 08.

В MCP ролей всего две: `user` и `assistant`. Ни `system`, ни `tool` в `PromptMessage.role` не встречается — системные инструкции закладывают либо первым `UserMessage`, либо через поле `instructions` сервера в `initialize`.

## Что там нового под капотом

Всё, что мы пощупали в Inspector, в wire — это две пары запрос/ответ: один раз `prompts/list` (каталог) и по одному `prompts/get` на каждый клик. Смотрим те же сообщения, что Inspector вытащил в UI, в сыром JSON — через ручной `echo | uv run python server.py`, как в [`03-errors/`](../03-errors/).

### `prompts/list`

Запрос прост — метода и id достаточно:

```json
>>> {"jsonrpc":"2.0","method":"prompts/list","id":2}
```

Ответ — каталог (показан с переносами для читаемости; по факту прилетает одной строкой):

```json
<<< {
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "prompts": [
      {
        "name": "review_code",
        "title": "Review code",
        "description": "Провести подробное ревью фрагмента кода: баги, неидиоматичные места, конкретные правки.",
        "arguments": [{"name": "code", "required": true}]
      },
      {
        "name": "debug_error",
        "title": "Debug an error",
        "description": "Заготовка разговора про разбор ошибки: user кидает стектрейс, assistant задаёт уточнения.",
        "arguments": [{"name": "error", "required": true}]
      },
      {
        "name": "commit_message",
        "title": "Commit message",
        "description": "Составить commit-сообщение для diff.\n\n`tone` — опциональный: ...",
        "arguments": [
          {"name": "diff", "required": true},
          {"name": "tone", "required": false}
        ]
      }
    ]
  }
}
```

На что смотреть:

- **`arguments` — плоский список** объектов `{name, description?, title?, required?}`. Ни `type`, ни `properties`, ни JSON Schema здесь нет — это фундаментальное решение спеки. Prompts задумывались как слоты для slash-команд, куда пользователь печатает текст; строковой формы и `required`-флага хватает, а полноценная схема была бы излишеством.
- **`required: false` у `tone`** — default в Python-сигнатуре (`tone: str = "нейтральный"`) стал флагом в каталоге.
- Как и у tools, `prompts/list` — **пагинируемый** метод: если каталог большой, в response приходит `nextCursor`, а повторный запрос с `{"cursor": "..."}` тянет следующую страницу. У нас три штуки — умещается в одну.

### `prompts/get`

Сам вызов — `name` + словарь строковых `arguments`:

```json
>>> {
  "jsonrpc": "2.0",
  "method": "prompts/get",
  "params": {
    "name": "debug_error",
    "arguments": {"error": "ModuleNotFoundError: No module named 'mcp'"}
  },
  "id": 2
}
```

**`arguments` — `{string: string}`**, а не произвольный объект. Если prompt-функция в Python принимает `int` или `bool`, host всё равно передаёт всё строкой; приведение делает FastMCP уже на своей стороне через `validate_call`.

Ответ:

```json
<<< {
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "description": "Заготовка разговора про разбор ошибки: user кидает стектрейс, assistant задаёт уточнения.",
    "messages": [
      {"role": "user",      "content": {"type": "text", "text": "Я ловлю такую ошибку:"}},
      {"role": "user",      "content": {"type": "text", "text": "ModuleNotFoundError: No module named 'mcp'"}},
      {"role": "assistant", "content": {"type": "text", "text": "Давай сузим. Какой командой ты это воспроизвёл, и раньше этот код работал? Были ли недавние обновления зависимостей?"}}
    ]
  }
}
```

- `messages[]` — готовый разговор, ровно как в LLM-API (`role` + `content`).
- `content` — **один блок**, не массив. Это отличие от `tools/call`, где `content` — массив блоков. Внутри может быть `text`, `image`, `audio`, `resource_link` или инлайн-resource (пример с ресурсом — в [`05-resources/`](../05-resources/)).
- `description` — **переопределение** на уровне конкретного вызова: сервер может подставить что-то более специфичное, чем общее описание из `prompts/list`. У нас FastMCP просто продублировал docstring.
- **Поля `isError` здесь нет и не бывает**. `GetPromptResult` в схеме его не содержит — у prompts нет «domain-level ошибки» как у tools. Подробнее — в секции [Ошибки](#ошибки-prompts).

Для сравнения, простой `review_code(code="x = 1")` вернёт одно сообщение:

```json
"messages": [
  {"role": "user", "content": {"type": "text", "text": "Посмотри код ниже. Укажи баги, ...\n\n```python\nx = 1\n```"}}
]
```

Всё, что вернула Python-функция строкой, FastMCP завернул в один `UserMessage` с `TextContent`.

### Tools vs Prompts — сводная таблица

| | Tools | Prompts |
|---|---|---|
| Инициатор вызова | LLM (model-controlled) | пользователь (user-controlled) |
| Аргументы | JSON Schema (`inputSchema`) | плоский `PromptArgument[]`: `name`, `description?`, `required?` |
| Передача аргументов в вызове | `arguments: {…}` произвольной структуры | `arguments: {string: string}` |
| Ответ | `content[]` + `structuredContent` + `isError` | `messages[]` (каждое — `role` + `content`-блок) + `description?` |
| Ошибки исполнения | `isError: true` внутри `result` (domain); `-32xxx` (protocol) | **только `-32xxx`** — канала `isError` у prompts нет |
| Роли в ответе | — | `user` или `assistant`, других нет |
| `listChanged` capability | есть | есть |
| `subscribe` capability | — | — (есть только у resources) |

## Resource-блоки в prompt-content

В `content` prompt-сообщения спека разрешает не только `text`/`image`/`audio`, но и **ресурсы** — либо как ссылку (`resource_link`), либо как инлайн-тело (`resource` с `text`/`blob`). Это позволяет отдать модели документ прямо в заготовке разговора, не заставляя её его читать через отдельный tool. Живой пример и разбор обоих форм — в [`05-resources/`](../05-resources/), там появляются и сами resources как примитив.

## Подключаем к VS Code + GitHub Copilot

Inspector — дебажный инструмент. Чтобы пощупать prompts как **реальные slash-команды**, подключим сервер к живому host'у. Берём **VS Code с GitHub Copilot Chat** — по [официальному списку](https://modelcontextprotocol.io/clients) у него самое полное покрытие MCP-фич.

**Настройка** 
- Открой Command Palette (`⇧⌘P` / `Ctrl+Shift+P`) → **`MCP: Add Server...`** → в выпадашке выбери **`Command (stdio)`**.
- Введи команду (подставь свой путь до `04-prompts`):

  ```
  uv run --directory /path/to/mcp/examples/04-prompts python server.py
  ```

После `Enter` VS Code дополнительно спросит **имя** сервера (ставь `prompts-demo` — под ним будут построены slash-команды) и **scope**: **Workspace** (конфиг ляжет в `.vscode/mcp.json`) или **Global** (в user-профиль, доступно из любого воркспейса).

VS Code сам допишет JSON и попытается поднять сервер. Проверить статус — `MCP: List Servers` в Command Palette; там же кнопка логов stderr, если что-то пойдёт не так.

Дальше открывай **Copilot Chat** (`Ctrl/Cmd+Alt+I`), набирай `/` — в выпадашке появятся команды формата **`/prompts-demo.review_code`**, **`/prompts-demo.debug_error`**, **`/prompts-demo.commit_message`**. Копилот показывает `title` и `description` ровно так же, как Inspector в шаге с каталогом.

## Ошибки prompts

В [главе 03](../03-errors/) мы разобрали два канала ошибок у tools: `isError: true` для бизнес-логики и `-32xxx` для протокола. **У prompts второго этажа нет**: поля `isError` в `GetPromptResult` не существует. По спеке любая ошибка `prompts/get` — это JSON-RPC error с кодом:

- `-32602 InvalidParams` — неизвестное имя prompt'а или не хватает обязательных аргументов.
- `-32603 InternalError` — всё остальное.

Проверим, что делает Python SDK 1.27.0. Три кейса подряд, вывод — это реальный stdout сервера, `uv run python server.py` с ручным stdin.

**Неизвестный prompt:**

```bash
echo '... prompts/get name="does_not_exist" ...' | uv run python server.py
```

```json
{"jsonrpc":"2.0","id":2,"error":{"code":0,"message":"Unknown prompt: does_not_exist"}}
```

**Отсутствует обязательный аргумент:**

```bash
echo '... prompts/get name="review_code" arguments={} ...' | uv run python server.py
```

```json
{"jsonrpc":"2.0","id":2,"error":{"code":0,"message":"Missing required arguments: {'code'}"}}
```

**Исключение внутри тела prompt'а** (добавь `raise ValueError("boom")` первой строкой `review_code`, вызови его):

```json
{"jsonrpc":"2.0","id":2,"error":{"code":0,"message":"Error rendering prompt review_code: boom"}}
```


## Что потрогать

1. **Вернуть dict вместо Message.** В `review_code` замени return на `{"role": "assistant", "content": "уже отревьюил"}`. FastMCP провалидирует через `UserMessage | AssistantMessage` и соберёт корректный `messages[]` с ролью assistant — видно будет в `prompts/get`.
2. **Добавить optional-аргумент с default-объектом.** Впиши `style: str = "pep8"` в `review_code`. В `prompts/list` появится новый `PromptArgument` с `required: false`; в `prompts/get` его можно и не передавать.
3. **Словить `code: 0` на исключении.** Поставь первой строкой `review_code` `raise RuntimeError("sim boom")`, вызови prompt. Увидишь `error.code: 0`, `message: "Error rendering prompt review_code: sim boom"` — всё оборачивается одинаково, ни `-32603`, ни `isError`.
4. **Проверить, что роль `system` не пролезет.** Верни `{"role": "system", "content": "..."}` из любого prompt'а. Pydantic провалит валидацию `UserMessage | AssistantMessage`, и получишь всё тот же `code: 0` с pydantic-дампом в `message` — подтверждение, что ролей в MCP только две.

## Что разобрали

- **Prompts user-controlled, tools model-controlled.** Всё остальное — следствие: плоские строковые аргументы, `messages[]`-ответ, отсутствие domain-канала ошибок.
- **`PromptArgument` — не JSON Schema.** Четыре опциональных поля и всё. Historically: задумано под slash-команды, где пользователь печатает строку; JSON Schema здесь был бы избыточной сложностью.
- **`messages[]` с `role` ∈ {user, assistant}**. Роли `system`/`tool` в MCP-prompts не бывает: системные инструкции кладут первым user-сообщением или через `instructions` сервера в `initialize`. Возврат `assistant`-сообщения — способ заготовить разговор для sampling, подробнее в [`08-sampling/`](../08-sampling/).
- **`isError` у prompts нет.** В отличие от tools, домен-уровня ошибок тут нет — только JSON-RPC errors. По спеке `-32602`/`-32603`, в FastMCP 1.27.0 всё сыпется одним `code: 0`. Это расхождение SDK со спекой, симметричное тому, что в [главе 03](../03-errors/).
- **Shortcuts FastMCP:** вернул `str` → один `UserMessage`; `list[Message]` → как есть; `dict` → валидируется через union `UserMessage | AssistantMessage`. Generator'ы не поддерживаются.
- **UX — slash-команды** в Claude Desktop, Cursor, Inspector. Но спека это не нормирует: host волен показывать prompts как угодно.
- **Completion для аргументов** — отдельный механизм спеки (`completion/complete`), не связанный с `@mcp.prompt()` автоматически. В этой главе не раскрываем.

Дальше — [`05-resources/`](../05-resources/): тот же примитив «готовый контент для модели», но с URI, подпиской на изменения и живым примером resource-контента в `PromptMessage`.
