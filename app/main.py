from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(title="Demo Site", version="0.1.0")

app.mount("/static", StaticFiles(directory="static"), name="static")

_todos: dict[int, dict[str, object]] = {}
_next_id = 1

# In-memory mindmap storage (demo-only; resets on restart)
_mindmaps: dict[int, dict[str, Any]] = {}
_next_map_id = 1


class TodoCreate(BaseModel):
    title: str
    done: bool = False


class TodoUpdate(BaseModel):
    done: bool


class Todo(BaseModel):
    id: int
    title: str
    done: bool


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse("static/index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    # Avoid noisy 404s in terminal from browsers automatically requesting this.
    return FileResponse("static/favicon.ico")


@app.get("/apple-touch-icon.png", include_in_schema=False)
def apple_touch_icon() -> FileResponse:
    # Avoid noisy 404s on iOS/Safari.
    return FileResponse("static/apple-touch-icon.png")


@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
def apple_touch_icon_precomposed() -> FileResponse:
    # Avoid noisy 404s on iOS/Safari.
    return FileResponse("static/apple-touch-icon-precomposed.png")


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


@app.patch("/todos/{todo_id}", response_model=Todo)
def update_todo(todo_id: int, payload: TodoUpdate) -> Todo:
    if todo_id not in _todos:
        raise HTTPException(status_code=404, detail="Not found")
    _todos[todo_id]["done"] = payload.done
    return Todo(**_todos[todo_id])  # type: ignore[arg-type]


@app.delete("/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int) -> None:
    if todo_id not in _todos:
        raise HTTPException(status_code=404, detail="Not found")
    del _todos[todo_id]
    return None


# --------------------
# Mindmap (AI-assisted)
# --------------------

class MindmapCreate(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)


class MindmapExpand(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=200)


class MindmapNode(BaseModel):
    id: str
    label: str
    parent_id: str | None = None
    depth: int = 0


class MindmapResponse(BaseModel):
    map_id: int
    root_id: str
    nodes: list[MindmapNode]


def _env_openai_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def _fallback_expand(seed: str, depth: int) -> list[str]:
    # Deterministic-ish fallback expansion (no external AI).
    base = seed.strip().rstrip(".?!")
    if not base:
        base = "Idea"

    if depth <= 0:
        return [
            f"What is {base}?",
            "Key components",
            "Examples",
            "Risks & constraints",
            "Next steps",
        ]

    # For deeper expansions, keep it short and actionable.
    return [
        "Define",
        "Break into steps",
        "Tools / resources",
        "Measure success",
        "Common pitfalls",
    ]


async def _ai_expand_idea(prompt: str, *, depth: int) -> list[str]:
    """Return a list of node labels that expand the prompt.

    Uses OpenAI if OPENAI_API_KEY is present; otherwise uses a local fallback.
    """

    api_key = _env_openai_key()
    if not api_key:
        return _fallback_expand(prompt, depth)

    # Lazy import so tests/run don't require this dependency.
    try:
        from openai import AsyncOpenAI  # type: ignore
    except Exception:
        return _fallback_expand(prompt, depth)

    client = AsyncOpenAI(api_key=api_key)

    system = (
        "You expand ideas into concise mindmap child nodes. "
        "Return ONLY a JSON array of short strings (2-6 words each), 5 to 8 items. "
        "No extra keys, no explanations."
    )

    user = (
        f"Parent node: {prompt}\n"
        f"Depth: {depth}\n"
        "Generate child nodes that expand this idea."
    )

    try:
        resp = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.6,
        )
        content = (resp.choices[0].message.content or "").strip()

        # Expect a JSON array of strings.
        import json

        data = json.loads(content)
        if not isinstance(data, list):
            return _fallback_expand(prompt, depth)
        out: list[str] = []
        for item in data:
            if isinstance(item, str):
                s = item.strip()
                if s:
                    out.append(s)
        if len(out) < 3:
            return _fallback_expand(prompt, depth)
        return out[:10]
    except Exception:
        return _fallback_expand(prompt, depth)


def _new_node_id(map_id: int, parent_id: str | None, idx: int) -> str:
    if parent_id is None:
        return f"m{map_id}:root"
    return f"m{map_id}:{parent_id}.{idx}"


@app.post("/mindmap", response_model=MindmapResponse, status_code=201)
async def create_mindmap(payload: MindmapCreate) -> MindmapResponse:
    global _next_map_id

    map_id = _next_map_id
    _next_map_id += 1

    root_id = _new_node_id(map_id, None, 0)
    root = MindmapNode(id=root_id, label=payload.prompt.strip(), parent_id=None, depth=0)

    children_labels = await _ai_expand_idea(payload.prompt, depth=0)
    children: list[MindmapNode] = []
    for i, label in enumerate(children_labels, start=1):
        children.append(
            MindmapNode(
                id=_new_node_id(map_id, root_id, i),
                label=label,
                parent_id=root_id,
                depth=1,
            )
        )

    nodes = [root, *children]
    _mindmaps[map_id] = {
        "map_id": map_id,
        "root_id": root_id,
        "nodes": {n.id: n.model_dump() for n in nodes},
    }

    return MindmapResponse(map_id=map_id, root_id=root_id, nodes=nodes)


@app.post("/mindmap/{map_id}/expand", response_model=list[MindmapNode])
async def expand_mindmap_node(map_id: int, payload: MindmapExpand) -> list[MindmapNode]:
    if map_id not in _mindmaps:
        raise HTTPException(status_code=404, detail="Mindmap not found")

    store = _mindmaps[map_id]
    nodes: dict[str, dict[str, Any]] = store["nodes"]

    if payload.node_id not in nodes:
        raise HTTPException(status_code=404, detail="Node not found")

    parent = nodes[payload.node_id]
    parent_depth = int(parent.get("depth", 0))

    # Do not duplicate children on repeated clicks.
    existing_children = [n for n in nodes.values() if n.get("parent_id") == payload.node_id]
    if existing_children:
        return [MindmapNode(**c) for c in existing_children]

    labels = await _ai_expand_idea(str(parent.get("label", "")), depth=parent_depth)
    new_children: list[MindmapNode] = []
    for i, label in enumerate(labels, start=1):
        nid = _new_node_id(map_id, payload.node_id, i)
        node = MindmapNode(id=nid, label=label, parent_id=payload.node_id, depth=parent_depth + 1)
        nodes[nid] = node.model_dump()
        new_children.append(node)

    return new_children
