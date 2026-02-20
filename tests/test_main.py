from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root() -> None:
    assert client.get("/").status_code == 200


def test_create_and_get_todo() -> None:
    r = client.post("/todos", json={"title": "Buy milk"})
    assert r.status_code == 201
    todo_id = r.json()["id"]

    r2 = client.get(f"/todos/{todo_id}")
    assert r2.status_code == 200
    assert r2.json()["title"] == "Buy milk"


def test_list_todos() -> None:
    r = client.get("/todos")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_missing_todo() -> None:
    r = client.get("/todos/99999")
    assert r.status_code == 404


def test_delete_todo_success() -> None:
    r = client.post("/todos", json={"title": "Delete me"})
    assert r.status_code == 201
    todo_id = r.json()["id"]

    d = client.delete(f"/todos/{todo_id}")
    assert d.status_code == 204

    r2 = client.get(f"/todos/{todo_id}")
    assert r2.status_code == 404


def test_delete_missing_todo() -> None:
    d = client.delete("/todos/99999")
    assert d.status_code == 404
