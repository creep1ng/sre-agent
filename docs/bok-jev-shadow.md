# BoK Jev shadow evaluation

Jev is an optional relevance signal for experimenting with already-authorized BoK
search results. It is **shadow-only**: PostgreSQL lexical ranking remains the
returned order, and Jev cannot grant access, filter results, or change answers.
The default path makes no TypeSafe request.

## Quick path

1. Use only a synthetic BoK corpus. The runtime rejects evaluator calls when a
   candidate's source reference is not `synthetic://`.
2. Configure both `BOK_JEV_ENABLED=true` and `TYPESAFE_API_KEY`. The key alone
   does not enable evaluation. `BOK_JEV_TIMEOUT_SECONDS` is optional (default
   5 seconds; maximum 30).
3. Explicitly request shadow mode on an authorized search:

   ```json
   {
     "query": "How should incident severity be assigned?",
     "limit": 5,
     "evaluation_mode": "shadow"
   }
   ```

The server evaluates at most five lexical candidates. It returns the same
`results` array and order as the non-Jev request, plus an `evaluation` status,
the model ID, token counts, elapsed time, and per-chunk relevance scores. No
query or chunk text is added to audit records or logs. Evaluator, timeout,
provider, and response-validation failures produce a content-free fallback
status and leave lexical results unchanged. Requests without
`evaluation_mode: "shadow"`, denied or unready requests, empty searches, and
direct chunk reads do not invoke Jev.

## Privacy and safety boundary

The live adapter transmits the query and selected passage text to TypeSafe. This
implementation only allows that path for chunks whose owner-provided source
reference is marked `synthetic://`; do not mark customer or operational content
synthetic. Do not enable live evaluation until the data owner has approved the
transfer and reviewed applicable privacy terms. TypeSafe says customer
requests/responses are not used to train Jev and documents zero data retention
for enterprise customers; those statements do not establish ZDR for other
plans. See [TypeSafe model and data-handling notes](https://docs.typesafe.ai/models).

Jev is not a security control, prompt-injection detector, exact ranker, or
authorization policy. The experiment asks one semantic relevance question per
query-passage pair and only records a score. The official RAG cookbook uses
several separate questions and program-owned routing thresholds; this smaller
experiment does not adopt those thresholds or routing decisions. Treat every
score as advisory, not ground truth. Jev 1.13's documented jaggedness includes
literal interpretation, difficulty with indirection and numbers, and risks
around adversarial content; do not rely on its output to make security or
mathematical decisions. See [the RAG passage-classification cookbook](https://docs.typesafe.ai/cookbooks/classifying_rag_passages)
and [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13).

## Cost, latency, and versioning

The adapter pins `jev-1.13.0`, sends one HTTP request per evaluated chunk, and
caps each request at five candidates. Those calls are concurrent and share a
five-second default timeout; no retries are made. A failed or rate-limited
evaluation falls back immediately to lexical results. Measure end-to-end
latency and token counts in the actual environment before expanding the cap.

At the time this guide was written, TypeSafe's model page listed Jev 1.13 at
$0.042 per million input tokens, with output tokens free; provider rates and
limits may change. The cookbook still reports results from `jev-1.12`, so its
thresholds and examples should not be assumed to validate this pinned model.
Confirm current details in the [models page](https://docs.typesafe.ai/models)
before any cost estimate. The integration uses the documented
`POST https://api.typesafe.ai/v1/systemone` contract and validates the returned
model ID, `Noul` answer, and usage fields; see the [HTTP API reference](https://docs.typesafe.ai/api).

## What this does not prove

- No live TypeSafe request or model result is required by the local acceptance
  tests; they use a deterministic synthetic evaluator and HTTP mock transport.
- A positive Jev score does not show retrieval quality improved. Compare
  against a human-judged relevance set before considering a ranking change.
- This experiment does not reorder or remove results. A future reranker needs a
  separately reviewed evaluation design and evidence; it must retain the same
  authorization boundary and failure fallback.
