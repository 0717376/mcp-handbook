"""MCP-сервер над тем же сервисом задач, что в 02. Расширяет сервер из 02:
tools остаются, сверху добавляются resources и resource templates.

Показывает, как один и тот же домен выставляется одновременно двумя
примитивами — и в чём разница (см. README § «Когда tool, когда resource»).

Ожидает, что rest_api.py уже поднят на 127.0.0.1:8765.
"""

from __future__ import annotations

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base as prompts_base
from mcp.types import (
    Completion,
    CompletionArgument,
    CompletionContext,
    ContentBlock,
    EmbeddedResource,
    PromptReference,
    ResourceLink,
    ResourceTemplateReference,
    TextContent,
    TextResourceContents,
    ToolAnnotations,
)
from pydantic import AnyUrl, BaseModel

API_URL = "http://127.0.0.1:8765"

mcp = FastMCP("tasks")
http = httpx.Client(base_url=API_URL, timeout=5.0)


class Task(BaseModel):
    id: str
    title: str
    done: bool
    created_at: str


# ============================================================================
# Tools — без изменений из 02. Домен действий: создать/обновить/удалить/искать.
# ============================================================================


@mcp.tool(
    title="List tasks",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        openWorldHint=False,
    ),
)
def list_tasks() -> list[Task]:
    """Return every task currently stored."""
    r = http.get("/tasks")
    r.raise_for_status()
    return [Task(**t) for t in r.json()]


@mcp.tool(
    title="Get task by id",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        openWorldHint=False,
    ),
)
def get_task(task_id: str) -> Task:
    """Fetch a single task."""
    r = http.get(f"/tasks/{task_id}")
    r.raise_for_status()
    return Task(**r.json())


