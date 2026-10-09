"""Requests the platform could plausibly send must never be answered with a permanent 4xx: Add 422 is not retried
(the task fails, and a Full run is published only when every task succeeded) and a Search 4xx loses the question.
Shapes below come from the API guide (role + non-empty content, optional ms timestamp, top-level options array) and
from the public ScriptMem schema (narration lines with a null speaker, "Unknown" session dates)."""
import os
import tempfile

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import parse_timestamp
from app.store import MemoryStore


def make_client(**overrides):
    tmp = tempfile.TemporaryDirectory()
    settings = Settings(api_key="", data_dir=os.path.join(tmp.name, "d"), **overrides)
    client = TestClient(create_app(settings=settings, store=MemoryStore(settings.data_dir)))
    client.__enter__()
    client._tmp = tmp
    return client


def add(c, messages, rid="eval:r:scriptmem:conv-0:chunk-0"):
    return c.post("/v1/memories/add", json={"request_id": rid, "user_id": "u", "session_id": "s", "messages": messages})


def test_parse_timestamp_shapes():
    assert parse_timestamp(1704067200000) == 1704067200000
    assert parse_timestamp(1704067200000.0) == 1704067200000
    assert parse_timestamp("1704067200000") == 1704067200000
    assert parse_timestamp("2024-01-01T00:00:00Z") == 1704067200000
    assert parse_timestamp("2024-01-01T00:00:00") == 1704067200000
    assert parse_timestamp(1704067200000000) == 1704067200000          # microseconds
    assert parse_timestamp(1704067200000000000) == 1704067200000       # nanoseconds
    assert parse_timestamp(-400000000000) == -400000000000             # 1957: scripts are set before 1970
    for junk in (None, "", "Unknown", "September 22, 1994", True, float("nan"), float("inf"), [1], {"a": 1}):
        assert parse_timestamp(junk) is None, junk


def test_add_accepts_script_style_and_odd_messages():
    c = make_client()
    r = add(c, [
        {"role": "user", "content": "Juror 8: I just want to talk about it."},
        {"role": None, "content": "The jurors file into the room. It is very hot."},          # narration, null speaker
        {"role": "narrator", "timestamp": "Unknown", "content": "The Foreman counts the slips."},
        {"content": "No role at all, the door is locked from the outside."},
        {"role": 7, "timestamp": "2024-01-01T00:00:00Z", "content": "Numeric role, ISO timestamp."},
        {"role": "user", "timestamp": None, "content": None},                                   # skipped, not rejected
        {"role": "user", "content": {"type": "text", "text": "A single content part as an object."}},
        {"role": "user", "content": [{"type": "text", "text": "Parts"}, {"type": "image_url", "image_url": {"url": "data:x"}}]},
        {"role": "user", "timestamp": -400000000000, "content": "A line stamped in 1957."},
        {"role": "user", "content": 12345, "name": "ignored extra field", "metadata": {"x": 1}},
    ])
    assert r.status_code == 200, r.text
    assert r.json() == {"success": True, "request_id": "eval:r:scriptmem:conv-0:chunk-0", "user_id": "u", "session_id": "s"}
    data = c.post("/v1/memories/search", json={"query": "door locked jurors slips 1957 parts object 12345", "user_id": "u", "top_k": 100}).json()["data"]
    text = "\n".join(d["content"] for d in data)
    for needle in ("jurors file into the room", "Foreman counts the slips", "door is locked", "ISO timestamp", "single content part",
                   "Parts", "stamped in 1957", "12345"):
        assert needle in text, needle
    assert "[1957-04-29" in text and "[2024-01-01 00:00 UTC] 7:" in text
    assert "NARRATOR: The Foreman" in text and "USER: The jurors file" in text
    assert all(d["id"] and d["content"] for d in data)                                          # contract: both non-empty
    assert add(c, [{"role": "user", "content": None}, {"role": "user", "content": "   "}], rid="eval:r:scriptmem:conv-0:chunk-1").status_code == 200


def test_search_accepts_odd_requests():
    c = make_client()
    add(c, [{"role": "user", "content": f"Dexter: line number {i} about the lost ring."} for i in range(8)])
    base = {"user_id": "u"}
    ok = lambda body: c.post("/v1/memories/search", json={**base, **body})
    for body in (
        {"query": "lost ring", "top_k": 100},
        {"query": "lost ring"},                                                    # top_k missing
        {"query": "lost ring", "top_k": None},
        {"query": "lost ring", "top_k": "100"},
        {"query": "lost ring", "top_k": 0},
        {"query": "lost ring", "top_k": 100000},
        {"query": "lost ring", "top_k": 100, "options": "A. the ring"},           # one string
        {"query": "lost ring", "top_k": 100, "options": {"A": "the ring", "B": "the watch"}},
        {"query": "lost ring", "top_k": 100, "options": [{"label": "A", "text": "the ring"}, {"text": "the watch"}, None, 3]},
        {"query": "lost ring", "top_k": 100, "options": []},
        {"query": [{"type": "text", "text": "lost ring"}], "top_k": 100},         # content parts
        {"query": "", "top_k": 100},                                              # blank -> newest turns, still 200
        {"query": None, "top_k": 100},
        {"top_k": 100},
    ):
        r = ok(body)
        assert r.status_code == 200, (body, r.text)
        data = r.json()["data"]
        assert isinstance(data, list) and len(data) <= 100 and data, body
        assert all(d["id"] and d["content"] for d in data)
    assert len(ok({"query": "lost ring", "top_k": 0}).json()["data"]) == 1        # clamped to 1, never more than top_k
    assert ok({"query": "lost ring", "top_k": 3}).json()["data"].__len__() <= 3
    assert c.post("/v1/memories/search", json={"query": "x", "user_id": "", "top_k": 5}).status_code == 422   # no user: cannot serve
    assert c.post("/v1/memories/search", json={"query": "x", "user_id": "nobody", "top_k": 5}).json() == {"data": []}
