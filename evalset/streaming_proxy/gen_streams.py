"""Our own streaming-memory proxy (synthetic, seeded, no external data).

The Cycle-2 Streaming branch interleaves Add and Search "as events unfold" and asks the system to use what was
known *at that time* and to recognise updates, conflicts and invalidation. No streaming dataset is public, so this
file builds a stand-in from templates only: three users, ~40 short sessions each (one Add per session), a dozen
*slots* per user whose values change over the stream, standing rules that get replaced or revoked, plans that get
cancelled, and a few statements that are contradicted and then clarified one session later.

Questions are attached to checkpoints (session indexes). The same slot is asked right after a change and again
later, so the gold answer depends on when it is asked. Multiple-choice variants list every value the slot ever
takes in the whole stream (past and future), so stale values are the distractors.

    uv run python evalset/streaming_proxy/gen_streams.py        # writes streams.json and questions.json next to it
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = 20261023
USERS = 3
SESSIONS = 40

# kind: fact = a value that is replaced; rule = a standing instruction (can be revoked -> None);
# plan = a dated plan (can be cancelled -> None). Values are deliberately plain and distinctive.
# slot -> (phrase used in questions, phrase the user says, values). ORDERED slots keep their values in list order
# (dates move forward); the others are sampled in random order.
FACT_SLOTS = {
    "city": ("the city the user lives in", "the city I live in", ["Leeds", "Bristol", "Aberdeen", "Norwich"]),
    "employer": ("the company the user works for", "my employer", ["Halvern Logistics", "Pinecrest Analytics", "Orbital Dairy", "Mossbank Press"]),
    "job title": ("the user's job title", "my job title", ["operations analyst", "supply planner", "fleet coordinator"]),
    "team meeting day": ("the weekday of the user's weekly team meeting", "our weekly team meeting day", ["Tuesday", "Thursday", "Monday", "Wednesday"]),
    "Marigold deadline": ("the deadline of the user's Marigold project", "the Marigold deadline", ["14 March", "2 April", "28 April", "19 May"]),
    "phone carrier": ("the user's phone carrier", "my phone carrier", ["Vodafone", "giffgaff", "Three"]),
    "car": ("the car the user drives", "my car", ["a blue Skoda Fabia", "a grey Toyota Yaris", "a red Honda Jazz"]),
    "main client": ("the user's main client account", "my main client", ["Brightwater Foods", "Kestrel Marine", "Dunmore Hotels", "Ashgrove Timber"]),
    "gym": ("the gym the user goes to", "my gym", ["PureGym Kirkstall", "the university sports centre", "Nuffield on Park Row"]),
    "coffee order": ("the user's usual coffee order", "my usual coffee order", ["a flat white", "a black americano", "an oat latte"]),
}
ORDERED = {"Marigold deadline"}
RULE_SLOTS = {
    "reply format": ("the user's rule about how replies should be formatted",
                     ["always answer in bullet points", "answer in plain paragraphs, no bullet points", "keep every answer under three sentences"]),
    "scheduling": ("the user's rule about scheduling",
                   ["never book anything before 10am", "keep Friday afternoons free", "avoid back-to-back calls"]),
    "units": ("the user's rule about units", ["use metric units", "use imperial units"]),
}
PLAN_SLOTS = {
    "spring trip": ("the user's spring trip", ["Lisbon in March", "Porto in April", "Seville in May"]),
    "course": ("the evening course the user signed up for", ["the Tuesday pottery course", "the Thursday Spanish class"]),
}
FACT_TEMPLATES = ["Update for you: {desc} is now {v}.", "Just so you know, {desc} changed - it's {v} now.",
                  "Small change: {desc} is {v} from today."]
RULE_SET = ["From now on, please {v}.", "New rule for our chats: {v}."]
RULE_DROP = ["You can drop the rule about {topic}; it no longer applies.", "Forget what I said about {topic}, no rule there anymore."]
PLAN_SET = ["New plan: {topic} is {v}.", "Booked it - {topic} will be {v}."]
PLAN_DROP = ["The {topic} is cancelled, scrap it.", "Change of heart: no {topic} this year after all."]
CLARIFY = "Actually I misspoke earlier - {desc} is {v}, not {old}."
FILLERS_USER = ["Can you remind me what we discussed about the budget last week?", "What's a quick stretch for a stiff neck?",
                "Draft a two-line thank-you note for a colleague.", "How long does it take to roast a tray of vegetables?",
                "Give me three names for a houseplant.", "What's the difference between a latte and a cortado?",
                "Suggest a short walk for a rainy afternoon.", "How do I phrase a polite reminder email?",
                "Any tips for keeping a sourdough starter alive?", "What should I pack for a one-night train trip?",
                "Recommend a podcast about city planning.", "How many litres are in a US gallon?"]
FILLERS_ASSISTANT = ["Sure - here is a short answer.", "Noted, I'll keep that in mind.", "Happy to help with that.",
                     "Good question; here is what I'd suggest.", "Got it. Anything else for today?"]


def build(rng: random.Random, user_idx: int) -> tuple[dict, list[dict]]:
    """One user's stream (sessions with keyed messages) and the questions attached to its checkpoints."""
    uid = f"stream-{user_idx}"
    start = datetime(2025, 1, 6, 9, 0) + timedelta(days=11 * user_idx)
    sessions = [{"start": (start + timedelta(days=2 * i, minutes=rng.randint(0, 540))).strftime("%Y-%m-%d %H:%M"),
                 "messages": []} for i in range(SESSIONS)]
    events: list[dict] = []                       # {slot, kind, session, value, old, key}
    counter = [0]

    def key(sess: int) -> str:
        counter[0] += 1
        return f"{uid}:s{sess:02d}:m{counter[0]:03d}"

    def schedule(n_changes: int) -> list[int]:
        """Sessions for the first statement and later changes, spaced at least 4 sessions apart."""
        while True:
            picks = sorted(rng.sample(range(1, SESSIONS - 3), n_changes))
            if all(b - a >= 4 for a, b in zip(picks, picks[1:])):
                return picks

    slot_values: dict[str, list[tuple[int, str | None, str]]] = {}   # slot -> [(session, value, key)]
    for slot, (desc, said, values) in FACT_SLOTS.items():
        n = rng.randint(2, min(3, len(values)))
        chosen = sorted(rng.sample(values, n), key=values.index) if slot in ORDERED else rng.sample(values, n)
        hist = []
        for sess, v in zip(schedule(n), chosen):
            k = key(sess)
            sessions[sess]["messages"].append({"role": "user", "content": rng.choice(FACT_TEMPLATES).format(desc=said, v=v), "key": k})
            hist.append((sess, v, k))
        slot_values[slot] = hist
    for slot, (desc, values) in RULE_SLOTS.items():
        n = rng.randint(1, min(2, len(values)))
        chosen = rng.sample(values, n)
        picks = schedule(n + 1)                     # last pick = revocation
        hist = []
        for sess, v in zip(picks[:-1], chosen):
            k = key(sess)
            sessions[sess]["messages"].append({"role": "user", "content": rng.choice(RULE_SET).format(v=v), "key": k})
            hist.append((sess, v, k))
        k = key(picks[-1])
        sessions[picks[-1]]["messages"].append({"role": "user", "content": rng.choice(RULE_DROP).format(topic=slot), "key": k})
        hist.append((picks[-1], None, k))
        slot_values[slot] = hist
    for slot, (desc, values) in PLAN_SLOTS.items():
        n = rng.randint(1, min(2, len(values)))
        chosen = rng.sample(values, n)
        picks = schedule(n + 1)
        hist = []
        for sess, v in zip(picks[:-1], chosen):
            k = key(sess)
            sessions[sess]["messages"].append({"role": "user", "content": rng.choice(PLAN_SET).format(topic=slot, v=v), "key": k})
            hist.append((sess, v, k))
        k = key(picks[-1])
        sessions[picks[-1]]["messages"].append({"role": "user", "content": rng.choice(PLAN_DROP).format(topic=slot), "key": k})
        hist.append((picks[-1], None, k))
        slot_values[slot] = hist
    # two contradiction + clarification pairs per user: the slot gets a wrong value, corrected next session
    for slot in rng.sample([s for s in FACT_SLOTS if s not in ORDERED], 2):
        desc, said, values = FACT_SLOTS[slot]
        hist = slot_values[slot]
        last_sess, last_v, _ = hist[-1]
        if last_sess + 2 >= SESSIONS:
            continue
        wrong = rng.choice([v for v in values if v != last_v])
        k1 = key(last_sess + 1)
        sessions[last_sess + 1]["messages"].append({"role": "user", "content": rng.choice(FACT_TEMPLATES).format(desc=said, v=wrong), "key": k1})
        k2 = key(last_sess + 2)
        sessions[last_sess + 2]["messages"].append({"role": "user", "content": CLARIFY.format(desc=said, v=last_v, old=wrong), "key": k2})
        hist.append((last_sess + 1, wrong, k1))
        hist.append((last_sess + 2, last_v, k2))

    # fill every session to 12-16 alternating messages, slot statements first (they are user turns)
    for sess in sessions:
        slot_msgs = sess["messages"]
        target = rng.randint(12, 16)
        msgs: list[dict] = []
        pending = list(slot_msgs)
        while len(msgs) < target:
            if pending and len(msgs) % 2 == 0:
                msgs.append(pending.pop(0))
            elif len(msgs) % 2 == 0:
                msgs.append({"role": "user", "content": rng.choice(FILLERS_USER)})
            else:
                msgs.append({"role": "assistant", "content": rng.choice(FILLERS_ASSISTANT)})
        sess["messages"] = msgs

    # questions per slot change: now / later / mcq (+ prev for a quarter of fact changes, revoke for rules & plans)
    questions: list[dict] = []
    qn = [0]

    def q(**fields) -> None:
        qn[0] += 1
        questions.append({"qid": f"{uid}#q{qn[0]:03d}", "user": uid, **fields})

    for slot, hist in slot_values.items():
        kind = "fact" if slot in FACT_SLOTS else ("rule" if slot in RULE_SLOTS else "plan")
        spec = FACT_SLOTS.get(slot) or RULE_SLOTS.get(slot) or PLAN_SLOTS.get(slot)
        desc, pool = spec[0], spec[-1]
        all_values = list(dict.fromkeys(v for _, v, _ in hist if v is not None))   # every value the slot ever takes, once
        extra = [v for v in pool if v not in all_values]
        for i, (sess, v, k) in enumerate(hist):
            next_sess = hist[i + 1][0] if i + 1 < len(hist) else SESSIONS
            stale = [(hv, hk) for hs, hv, hk in hist[:i] if hv is not None and hv != v]
            if v is None:   # revocation / cancellation: ask as multiple choice only
                opts = all_values[:] + [f"No {slot} rule is in effect" if kind == "rule" else f"No {slot} is planned"]
                rng.shuffle(opts)
                gold = opts.index(opts[-1] if False else next(o for o in opts if o.startswith("No ")))
                stem = (f"Which instruction about {slot} is currently in effect?" if kind == "rule"
                        else f"What is currently planned for the {slot}?")
                q(checkpoint=min(sess + 1, SESSIONS - 1), kind="revoke", slot=slot, stem=stem, options=opts,
                  gold_letter=chr(65 + gold), gold_value=None, stale_values=[hv for hv, _ in stale],
                  evidence_key=k, stale_keys=[hk for _, hk in stale])
                continue
            wording = f"What is {desc} right now?" if kind == "fact" else (
                f"What is the user's current rule about {slot}?" if kind == "rule" else f"What is the user's current plan for the {slot}?")
            base = dict(slot=slot, stem=wording, gold_value=v, stale_values=[hv for hv, _ in stale],
                        evidence_key=k, stale_keys=[hk for _, hk in stale])
            q(checkpoint=sess, kind="now", **base)
            if next_sess - sess >= 3:
                q(checkpoint=min(sess + rng.randint(2, max(2, next_sess - sess - 1)), SESSIONS - 1), kind="later", **base)
            opts = all_values[:] + ([rng.choice(extra)] if extra else [])
            rng.shuffle(opts)
            q(checkpoint=min(sess + 1, next_sess - 1) if next_sess - sess >= 2 else sess, kind="mcq", options=opts,
              gold_letter=chr(65 + opts.index(v)), **base)
            if i >= 1 and kind == "fact" and rng.random() < 0.35:
                prev_v, prev_k = hist[i - 1][1], hist[i - 1][2]
                q(checkpoint=min(sess + 1, next_sess - 1) if next_sess - sess >= 2 else sess, kind="prev", slot=slot,
                  stem=f"What was {desc} before the most recent change?", gold_value=prev_v,
                  stale_values=[hv for hs, hv, hk in hist[:i - 1] if hv not in (None, prev_v)] + [v],
                  evidence_key=prev_k, stale_keys=[hk for hs, hv, hk in hist[:i - 1] if hv not in (None, prev_v)] + [k])
    for item in questions:   # render the question text; options are also sent in the API's top-level field
        if item.get("options"):
            letters = "\n".join(f"{chr(65 + j)}. {o}" for j, o in enumerate(item["options"]))
            item["question"] = f"{item['stem']}\n\n{letters}\n\nAnswer with the single option letter only."
        else:
            item["question"] = item["stem"]
    questions.sort(key=lambda x: (x["checkpoint"], x["qid"]))
    return {"user": uid, "sessions": sessions}, questions


def main() -> None:
    rng = random.Random(SEED)
    streams, questions = [], []
    for u in range(USERS):
        s, qs = build(rng, u)
        streams.append(s)
        questions.extend(qs)
    (HERE / "streams.json").write_text(json.dumps(streams, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "questions.json").write_text(json.dumps(questions, ensure_ascii=False, indent=1), encoding="utf-8")
    turns = sum(len(s["messages"]) for st in streams for s in st["sessions"])
    kinds = {}
    for item in questions:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    print(f"users={USERS} sessions/user={SESSIONS} turns={turns} questions={len(questions)} by kind={kinds}")


if __name__ == "__main__":
    main()
