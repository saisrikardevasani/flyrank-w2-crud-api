from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints

import db

db.init()

app = FastAPI(
    title="Task API",
    version="1.0",
    description="A tiny to-do API. Tasks are stored in a SQLite file, so they survive a restart.",
)

# The three example tasks now live in db.py, which puts them in tasks.db on first run.
# The write routes below still use this list; stages 2 and 3 move them onto SQL as well.
SEED = db.SEED
tasks = [dict(t) for t in SEED]


class TaskIn(BaseModel):
    """What a client is allowed to send. An empty or missing title is rejected."""

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    done: bool | None = None


def find(task_id: int):
    """Return the in-memory task with this id, or raise a 404. Stage 3 retires this."""
    for task in tasks:
        if task["id"] == task_id:
            return task
    raise HTTPException(404, f"Task {task_id} not found")


def fetch(conn, task_id: int) -> dict:
    """Read one row by id, or raise a 404. The id travels as a parameter, never as text."""
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Task {task_id} not found")
    return db.to_task(row)


@app.exception_handler(HTTPException)
async def error_shape(request, exc: HTTPException):
    """Every error answers with {"error": "..."} instead of FastAPI's default."""
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def invalid_body(request, exc: RequestValidationError):
    """A body that fails validation is the client's fault: 400, not FastAPI's 422."""
    problem = exc.errors()[0]
    field = ".".join(str(part) for part in problem["loc"][1:]) or "body"
    return JSONResponse(status_code=400, content={"error": f"{field}: {problem['msg']}"})


@app.get("/", summary="What this API is")
def root():
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


@app.get("/health", summary="Is the server alive?")
def health():
    return {"status": "ok"}


@app.get("/tasks", summary="List tasks, optionally filtered")
def list_tasks(
    done: bool | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """limit/offset is capped at 100 so this never returns an unbounded list."""
    with db.transaction() as conn:
        found = [db.to_task(row) for row in conn.execute("SELECT * FROM tasks")]
    if done is not None:
        found = [t for t in found if t["done"] == done]
    if search:
        found = [t for t in found if search.lower() in t["title"].lower()]
    return found[offset : offset + limit]


@app.get("/tasks/{task_id}", summary="Get one task by id")
def get_task(task_id: int):
    with db.transaction() as conn:
        return fetch(conn, task_id)


@app.post("/tasks", status_code=201, summary="Create a task")
def create_task(body: TaskIn):
    task = {
        "id": max((t["id"] for t in tasks), default=0) + 1,
        "title": body.title,
        "done": bool(body.done),
    }
    tasks.append(task)
    return task


@app.put("/tasks/{task_id}", summary="Replace a task")
def update_task(task_id: int, body: TaskIn):
    task = find(task_id)
    task["title"] = body.title
    if body.done is not None:
        task["done"] = body.done
    return task


@app.delete("/tasks/{task_id}", status_code=204, summary="Delete a task")
def delete_task(task_id: int):
    tasks.remove(find(task_id))


@app.get("/stats", summary="Count tasks by state")
def stats():
    done = sum(1 for t in tasks if t["done"])
    return {"total": len(tasks), "done": done, "open": len(tasks) - done}


@app.post("/reset", summary="Restore the 3 example tasks")
def reset():
    tasks[:] = [dict(t) for t in SEED]
    return tasks