@mcp.tool(
    title="Create task",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def create_task(title: str) -> Task:
    """Create a new task with the given title. Returns the created task."""
    r = http.post("/tasks", json={"title": title})
    r.raise_for_status()
    return Task(**r.json())


@mcp.tool(
    title="Update task",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def update_task(
    task_id: str,
    title: str | None = None,
    done: bool | None = None,
) -> Task:
    """Modify a task. Idempotent: repeating the same call with the same arguments yields the same state."""
    body = {k: v for k, v in {"title": title, "done": done}.items() if v is not None}
    r = http.put(f"/tasks/{task_id}", json=body)
    r.raise_for_status()
    return Task(**r.json())


@mcp.tool(
    title="Delete task",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def delete_task(task_id: str) -> str:
    """Permanently remove a task. Calling twice is safe (no-op second time)."""
    r = http.delete(f"/tasks/{task_id}")
    r.raise_for_status()
    return f"deleted {task_id}"


@mcp.tool(
    title="Search tasks",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        openWorldHint=True,
    ),
)
def search_tasks(query: str) -> list[Task]:
    """Substring search over task titles. Marked openWorld to signal the server may talk to external systems."""
    r = http.get("/search", params={"q": query})
    r.raise_for_status()
    return [Task(**t) for t in r.json()]


# ============================================================================
# Resources — concrete. URI без параметров, один URI = один ресурс.
# FastMCP регистрирует их как FunctionResource: функция зовётся по read.
# ============================================================================


@mcp.resource(
    "tasks://all",
    title="Все задачи",
    description="Снимок всего списка задач одним JSON-массивом.",
    mime_type="application/json",
)
def all_tasks_resource() -> list[dict]:
    """Current snapshot of every task as a JSON array."""
    r = http.get("/tasks")
    r.raise_for_status()
    return r.json()


@mcp.resource(
    "tasks://stats",
    title="Статистика по задачам",
    description="Сводка: всего / выполнено / осталось. Текстовый plain-блок.",
    mime_type="text/plain",
)
def tasks_stats_resource() -> str:
    """Short human-readable summary of task counts."""
    r = http.get("/tasks")
    r.raise_for_status()
    tasks = r.json()
    total = len(tasks)
    done = sum(1 for t in tasks if t["done"])
    return f"total:   {total}\ndone:    {done}\npending: {total - done}\n"


# ============================================================================
# Resources — templates. URI с параметрами, RFC 6570. FastMCP матчит входящий
# URI на шаблон, извлекает параметры и передаёт их в функцию.
# Плейсхолдеры в URI обязаны совпадать с именами аргументов функции.
# ============================================================================


@mcp.resource(
    "tasks://id/{task_id}",
    title="Задача по id",
    description="Одна задача по её идентификатору.",
    mime_type="application/json",
)
def task_by_id_resource(task_id: str) -> dict:
    """Single task fetched by id."""
    r = http.get(f"/tasks/{task_id}")
    r.raise_for_status()
    return r.json()


@mcp.resource(
    "tasks://status/{status}",
    title="Задачи по статусу",
    description="Задачи, отфильтрованные по статусу: 'done' или 'pending'.",
    mime_type="application/json",
)
def tasks_by_status_resource(status: str) -> list[dict]:
    """Tasks filtered by status: either 'done' or 'pending'."""
    r = http.get("/tasks")
    r.raise_for_status()
    tasks = r.json()
    if status == "done":
        return [t for t in tasks if t["done"]]
    if status == "pending":
        return [t for t in tasks if not t["done"]]
    return []


# ============================================================================
# Completion — подсказки значений для аргументов template-ресурсов (и prompts).
# Один хендлер на весь сервер; сам различает, откуда пришёл запрос, по ref.
# ============================================================================


@mcp.completion()
async def complete(
    ref: PromptReference | ResourceTemplateReference,
    argument: CompletionArgument,
    context: CompletionContext | None,
) -> Completion | None:
    if not isinstance(ref, ResourceTemplateReference):
        return None

    if ref.uri == "tasks://status/{status}" and argument.name == "status":
        values = [s for s in ("done", "pending") if s.startswith(argument.value)]
        return Completion(values=values, total=len(values), hasMore=False)

    if ref.uri == "tasks://id/{task_id}" and argument.name == "task_id":
        r = http.get("/tasks")
        r.raise_for_status()
        ids = [t["id"] for t in r.json() if t["id"].startswith(argument.value)]
        return Completion(values=ids, total=len(ids), hasMore=False)

    return None


# ============================================================================
# Resource-блоки в других ответах.
# Tool возвращает text + resource_link (ссылка, клиент решит, читать ли).
# Prompt возвращает embedded resource (тело ресурса инлайн в сообщении).
# ============================================================================


@mcp.tool(
    title="Create task (with link)",
    annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False),
)
def create_task_linked(title: str):
    """Create a task and return a short confirmation + a resource_link to the new task.

    Нет return-аннотации сознательно: FastMCP без неё не строит output_schema и
    не дублирует блоки в structuredContent — в wire остаётся только content[].
    """
    r = http.post("/tasks", json={"title": title})
    r.raise_for_status()
    task = r.json()
    return [
        TextContent(type="text", text=f"created: {task['title']}"),
        ResourceLink(
            type="resource_link",
            uri=AnyUrl(f"tasks://id/{task['id']}"),
            name=f"task-{task['id'][:8]}",
            title=task["title"],
            mimeType="application/json",
        ),
    ]


@mcp.prompt(title="Show task inline")
def show_task(task_id: str) -> list[prompts_base.Message]:
    """User-facing prompt that embeds the full task JSON into the message as a resource."""
    r = http.get(f"/tasks/{task_id}")
    r.raise_for_status()
    task_json = r.text
    return [
        prompts_base.UserMessage("Объясни эту задачу, опираясь на её данные:"),
        prompts_base.UserMessage(
            content=EmbeddedResource(
                type="resource",
                resource=TextResourceContents(
                    uri=AnyUrl(f"tasks://id/{task_id}"),
                    mimeType="application/json",
                    text=task_json,
                ),
            )
        ),
    ]


if __name__ == "__main__":
    mcp.run()
