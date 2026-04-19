"""Учебный REST-сервис задач. Запускается как самостоятельный процесс,
хранит данные в памяти. Не MCP — обычный HTTP API, который мы оборачиваем.

Запуск автономно (для экспериментов curl'ом):
    uv run python rest_api.py

Но обычно этот файл стартует сам demo.py как subprocess.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class Task(BaseModel):
    id: str
    title: str
    done: bool
    created_at: str


class TaskCreate(BaseModel):
    title: str


class TaskUpdate(BaseModel):
    title: str | None = None
    done: bool | None = None


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


app = FastAPI(title="tasks-rest")
db: dict[str, Task] = {}


def seed() -> None:
    for title in ("buy milk", "write MCP handbook"):
        tid = str(uuid4())
        db[tid] = Task(id=tid, title=title, done=False, created_at=now())


seed()


@app.get("/tasks", response_model=list[Task])
def list_tasks() -> list[Task]:
    return list(db.values())


@app.get("/tasks/{task_id}", response_model=Task)
def get_task(task_id: str) -> Task:
    if task_id not in db:
        raise HTTPException(status_code=404, detail="task not found")
    return db[task_id]


@app.post("/tasks", response_model=Task, status_code=201)
def create_task(body: TaskCreate) -> Task:
    tid = str(uuid4())
    db[tid] = Task(id=tid, title=body.title, done=False, created_at=now())
    return db[tid]


@app.put("/tasks/{task_id}", response_model=Task)
def update_task(task_id: str, body: TaskUpdate) -> Task:
    if task_id not in db:
        raise HTTPException(status_code=404, detail="task not found")
    existing = db[task_id]
    patched = existing.model_copy(update=body.model_dump(exclude_unset=True))
    db[task_id] = patched
    return patched


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: str) -> None:
    db.pop(task_id, None)


@app.get("/search", response_model=list[Task])
def search_tasks(q: str) -> list[Task]:
    needle = q.lower()
    return [t for t in db.values() if needle in t.title.lower()]


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
