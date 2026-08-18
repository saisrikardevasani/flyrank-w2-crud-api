from typing import Annotated, Optional

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints

app = FastAPI()

# In-memory "database" — a plain list. Restarting the server resets it.
tasks = [
    {"id": 1, "title": "Read the assignment", "done": True},
    {"id": 2, "title": "Build the CRUD API", "done": False},
    {"id": 3, "title": "Push it to GitHub", "done": False},
]


class TaskIn(BaseModel):
    """What a client is allowed to send. An empty or missing title is rejected."""

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    done: Optional[bool] = None


def find(task_id: int):
    """Return the task with this id, or raise a 404."""
    for task in tasks:
        if task["id"] == task_id:
            return task
    raise HTTPException(404, f"Task {task_id} not found")


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


@app.get("/")
def root():
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/tasks")
def list_tasks():
    return tasks


@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    return find(task_id)


@app.post("/tasks", status_code=201)
def create_task(body: TaskIn):
    task = {
        "id": max((t["id"] for t in tasks), default=0) + 1,
        "title": body.title,
        "done": bool(body.done),
    }
    tasks.append(task)
    return task
