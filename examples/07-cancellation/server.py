"""MCP-сервер из 06 + один новый tool slow_cancellable_import.

Главная идея 07 — `notifications/cancelled` и кооперативная отмена.
Логика та же, что у slow_bulk_import из 06, но с try/finally:
после отмены в stderr печатается, сколько задач успело создаться.
Это и есть демонстрация «cancel — это "перестань делать", а не "откати"».

Ожидает, что rest_api.py уже поднят на 127.0.0.1:8765.
"""

from __future__ import annotations

import asyncio
import sys

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.prompts import base as prompts_base
from mcp.types import (
    Completion,
    CompletionArgument,
    CompletionContext,
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
# Tools — без изменений из 02/05/06.
# ============================================================================


@mcp.tool(
    title="List tasks",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
)
def list_tasks() -> list[Task]:
    """Return every task currently stored."""
    r = http.get("/tasks")
    r.raise_for_status()
    return [Task(**t) for t in r.json()]


@mcp.tool(
    title="Get task by id",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
)
def get_task(task_id: str) -> Task:
    """Fetch a single task."""
    r = http.get(f"/tasks/{task_id}")
    r.raise_for_status()
    return Task(**r.json())


@mcp.tool(
    title="Create task",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
    ),
)
def create_task(title: str) -> Task:
    """Create a new task with the given title."""
    r = http.post("/tasks", json={"title": title})
    r.raise_for_status()
    return Task(**r.json())


@mcp.tool(
    title="Update task",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def update_task(
    task_id: str,
    title: str | None = None,
    done: bool | None = None,
) -> Task:
    """Modify a task. Idempotent."""
    body = {k: v for k, v in {"title": title, "done": done}.items() if v is not None}
    r = http.put(f"/tasks/{task_id}", json=body)
    r.raise_for_status()
    return Task(**r.json())


@mcp.tool(
    title="Delete task",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
    ),
)
def delete_task(task_id: str) -> str:
    """Permanently remove a task."""
    r = http.delete(f"/tasks/{task_id}")
    r.raise_for_status()
    return f"deleted {task_id}"


@mcp.tool(
    title="Search tasks",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
def search_tasks(query: str) -> list[Task]:
    """Substring search over task titles."""
    r = http.get("/search", params={"q": query})
    r.raise_for_status()
    return [Task(**t) for t in r.json()]


# ============================================================================
# Resources, completion, resource_link / embedded — копия из 05/06.
# ============================================================================


@mcp.resource(
    "tasks://all",
    title="Все задачи",
    description="Снимок всего списка задач одним JSON-массивом.",
    mime_type="application/json",
)
def all_tasks_resource() -> list[dict]:
    r = http.get("/tasks")
    r.raise_for_status()
    return r.json()


@mcp.resource(
    "tasks://stats",
    title="Статистика по задачам",
    description="Сводка: всего / выполнено / осталось.",
    mime_type="text/plain",
)
def tasks_stats_resource() -> str:
    r = http.get("/tasks")
    r.raise_for_status()
    tasks = r.json()
    total = len(tasks)
    done = sum(1 for t in tasks if t["done"])
    return f"total:   {total}\ndone:    {done}\npending: {total - done}\n"


@mcp.resource(
    "tasks://id/{task_id}",
    title="Задача по id",
    description="Одна задача по её идентификатору.",
    mime_type="application/json",
)
def task_by_id_resource(task_id: str) -> dict:
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
    r = http.get("/tasks")
    r.raise_for_status()
    tasks = r.json()
    if status == "done":
        return [t for t in tasks if t["done"]]
    if status == "pending":
        return [t for t in tasks if not t["done"]]
    return []


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


@mcp.tool(
    title="Create task (with link)",
    annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False),
)
def create_task_linked(title: str):
    """Create a task and return text + resource_link."""
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
    """Embed full task JSON into a prompt message as a resource."""
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


# ============================================================================
# Долгие tool'ы из 06 — оставляем как было.
# ============================================================================


@mcp.tool(
    title="Bulk import tasks (slow)",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
async def slow_bulk_import(count: int, ctx: Context) -> str:
    """Same as in 06: creates tasks with delay between each, emits progress."""
    count = max(1, min(count, 20))
    for i in range(count):
        r = http.post("/tasks", json={"title": f"imported-task-{i + 1}"})
        r.raise_for_status()
        await ctx.report_progress(
            progress=i + 1,
            total=count,
            message=f"Created task {i + 1}/{count}",
        )
        await asyncio.sleep(0.5)
    return f"Imported {count} tasks."


@mcp.tool(
    title="Log demo",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
)
async def log_demo(ctx: Context) -> str:
    """Emit four notifications/message at debug/info/warning/error."""
    await ctx.debug("debug-level note")
    await ctx.info("info-level note")
    await ctx.warning("warning-level note")
    await ctx.error("error-level note")
    return "emitted 4 log notifications"


# ============================================================================
# ШАГ 07 — slow_cancellable_import.
#
# То же тело, что у slow_bulk_import, но с try/finally. Когда клиент шлёт
# notifications/cancelled, FastMCP отменяет cancel-scope тула — ближайший
# `await` (`asyncio.sleep` или `report_progress`) поднимает CancelledError.
# Хэндлер размотывается, finally отрабатывает — пишем в stderr, сколько
# задач успело создаться. На этой строке стоит вся практическая мысль главы:
# отмена не магия и точно не транзакция.
# ============================================================================


@mcp.tool(
    title="Bulk import tasks (cancellable)",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
async def slow_cancellable_import(count: int, ctx: Context) -> str:
    """Like slow_bulk_import, but logs how many tasks were created if cancelled.

    The try/finally still runs when the handler is cancelled — that's where
    we'd commit a checkpoint, release a lock, or roll back a transaction in
    a real server. Here we just print to stderr so it shows up in Inspector's
    Server Notifications panel.
    """
    count = max(1, min(count, 20))
    created = 0
    try:
        for i in range(count):
            r = http.post("/tasks", json={"title": f"cancellable-task-{i + 1}"})
            r.raise_for_status()
            created += 1
            await ctx.report_progress(
                progress=i + 1,
                total=count,
                message=f"Created task {i + 1}/{count}",
            )
            await asyncio.sleep(0.5)
        return f"Imported {count} tasks."
    finally:
        # Печатаем синхронно — внутри отменённого scope любой `await` снова
        # бросит CancelledError, поэтому ctx.info(...) тут не подойдёт.
        print(
            f"[cleanup] slow_cancellable_import: created={created}/{count}",
            file=sys.stderr,
            flush=True,
        )


if __name__ == "__main__":
    mcp.run()
