# Cycle-1 open-source board: what the leaders did (notes, 2026-10-08)

Source: the official leaderboard data file served by the AML Hugging Face Space
(`huggingface.co/spaces/agent-memory-leaderboard/leaderboard`, `data/generated/leaderboard_data.json`,
published 2026-08-12), plus each entry's public repository. Scores are the platform's, in points.
Ideas listed here are *not* code: nothing from these repositories is copied (see `AGENTS.md`).

## Top 10 + the plain FTS5 baseline (academic textual, Cycle 1)

| # | system | overall | fact | comp | temp | gov | pers | exec | safe | method in one line | repo |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | InvMem | 45.1 | 56.8 | 46.0 | 21.8 | 32.6 | 53.1 | 30.8 | 30.3 | one row per message; bge-small-en-v1.5 dense + hand-written BM25, RRF k=60 with lexical weight 0.5; query = question + options; top-20 seeds expanded ±1 neighbour; relative-time annotations ("yesterday = 2024-01-01") on the text; no LLM | github.com/wenxiaof345-ctrl/vanilla-rag-memory (no licence) |
| 2 | ReFind | 45.0 | 57.7 | 45.3 | 19.6 | 33.3 | 52.8 | 28.3 | 30.3 | BM25 over raw chunks + gpt-4o-mini planner loop (≤4 search/note/finish actions), contextual evidence blocks | github.com/imlrz/ReFind (MIT) |
| 3 | ActiveMemoryIndex | 44.8 | 56.9 | 45.0 | 18.4 | 38.0 | 54.6 | 29.7 | 32.9 | dual store: verbatim timestamped turns + gpt-4o-mini-extracted first-person facts; text-embedding-v4; question rewritten as a first-person "Did I tell you …" recall question (HyDE-style), fused similarity; verbatim turns ordered first; returns the full top_k | github.com/linxuhao/ActiveMemoryIndex (MIT) |
| 4 | Hybrid Search v2.0 | 44.6 | 57.9 | 46.8 | 20.9 | 32.1 | 52.6 | 26.7 | 30.3 | BM25 + dense fused, synchronous embedding on write, per-user isolation | github.com/cydd-1972/hybrid_search |
| 5 | ChronoHybridMem | 44.3 | 55.7 | 44.4 | 23.3 | 32.9 | 57.1 | 28.3 | 35.0 | SQLite FTS5 + optional LLM fact extraction + multi-route candidate recall | github.com/Tin11Mn/chrono-hybrid-mem |
| 6 | Hybrid Episodic Memory | 44.3 | 55.5 | 45.9 | 21.6 | 34.2 | 57.3 | 28.1 | 27.1 | weighted RRF of BM25 (k1 1.5, b 0.75) + bge-small; option channel weight 0.6; recency nudge 0.15 in rank space; candidate depth 400; no LLM | github.com/tlysanhuo/agent-memory-challenge (MIT) |
| 7 | Chronicle | 44.2 | 56.2 | 43.9 | 21.2 | 30.4 | 52.6 | 28.6 | 30.3 | FTS5 + lexical/phrase/entity/relation/temporal signals, two-hop relation expansion, same-session neighbours | github.com/simple-boy/Chronicle-Memory |
| 8 | FlowGrid_AML_Retriever | 44.0 | 55.6 | 45.2 | 21.1 | 27.9 | 51.3 | 29.2 | 30.3 | deterministic evidence-first retriever, every original message stored | github.com/dlxeva/flowgrid-aml-retriever |
| 9 | LLLMemoryAgent | 43.1 | 54.5 | 42.7 | 24.6 | 30.3 | 53.5 | 27.6 | 29.7 | ChromaDB + local sentence-transformers, similarity-based write de-dup | github.com/llLAlisa/memory-agent-submission |
| 10 | aml-memory-mvp | 43.0 | 54.8 | 43.3 | 18.0 | 32.3 | 54.4 | 27.3 | 29.0 | SQLite FTS5 + character n-grams + conversation-neighbour expansion (closest to ours) | github.com/0xboyu/aml-memory-mvp |
| 16 | MemMachine | 42.2 | 63.5 | 53.1 | 37.9 | 38.7 | 44.2 | 11.7 | 30.3 | LLM-structured memory framework: best fact/composition/temporal on the board, but execution collapsed | github.com/MemMachine/MemMachine |
| 22 | SQLite-FTS-Baseline | 41.8 | 51.5 | 38.4 | 21.9 | 33.4 | 55.1 | 28.5 | 27.7 | plain FTS5 BM25, recency fallback | github.com/FantaSmallhamster/ldbd-sqlite-fts-baseline |

