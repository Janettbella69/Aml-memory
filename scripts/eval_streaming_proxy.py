"""Replay OUR streaming proxy through the service, Search at every checkpoint, answer with the organisers' prompts.

Data   : evalset/streaming_proxy/streams.json + questions.json (built by gen_streams.py; synthetic, ours).
Replay : sessions are Added in order (one Add per session, chunk ids as the platform sends them); after session i
         every question whose checkpoint is i is searched - so a question only ever sees what was written so far.
Answer : open questions use the LoCoMo/LongMemEval OPEN_ENDED_ANSWER_TEMPLATE, multiple choice the ScriptMem
         CHOICE_ANSWER_TEMPLATE, both loaded at runtime from a local clone of the organisers' repository (AML_OFFICIAL),
         answered by gpt-4o-mini at temperature 0 (OPENAI_API_KEY / OPENAI_BASE_URL from .env).
Score  : multiple choice = exact letter (official scorer); open = strict (the gold value is in the answer AND no stale
         value is) and lenient (the gold value is in the answer).
Retrieval metrics need no model: is the turn that states the current value in the list, at what rank, and how many
turns stating a stale value are ranked above it.

    AML_OFFICIAL=/path/to/clone EMBED_MODEL=text-embedding-v4 EMBED_CACHE=/tmp/emb.sqlite \
      env -u OPENAI_API_KEY uv run --env-file .env python scripts/eval_streaming_proxy.py --label v1 [--no-answer]
    ... --no-timestamps                 # sessions are sent without timestamps (task-unit shape)
    TURN_MARKS=untimed ... --no-timestamps --label marks
    OPTIONS_MODE=none ... --label noopts
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import statistics
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
OFFICIAL = Path(os.environ.get("AML_OFFICIAL", "")) if os.environ.get("AML_OFFICIAL") else None


def load_official(name: str):
    if OFFICIAL is None:
        sys.exit("AML_OFFICIAL must point at a clone of github.com/AML-memory/agent-memory-leaderboard")
    spec = importlib.util.spec_from_file_location(f"aml_{name}", str(OFFICIAL / f"data/{name}/pipeline.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


KEY = os.environ.get("OPENAI_API_KEY", "")
BASE = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
MODEL = os.environ.get("ANSWER_MODEL", "openai/gpt-4o-mini")
WS = re.compile(r"\s+")


def norm(s: str) -> str:
    return WS.sub(" ", s.strip().lower())


def chat(prompt: str, max_tokens: int = 256) -> tuple[str, dict]:
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": max_tokens}
    req = urllib.request.Request(BASE + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    delay = 2.0
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                out = json.load(r)
            return out["choices"][0]["message"]["content"].strip(), out.get("usage", {})
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            if attempt == 5:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 30)
    raise RuntimeError("unreachable")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--streams", default=str(REPO / "evalset/streaming_proxy/streams.json"))
    ap.add_argument("--questions", default=str(REPO / "evalset/streaming_proxy/questions.json"))
    ap.add_argument("--label", default="proxy")
    ap.add_argument("--out-dir", default=str(REPO / "evalset/results"))
    ap.add_argument("--no-answer", action="store_true", help="retrieval metrics only, no model calls")
    ap.add_argument("--no-timestamps", action="store_true", help="send every session without timestamps")
    ap.add_argument("--users", help="comma-separated user ids to run, e.g. stream-0")
    ap.add_argument("--limit", type=int, help="stop after this many questions per user")
    args = ap.parse_args()
    if not args.no_answer and not KEY:
        sys.exit("OPENAI_API_KEY is not set")

    locomo = load_official("locomo-refined")
    scriptmem = load_official("scriptmem")
    streams = json.load(open(args.streams, encoding="utf-8"))
    questions = json.load(open(args.questions, encoding="utf-8"))
    if args.users:
        wanted = set(args.users.split(","))
        streams = [s for s in streams if s["user"] in wanted]
        questions = [q for q in questions if q["user"] in wanted]

    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app
    from app.store import MemoryStore

    tmp = tempfile.TemporaryDirectory()
    settings = replace(Settings.from_env(), api_key="", data_dir=os.path.join(tmp.name, "d"), log_level="WARNING")
    print(f"config: embed={settings.embed_model!r} planner={settings.planner_model!r} rerank={settings.rerank_model!r} "
          f"options={settings.options_mode} turn_marks={settings.turn_marks} time_notes={settings.time_notes} "
          f"window={settings.context_window} timestamps={'off' if args.no_timestamps else 'on'} answer={MODEL}", flush=True)
    client = TestClient(create_app(settings=settings, store=MemoryStore(settings.data_dir)))
    client.__enter__()
    run = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    rows: list[dict] = []
    for stream in streams:
        uid = stream["user"]
        user = f"eval:{run}:streaming:{uid}"
        by_checkpoint: dict[int, list[dict]] = defaultdict(list)
        for q in questions:
            if q["user"] == uid:
                by_checkpoint[q["checkpoint"]].append(q)
        texts: dict[str, str] = {}
        done = 0
        for i, sess in enumerate(stream["sessions"]):
            start = datetime.strptime(sess["start"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            msgs = []
            for j, m in enumerate(sess["messages"]):
                item = {"role": m["role"], "content": m["content"]}
                if not args.no_timestamps:
                    item["timestamp"] = int((start + timedelta(seconds=40 * j)).timestamp() * 1000)
                msgs.append(item)
                if m.get("key"):
                    texts[m["key"]] = norm(m["content"])
            r = client.post("/v1/memories/add", json={"request_id": f"eval:{run}:streaming:{uid}:chunk-{i}", "user_id": user,
                                                     "session_id": f"eval:{run}:streaming:{uid}:session-{i}", "messages": msgs})
            assert r.status_code == 200, r.text
            for q in by_checkpoint.get(i, []):
                if args.limit and done >= args.limit:
                    break
                done += 1
                body = {"query": q["question"], "user_id": user, "top_k": 100}
                if q.get("options"):
                    body["options"] = q["options"]
                t0 = time.time()
                data = client.post("/v1/memories/search", json=body).json()["data"]
                latency = time.time() - t0
                blocks = [norm(d["content"]) for d in data]
                gold_text = texts[q["evidence_key"]]
                gold_rank = next((k + 1 for k, b in enumerate(blocks) if gold_text in b), None)
                stale_texts = [texts[k] for k in q.get("stale_keys", []) if k in texts]
                stale_above = sum(1 for b in blocks[: (gold_rank or len(blocks) + 1) - 1] if any(s in b for s in stale_texts))
                mem = "\n".join(f"- [{d['created_at']}] {d['content']}" if d.get("created_at") else f"- {d['content']}" for d in data)
                row = {"qid": q["qid"], "user": uid, "kind": q["kind"], "slot": q["slot"], "checkpoint": i,
                       "gold_in_list": gold_rank is not None, "gold_rank": gold_rank, "stale_above": stale_above,
                       "results": len(data), "chars": len(mem), "latency_s": round(latency, 2)}
                if not args.no_answer:
                    if q.get("options"):
                        prompt = (scriptmem.CHOICE_ANSWER_TEMPLATE.replace("{{speaker_1_name}}", "the user")
                                  .replace("{{speaker_1_memories}}", mem).replace("{{speaker_2_name}}", "(no second speaker)")
                                  .replace("{{speaker_2_memories}}", "").replace("{{question}}", q["question"]))
                        pred, u = chat(prompt)
                        letters, malformed = scriptmem.predicted_letters(pred, "single_choice")
                        score = scriptmem.score_item("single_choice", [q["gold_letter"]], letters, malformed)
                        row.update({"prediction": pred, "predicted": letters, "strict": bool(score), "lenient": bool(score)})
                    else:
                        prompt = (locomo.OPEN_ENDED_ANSWER_TEMPLATE.replace("{{speaker_1_name}}", "the user")
                                  .replace("{{speaker_1_memories}}", mem).replace("{{speaker_2_name}}", "(no second speaker)")
                                  .replace("{{speaker_2_memories}}", "").replace("{{question}}", q["question"]))
                        pred, u = chat(prompt)
                        p = norm(pred)
                        gold_in = norm(q["gold_value"]) in p
                        stale_in = any(norm(s) in p for s in q.get("stale_values", []))
                        row.update({"prediction": pred, "strict": gold_in and not stale_in, "lenient": gold_in})
                    usage["prompt_tokens"] += u.get("prompt_tokens", 0)
                    usage["completion_tokens"] += u.get("completion_tokens", 0)
                rows.append(row)
                verdict = "" if args.no_answer else ("OK " if row["strict"] else ("~~ " if row["lenient"] else "-- "))
                print(f"{verdict}{q['qid']} cp{i:02d} {q['kind']:<6} {q['slot']:<18} gold@{gold_rank!s:<4} stale_above={stale_above} "
                      f"n={len(data):3d} {latency:.1f}s" + ("" if args.no_answer else f" | {row['prediction'][:60]!r}"), flush=True)
    client.__exit__(None, None, None)
    tmp.cleanup()

    out = Path(args.out_dir) / f"streaming-proxy-{args.label}-{run}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"label": args.label, "timestamps": not args.no_timestamps, "answer_model": MODEL,
                               "settings": {"embed": settings.embed_model, "planner": settings.planner_model, "rerank": settings.rerank_model,
                                            "options_mode": settings.options_mode, "turn_marks": settings.turn_marks, "time_notes": settings.time_notes},
                               "usage": usage, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["kind"]].append(r)
    groups["ALL"] = rows
    print(f"\n### streaming proxy · label={args.label} · timestamps={'off' if args.no_timestamps else 'on'} · questions={len(rows)}")
    print("| kind | n | strict acc | lenient acc | gold in list | gold rank (median) | stale above gold (mean) | results | chars | p50 latency |")
    print("|---" * 10 + "|")
    for kind in ["now", "later", "prev", "mcq", "revoke", "ALL"]:
        x = groups.get(kind, [])
        if not x:
            continue
        acc = f"{sum(r['strict'] for r in x) / len(x):.3f}" if not args.no_answer else "-"
        len_ = f"{sum(r['lenient'] for r in x) / len(x):.3f}" if not args.no_answer else "-"
        ranks = [r["gold_rank"] for r in x if r["gold_rank"]]
        print(f"| {kind} | {len(x)} | {acc} | {len_} | {sum(r['gold_in_list'] for r in x) / len(x):.3f} | "
              f"{statistics.median(ranks) if ranks else '-'} | {statistics.mean(r['stale_above'] for r in x):.2f} | "
              f"{statistics.mean(r['results'] for r in x):.0f} | {statistics.mean(r['chars'] for r in x):.0f} | "
              f"{statistics.median(r['latency_s'] for r in x):.2f}s |")
    cost = usage["prompt_tokens"] * 0.15 / 1e6 + usage["completion_tokens"] * 0.60 / 1e6
    print(f"\nanswer tokens: {usage['prompt_tokens']} in / {usage['completion_tokens']} out · ≈ ${cost:.2f}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
