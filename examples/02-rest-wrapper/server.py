"""MCP-обёртка над REST-сервисом задач.

Показывает два новых относительно 01 концепта:
  1. Tool annotations — подсказки LLM о характере операции
     (readOnly / destructive / idempotent / openWorld).
  2. structuredContent, выведенный из Pydantic-моделей в type hints.

Ожидает, что rest_api.py уже поднят на 127.0.0.1:8765.
"""

from __future__ import annotations

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel

API_URL = "http://127.0.0.1:8765"

mcp = FastMCP("tasks")
http = httpx.Client(base_url=API_URL, timeout=5.0)


class Task(BaseModel):
    id: str
    title: str
    done: bool
    created_at: str


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


if __name__ == "__main__":
    mcp.run()