Field (50 entries): mean 39.4, median 40.8. Capability means: fact 48.0 · composition 38.2 · temporal 19.3 ·
governance 30.4 · personalization 52.8 · execution 26.1 · safety 35.8. Commercial #1 MemoraX 58.0 (temporal 60.0, fact 89.9).

## What separates the top 10 from ranks 11–30

| capability | top-10 mean | ranks 11–30 mean | gap |
|---|---|---|---|
| fact recall | 56.2 | 52.4 | +3.8 |
| composition | 44.9 | 41.8 | +3.1 |
| execution | 28.5 | 26.4 | +2.1 |
| personalization | 53.9 | 52.5 | +1.4 |
| temporal | 21.1 | 20.4 | +0.7 |
| governance | 32.4 | 32.7 | −0.3 |
| safety | 30.5 | 31.7 | −1.2 |

#1 InvMem vs the FTS5 baseline: composition +7.5, fact +5.3, safety +2.6, execution +2.3; temporal −0.1, governance −0.8,
personalization −1.9. The whole open-source gain over plain BM25 is **recall of evidence with little lexical overlap**
(multi-hop composition, paraphrased facts). Two proven routes: a dense channel (InvMem, #4, #6, #9, #3) or an LLM query
planner (ReFind). Temporal and governance were *not* solved by anyone in the open-source field (top-10 ≈ field); only
MemMachine's extraction-based memory moved temporal (37.9) and it paid 17 points on execution.

## Lessons we act on (ideas, attributed in `METHOD_CARD.md` when adopted)

1. **Dense channel fused by RRF** (InvMem, Hybrid Episodic Memory): the most common ingredient of the top 10 and the one that
   buys composition/fact recall. For Cycle 2 the open-source rule fixes the embedding model to `text-embedding-v4`
   (Alibaba Model Studio; user-defined dimensions 64–2048; ≈ US$0.07 per 1 M tokens on the international endpoint per
   third-party price lists, to confirm in the console). Plan: embed each turn (or each ±1 window) at 256–512 dims,
   store float16 per user next to the FTS rows, brute-force dot product per user like InvMem, RRF with the word index,
   the trigram index and the planner's extra queries. Storage at 300 M tokens ≈ 7.5 M turns × 0.5–1 KB ≈ 4–8 GB (34 GB free).
2. **Relative-time annotations** (InvMem): "yesterday = 2024-01-01" resolved from the turn's own timestamp, appended to
   the rendered text. Deterministic, cheap, aimed at the weakest leaf on the whole board ("Dates, Relative Time &
   Intervals", 18–21 % for everyone). Do it for English and Chinese expressions.
3. **Verbatim first, fill top_k** (ActiveMemoryIndex): their largest lever was ordering verbatim turns before derived
   text and returning all 100 items (accuracy rose monotonically with the count on LoCoMo with a gpt-4o-mini reader).
   We already return verbatim only and fill the budget; keep it that way and do not shrink the response.
4. **Option channel** (Hybrid Episodic Memory, InvMem): include the multiple-choice options in the retrieval query
   (we do) and, optionally, as a separately weighted channel.
5. **Not now:** gpt-4o-mini fact extraction at Add (ActiveMemoryIndex, ChronoHybridMem, MemMachine) — the biggest build,
   ≈ US$45+ per Full run at 300 M tokens, and MemMachine shows the execution-score risk of derived memories.
