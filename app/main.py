from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Demo Site", version="0.1.0")

_todos: dict[int, dict[str, object]] = {}
_next_id = 1


class TodoCreate(BaseModel):
    title: str
    done: bool = False


class Todo(BaseModel):
    id: int
    title: str
    done: bool


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/todos", response_model=list[Todo])
def list_todos() -> list[Todo]:
    return [Todo(**t) for t in _todos.values()]  # type: ignore[arg-type]


@app.post("/todos", response_model=Todo, status_code=201)
def create_todo(payload: TodoCreate) -> Todo:
    global _next_id
    todo = Todo(id=_next_id, title=payload.title, done=payload.done)
    _todos[_next_id] = todo.model_dump()
    _next_id += 1
    return todo


@app.get("/todos/{todo_id}", response_model=Todo)
def get_todo(todo_id: int) -> Todo:
    if todo_id not in _todos:
        raise HTTPException(status_code=404, detail="Not found")
    return Todo(**_todos[todo_id])  # type: ignore[arg-type]


@app.delete("/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int) -> None:
    if todo_id not in _todos:
        raise HTTPException(status_code=404, detail="Not found")
    del _todos[todo_id]
    return None
