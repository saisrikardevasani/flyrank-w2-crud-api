import sqlite3
from typing import Annotated, Literal

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

# Every route now goes through db.py. Nothing is kept in memory between requests.


class TaskIn(BaseModel):
    """What a client is allowed to send. An empty or missing title is rejected."""

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    done: bool | None = None


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


@app.exception_handler(sqlite3.OperationalError)
async def busy_database(request, exc: sqlite3.OperationalError):
    """Another writer is holding the file (DB Browser with unsaved changes does this)."""
    return JSONResponse(status_code=503, content={"error": f"Database unavailable: {exc}"})


@app.exception_handler(RequestValidationError)
async def invalid_body(request, exc: RequestValidationError):
    """A body that fails validation is the client's fault: 400, not FastAPI's 422."""
    problem = exc.errors()[0]
    # loc looks like ("body", "title") for a field, or ("body", 39) for malformed JSON,
    # where 39 is a character offset. Dropping the numbers keeps the message readable.
    field = ".".join(p for p in problem["loc"][1:] if isinstance(p, str)) or "body"
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
    sort: Literal["id", "title"] = "id",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Filtering, searching and sorting all happen in SQL; Python never loops over rows.

    Values travel as ? parameters. A column name cannot be a parameter, so `sort` is a
    Literal: FastAPI rejects anything outside the two names before this function runs.
    """
    where, params = [], []
    if done is not None:
        where.append("done = ?")
        params.append(done)
    if search:
        where.append("title LIKE ?")
        params.append(f"%{search}%")
    sql = "SELECT * FROM tasks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {sort} LIMIT ? OFFSET ?"
    with db.transaction() as conn:
        return [db.to_task(row) for row in conn.execute(sql, (*params, limit, offset))]


@app.get("/tasks/{task_id}", summary="Get one task by id")
def get_task(task_id: int):
    with db.transaction() as conn:
        return fetch(conn, task_id)


@app.post("/tasks", status_code=201, summary="Create a task")
def create_task(body: TaskIn):
    """The database hands out the id; the client never sends one."""
    with db.transaction() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (title, done) VALUES (?, ?)", (body.title, bool(body.done))
        )
        return fetch(conn, cur.lastrowid)


@app.put("/tasks/{task_id}", summary="Replace a task")
def update_task(task_id: int, body: TaskIn):
    """A body without `done` keeps the stored value, so renaming a finished task keeps it done."""
    with db.transaction() as conn:
        done = fetch(conn, task_id)["done"] if body.done is None else body.done
        conn.execute(
            "UPDATE tasks SET title = ?, done = ?, updated_at = datetime('now') WHERE id = ?",
            (body.title, done, task_id),
        )
        return fetch(conn, task_id)


@app.delete("/tasks/{task_id}", status_code=204, summary="Delete a task")
def delete_task(task_id: int):
    with db.transaction() as conn:
        fetch(conn, task_id)
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


@app.get("/stats", summary="Count tasks by state")
def stats():
    with db.transaction() as conn:
        total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        done = conn.execute("SELECT COUNT(*) FROM tasks WHERE done = 1").fetchone()[0]
    return {"total": total, "done": done, "open": total - done}


@app.post("/reset", summary="Restore the 3 example tasks")
def reset():
    """Empty the table and seed it again. Ids restart at 1 because none are left to follow."""
    with db.transaction() as conn:
        conn.execute("DELETE FROM tasks")
    db.init()
    with db.transaction() as conn:
        return [db.to_task(row) for row in conn.execute("SELECT * FROM tasks")]
