from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()

# In-memory "database" — a plain list. Restarting the server resets it.
tasks = [
    {"id": 1, "title": "Read the assignment", "done": True},
    {"id": 2, "title": "Build the CRUD API", "done": False},
    {"id": 3, "title": "Push it to GitHub", "done": False},
]


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
