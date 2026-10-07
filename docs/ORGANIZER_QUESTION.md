# Question for the organisers (draft; send from the contact address used in the form)

Subject: Open-source Methods — is an entry with no LLM/embedding model eligible?

Hello,

We are preparing an Open-source Methods entry for the Cycle 2 Textual track (system name: aml-memory).
Our Add and Search paths use no model at all: raw conversation turns are stored in SQLite and ranked
with BM25 (FTS5), with deterministic rules for context windows, recency and standing-instruction slots.

The Full-evaluation checklist says "Open-source Methods entries are expected to use gpt-4o-mini during
Add", and the FAQ specifies gpt-4o-mini for LLM components and text-embedding-v4 for embeddings.
Could you confirm whether an entry that uses **no** LLM and **no** embedding model is eligible for the
Open-source Methods board and for prize review? If a later version adds an LLM call, it will be
gpt-4o-mini only, declared in the method card.

Thank you,
<name> · <team/organisation>
