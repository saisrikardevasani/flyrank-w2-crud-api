"""One runnable check for the whole CRUD cycle: python -m pytest, or just run this file."""

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_crud_cycle():
    client.post("/reset")

    assert client.get("/health").json() == {"status": "ok"}
    assert len(client.get("/tasks").json()) == 3

    created = client.post("/tasks", json={"title": "Buy milk"})
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert created.json()["done"] is False

    assert client.get(f"/tasks/{task_id}").status_code == 200
    assert client.get("/tasks/99").status_code == 404
    assert client.get("/tasks/99").json() == {"error": "Task 99 not found"}

    updated = client.put(f"/tasks/{task_id}", json={"title": "Buy oat milk", "done": True})
    assert updated.status_code == 200
    assert updated.json() == {"id": task_id, "title": "Buy oat milk", "done": True}
    assert client.put("/tasks/99", json={"title": "x"}).status_code == 404

    assert client.delete(f"/tasks/{task_id}").status_code == 204
    assert client.delete(f"/tasks/{task_id}").status_code == 404
    assert len(client.get("/tasks").json()) == 3


def test_validation_and_extras():
    client.post("/reset")

    for bad in ({}, {"title": ""}, {"title": "   "}):
        assert client.post("/tasks", json=bad).status_code == 400
        assert client.put("/tasks/1", json=bad).status_code == 400

    assert client.get("/tasks?done=true").json() == [main.SEED[0]]
    assert client.get("/tasks?search=github").json() == [main.SEED[2]]
    assert len(client.get("/tasks?limit=2&offset=2").json()) == 1
    assert client.get("/stats").json() == {"total": 3, "done": 1, "open": 2}


if __name__ == "__main__":
    test_crud_cycle()
    test_validation_and_extras()
    print("all checks passed")
