"""v0.4 behaviours: relative-time notes in rendered content and the OPTIONS_MODE retrieval knob."""
from datetime import datetime, timezone

from tests.test_search_v02 import add, make_client, search

TS = int(datetime(2025, 4, 27, 7, 50, tzinfo=timezone.utc).timestamp() * 1000)


def test_time_notes_rendered_and_switchable():
    c = make_client()
    try:
        add(c, "c:chunk-0", "u", [{"role": "user", "content": "Did my first 5k yesterday along the river.", "timestamp": TS},
                                 {"role": "user", "content": "前天把样品寄出去了。", "timestamp": TS}])
        data = search(c, "u", "first 5k river")
        assert "(dates: yesterday = 2025-04-26)" in data[0]["content"]
        data = search(c, "u", "样品寄出")
        assert "(dates: 前天 = 2025-04-25)" in data[0]["content"]
    finally:
        c.__exit__(None, None, None)
    c = make_client(time_notes=False)
    try:
        add(c, "c:chunk-0", "u", [{"role": "user", "content": "Did my first 5k yesterday along the river.", "timestamp": TS}])
        assert "(dates:" not in search(c, "u", "first 5k river")[0]["content"]
    finally:
        c.__exit__(None, None, None)


def test_time_notes_need_a_timestamp():
    c = make_client()
    try:
        add(c, "c:chunk-0", "u", [{"role": "user", "content": "Did my first 5k yesterday along the river."}])
        assert "(dates:" not in search(c, "u", "first 5k river")[0]["content"]
    finally:
        c.__exit__(None, None, None)


MSGS = [{"role": "user", "content": "My cat is called Pixel and he wakes me at 6:30."},
        {"role": "user", "content": "Dani is coming to the wedding with her cat Mochi in tow."},
        {"role": "user", "content": "The vet visit cost 85 euros in May."}]
OPTS = ["A. Mochi", "B. Pixel", "C. Biscuit"]


def _first(c):
    return search(c, "u", "What is the name of the cat that wakes her up?", options=OPTS)[0]["content"]


def test_options_modes():
    c = make_client(options_mode="append")
    try:
        add(c, "c:chunk-0", "u", MSGS)
        contents = [r["content"] for r in search(c, "u", "What is the name of the cat that wakes her up?", options=OPTS)]
        assert any("Mochi" in x for x in contents)          # options pulled the distractor turn in too
        assert "Pixel" in contents[0]                        # but the question's own terms still lead
    finally:
        c.__exit__(None, None, None)
    c = make_client(options_mode="none")
    try:
        add(c, "c:chunk-0", "u", MSGS)
        contents = [r["content"] for r in search(c, "u", "What is the name of the cat that wakes her up?", options=OPTS)]
        assert "Pixel" in contents[0]
        assert not any("Mochi" in x for x in contents if "Pixel" not in x)   # distractor-only turn not retrieved
    finally:
        c.__exit__(None, None, None)
    c = make_client(options_mode="channel", options_weight=0.6)
    try:
        add(c, "c:chunk-0", "u", MSGS)
        contents = [r["content"] for r in search(c, "u", "What is the name of the cat that wakes her up?", options=OPTS)]
        assert "Pixel" in contents[0]
        assert any("Mochi" in x for x in contents)          # present, but behind the question's own evidence
    finally:
        c.__exit__(None, None, None)
